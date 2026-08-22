"""Local deployment provider — runs instances on the control-plane host.

Instead of going through a node agent, this provider speaks the LXD REST API
directly over the host's unix socket (the panel container mounts it). It
mirrors the agent's LXD logic one-to-one so behaviour is identical across
deployment modes.
"""

import ipaddress
from pathlib import Path
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.errors import NodeUnavailableError, ProviderError
from app.core.logging import get_logger
from app.providers.base import ComputeProvider, ConsoleTarget, InstanceSpec, InstanceState

log = get_logger("cvx.local_lxd")

LXD_SOCKET_CANDIDATES = [
    "/var/lib/lxd/unix.socket",              # apt/deb
    "/var/snap/lxd/common/lxd/unix.socket",  # snap
    "/var/lib/incus/unix.socket",            # Incus-compatible fallback
]

NODE_LOCAL_NAME = "local-machine"


class LXDError(Exception):
    """LXD API error carrying the HTTP status code."""

    def __init__(self, status: int, message: str) -> None:
        self.status = status
        self.message = message
        super().__init__(f"LXD error {status}: {message}")


def find_local_socket() -> str | None:
    """Return the first available LXD unix socket path, if any."""
    override = get_settings().lxd_socket_path
    candidates = [override] if override else []
    candidates.extend(LXD_SOCKET_CANDIDATES)
    for path in candidates:
        try:
            if path and Path(path).exists():
                return path
        except OSError:
            continue
    return None


def local_deployment_available() -> bool:
    return get_settings().enable_local_deployment and find_local_socket() is not None


class LocalLXDClient:
    """Minimal async LXD REST client over the unix socket."""

    def __init__(self, socket_path: str | None = None) -> None:
        self.socket_path = socket_path or find_local_socket()
        if self.socket_path is None:
            raise NodeUnavailableError(
                "LXD unix socket not found on the control-plane host."
            )
        transport = httpx.AsyncHTTPTransport(uds=self.socket_path)
        self._client = httpx.AsyncClient(
            transport=transport, base_url="http://localhost", timeout=120.0
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        json_body: dict[str, Any] | None = None,
        wait: bool = True,
    ) -> dict[str, Any]:
        params: dict[str, str] = {"project": "default"}
        if wait:
            params["wait"] = "60"
        try:
            resp = await self._client.request(method, path, json=json_body, params=params)
        except httpx.HTTPError as e:
            raise NodeUnavailableError(f"LXD socket unreachable: {path}") from e
        try:
            data = resp.json()
        except ValueError:
            raise LXDError(
                resp.status_code, f"non-JSON response (HTTP {resp.status_code})"
            ) from None
        meta_type = data.get("type")
        if resp.status_code >= 400 or meta_type == "error":
            raise LXDError(
                resp.status_code if resp.status_code >= 400 else 500,
                str(data.get("error", "unknown LXD error")),
            )
        return data

    # --- server info & capacity ---

    async def server_info(self) -> dict[str, Any]:
        data = await self._request("GET", "/1.0")
        env = data.get("metadata", {}).get("environment", {})
        return {
            "lxd_version": env.get("server_version"),
            "os_name": env.get("server_os") or env.get("distribution"),
            "os_version": env.get("server_release") or env.get("kernel_version"),
            "kernel_version": env.get("kernel_version"),
            "architecture": env.get("kernel_architecture"),
            "hostname": env.get("hostname"),
        }

    async def resources(self) -> dict[str, Any]:
        data = await self._request("GET", "/1.0/resources", wait=False)
        md = data.get("metadata", {})
        cpu_total = 0
        cpus = md.get("cpu", {}).get("total")
        if isinstance(cpus, int):
            cpu_total = cpus
        memory_total = int(md.get("memory", {}).get("total") or 0)
        return {"cpu_cores": cpu_total, "memory_total_bytes": memory_total}

    async def storage_usage(self) -> dict[str, Any]:
        out = {"storage_total_bytes": 0, "storage_used_bytes": 0}
        try:
            pools = await self._request("GET", "/1.0/storage-pools", wait=False)
        except LXDError:
            return out
        for url in pools.get("metadata", []):
            pool_name = url.rsplit("/", 1)[-1]
            try:
                pool = await self._request(
                    "GET", f"/1.0/storage-pools/{pool_name}", wait=False
                )
            except LXDError:
                continue
            usage = pool.get("metadata", {}).get("space") or {}
            total = int(usage.get("total") or 0)
            used = int(usage.get("used") or 0)
            if total > out["storage_total_bytes"]:
                out["storage_total_bytes"] = total
                out["storage_used_bytes"] = used
        return out

    # --- instances ---

    async def create_instance(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name", ""))
        devices: dict[str, Any] = {
            "root": {
                "path": "/",
                "pool": "default",
                "type": "disk",
                **({"size": payload["disk"]["size"]} if (payload.get("disk") or {}).get("size") else {}),
            }
        }
        net = payload.get("network") or "lxdbr0"
        eth0: dict[str, Any] = {
            "name": "eth0",
            "nictype": "bridged",
            "parent": net,
            "type": "nic",
        }
        if payload.get("ipv4"):
            eth0["ipv4.address"] = payload["ipv4"]
        if payload.get("ipv6"):
            eth0["ipv6.address"] = payload["ipv6"]
        devices["eth0"] = eth0

        body = {
            "name": name,
            "source": _image_source(str(payload.get("image", ""))),
            "config": payload.get("config", {}),
            "devices": devices,
            "instance_type": "container",
        }
        await self._request("POST", "/1.0/instances", body)
        await self.start_instance(name)
        info = await self.get_instance(name)
        assert info is not None
        dns = str((payload.get("config", {}) or {}).get("user.cvx_dns") or "").split()
        if dns:
            await self.apply_dns(name, dns)
        return info

    async def apply_dns(self, name: str, dns_servers: list[str]) -> None:
        # Defense in depth: re-validate upstream-supplied values before they
        # reach any command construction (mirrors the agent exactly).
        valid: list[str] = []
        for entry in dns_servers:
            try:
                valid.append(str(ipaddress.ip_address(entry)))
            except ValueError:
                continue
        if not valid:
            return
        dns_joined = " ".join(valid)
        script = (
            "mkdir -p /etc/systemd/resolved.conf.d && "
            f"printf '[Resolve]\\nDNS={dns_joined}\\n' > "
            "/etc/systemd/resolved.conf.d/cvx.conf && "
            "systemctl restart systemd-resolved || true"
        )
        try:
            await self.exec_command(name, ["sh", "-c", script])
        except Exception:
            pass  # best-effort; image may not use systemd-resolved

    async def get_instance(self, name: str) -> dict[str, Any] | None:
        try:
            data = await self._request("GET", f"/1.0/instances/{name}", wait=False)
        except LXDError as e:
            if e.status == 404:
                return None
            raise
        md = data.get("metadata", {})
        state = await self.get_state(name)
        ips: dict[str, str] = {}
        for iface, details in (state.get("network") or {}).items():
            if iface == "lo":
                continue
            for addr in details.get("addresses", []):
                if addr.get("family") == "inet":
                    ips[iface] = addr.get("address", "")
                    break
        config = md.get("config", {}) or {}
        return {
            "name": name,
            "status": md.get("status", "Unknown"),
            "pid": state.get("pid"),
            "process_count": state.get("processes"),
            "ips": ips,
            "created_at": md.get("created_at"),
            "raw": {"config": config, "mac": _first_mac(state)},
        }

    async def get_state(self, name: str) -> dict[str, Any]:
        data = await self._request(
            "GET", f"/1.0/instances/{name}/state", wait=False
        )
        return data.get("metadata", {})

    async def start_instance(self, name: str) -> None:
        await self._request(
            "PUT", f"/1.0/instances/{name}/state", {"action": "start"}
        )

    async def stop_instance(self, name: str, timeout: int = 30, force: bool = False) -> None:
        await self._request(
            "PUT",
            f"/1.0/instances/{name}/state",
            {"action": "stop", "timeout": timeout, "force": force},
        )

    async def restart_instance(self, name: str, timeout: int = 30) -> None:
        await self._request(
            "PUT",
            f"/1.0/instances/{name}/state",
            {"action": "restart", "timeout": timeout},
        )

    async def delete_instance(self, name: str) -> None:
        # Delete snapshots explicitly first: some storage drivers refuse to
        # remove an instance that still has snapshots (mirrors the agent).
        try:
            snaps = await self.list_snapshots(name)
        except LXDError as e:
            if e.status != 404:
                raise
            snaps = []
        except Exception:
            snaps = []
        for snap in snaps:
            try:
                await self.delete_snapshot(name, str(snap.get("name", "")))
            except Exception:
                continue
        try:
            await self.stop_instance(name, timeout=15)
        except Exception:
            pass
        await self._request("DELETE", f"/1.0/instances/{name}")

    async def patch_config(self, name: str, config: dict[str, str]) -> None:
        await self._request("PATCH", f"/1.0/instances/{name}", {"config": config})

    # --- metrics ---

    async def instance_metrics(self, name: str) -> dict[str, Any]:
        state = await self.get_state(name)
        cpu = state.get("cpu", {}) or {}
        memory = state.get("memory", {}) or {}
        disk = (state.get("disk") or {}).get("root", {}) or {}
        net_rx = sum(
            (n or {}).get("bytes_received", 0) for n in (state.get("network") or {}).values()
        )
        net_tx = sum(
            (n or {}).get("bytes_sent", 0) for n in (state.get("network") or {}).values()
        )
        return {
            "cpu_usage_ns": cpu.get("usage"),
            "mem_used_bytes": memory.get("usage"),
            "mem_total_bytes": memory.get("usage_peak"),
            "swap_used_bytes": memory.get("swap_usage"),
            "disk_used_bytes": disk.get("usage"),
            "disk_total_bytes": disk.get("usage_total"),
            "net_rx_bytes_total": net_rx,
            "net_tx_bytes_total": net_tx,
            "processes": state.get("processes"),
            "status": state.get("status"),
        }

    # --- snapshots / backups ---

    async def create_snapshot(
        self, name: str, snap_name: str, stateful: bool = False
    ) -> dict[str, Any]:
        await self._request(
            "POST",
            f"/1.0/instances/{name}/snapshots",
            {"name": snap_name, "stateful": stateful},
        )
        size = None
        created = None
        try:
            snap = await self._request(
                "GET", f"/1.0/instances/{name}/snapshots/{snap_name}", wait=False
            )
            md = snap.get("metadata", {})
            size = int(md.get("size") or 0) or None
            created = md.get("created_at")
        except Exception:
            pass
        return {"uuid": f"{name}/{snap_name}", "size": size, "created_at": created}

    async def list_snapshots(self, name: str) -> list[dict[str, Any]]:
        data = await self._request(
            "GET", f"/1.0/instances/{name}/snapshots", wait=False
        )
        urls = data.get("metadata", [])
        snaps = []
        for u in urls:
            snap_name = u.rsplit("/", 1)[-1]
            try:
                sd = await self._request(
                    "GET", f"/1.0/instances/{name}/snapshots/{snap_name}", wait=False
                )
                md = sd.get("metadata", {})
                snaps.append(
                    {
                        "name": snap_name,
                        "description": md.get("description") or None,
                        "stateful": bool(md.get("stateful")),
                        "size": int(md.get("size") or 0) or None,
                        "created_at": md.get("created_at"),
                    }
                )
            except Exception:
                continue
        return snaps

    async def delete_snapshot(self, name: str, snap_name: str) -> None:
        await self._request("DELETE", f"/1.0/instances/{name}/snapshots/{snap_name}")

    async def rename_snapshot(self, name: str, snap_name: str, new_name: str) -> None:
        await self._request(
            "POST",
            f"/1.0/instances/{name}/snapshots/{snap_name}",
            {"name": new_name},
        )

    async def restore_snapshot(self, name: str, snap_name: str) -> dict[str, Any]:
        await self._request(
            "PUT",
            f"/1.0/instances/{name}/snapshots/{snap_name}",
            {"restore": True},
        )
        return {"restored": f"{name}/{snap_name}"}

    async def create_backup(
        self, name: str, backup_name: str, optimized_storage: bool = True
    ) -> dict[str, Any]:
        await self._request(
            "POST",
            f"/1.0/instances/{name}/backups",
            {
                "name": backup_name,
                "instance_only": False,
                "optimized_storage": optimized_storage,
            },
        )
        info = await self._request(
            "GET", f"/1.0/instances/{name}/backups/{backup_name}", wait=False
        )
        md = info.get("metadata", {})
        return {
            "size": int(md.get("size") or 0) or None,
            "path": "",
            "checksum": None,
        }

    async def delete_backup(self, backup_name: str) -> None:
        data = await self._request("GET", "/1.0/instances", wait=False)
        for u in data.get("metadata", []):
            inst = u.rsplit("/", 1)[-1]
            try:
                await self._request(
                    "DELETE", f"/1.0/instances/{inst}/backups/{backup_name}"
                )
                return
            except Exception:
                continue
        raise ProviderError(f"Backup {backup_name} not found on any local instance")

    # --- exec (restricted internal use only) ---

    async def exec_command(self, name: str, command: list[str]) -> tuple[int, str]:
        body = {
            "command": command,
            "environment": {"TERM": "dumb"},
            "wait-for-websocket": False,
            "record-output": True,
            "interactive": False,
        }
        op = await self._request("POST", f"/1.0/instances/{name}/exec", body)
        metadata = op.get("metadata", {})
        output = metadata.get("output") or {}
        combined_url = output.get("2") or ""
        text = ""
        if combined_url:
            resp = await self._client.get(combined_url)
            text = resp.text
        return int(metadata.get("return", 0)), text


class LocalLXDProvider(ComputeProvider):
    """ComputeProvider implementation for the control-plane host's own LXD."""

    def __init__(self, client: LocalLXDClient | None = None) -> None:
        self.client = client or LocalLXDClient()

    async def ping(self) -> dict[str, Any]:
        return await self.client.server_info()

    async def create_instance(self, spec: InstanceSpec) -> InstanceState:
        from app.providers.lxd import LXDProvider

        payload = {
            "name": spec.name,
            "image": spec.image_source,
            "config": LXDProvider._build_config(spec),
            "disk": {"size": f"{spec.disk_gb}GiB"},
            "network": spec.network_name,
            "ipv4": spec.ipv4,
            "ipv6": spec.ipv6,
        }
        data = await self.client.create_instance(payload)
        return _to_state(data)

    async def get_instance(self, name: str) -> InstanceState | None:
        try:
            data = await self.client.get_instance(name)
        except Exception:
            return None
        if data is None:
            return None
        return _to_state(data)

    async def delete_instance(self, name: str) -> None:
        await self.client.delete_instance(name)

    async def start(self, name: str) -> dict[str, Any]:
        await self.client.start_instance(name)
        return {}

    async def stop(self, name: str, timeout: int = 30) -> dict[str, Any]:
        await self.client.stop_instance(name, timeout=timeout)
        return {}

    async def restart(self, name: str, timeout: int = 30) -> dict[str, Any]:
        await self.client.restart_instance(name, timeout=timeout)
        return {}

    async def shutdown(self, name: str, timeout: int = 120) -> dict[str, Any]:
        await self.client.stop_instance(name, timeout=timeout)
        return {}

    async def set_config(self, name: str, config: dict[str, str]) -> dict[str, Any]:
        await self.client.patch_config(name, config)
        return {}

    async def instance_metrics(self, name: str) -> dict[str, Any]:
        return await self.client.instance_metrics(name)

    async def create_snapshot(
        self, name: str, snapshot_name: str, stateful: bool = False
    ) -> dict[str, Any]:
        return await self.client.create_snapshot(name, snapshot_name, stateful)

    async def delete_snapshot(self, name: str, snapshot_name: str) -> None:
        await self.client.delete_snapshot(name, snapshot_name)

    async def rename_snapshot(
        self, name: str, snapshot_name: str, new_name: str
    ) -> None:
        await self.client.rename_snapshot(name, snapshot_name, new_name)

    async def restore_snapshot(self, name: str, snapshot_name: str) -> dict[str, Any]:
        return await self.client.restore_snapshot(name, snapshot_name)

    async def list_snapshots(self, name: str) -> list[dict[str, Any]]:
        return await self.client.list_snapshots(name)

    async def create_backup(
        self, name: str, backup_name: str, optimized_storage: bool = True
    ) -> dict[str, Any]:
        return await self.client.create_backup(name, backup_name, optimized_storage)

    async def delete_backup(self, backup_name: str) -> None:
        await self.client.delete_backup(backup_name)

    async def restore_backup(self, name: str, backup_path: str) -> dict[str, Any]:
        raise ProviderError(
            "Backup archive restore is not supported for locally deployed VPSes; "
            "use snapshot restore instead."
        )

    async def console_target(self, name: str, cols: int, rows: int) -> ConsoleTarget:
        """Start an interactive PTY session and return its websocket endpoints."""
        settings = get_settings()
        shell = settings.local_console_shell or "/bin/bash"
        body = {
            "command": [shell, "-il"],
            "environment": {"TERM": "xterm-256color"},
            "interactive": True,
            "wait-for-websocket": True,
            "width": max(2, min(500, cols)),
            "height": max(2, min(200, rows)),
        }
        op = await self.client._request(
            "POST", f"/1.0/instances/{name}/exec", body, wait=False
        )
        md = op.get("metadata", {})
        fds = (md.get("metadata") or {}).get("fds") or {}
        op_id = op.get("id") or md.get("id") or ""
        if not op_id or not fds:
            raise ProviderError("LXD exec did not return websocket endpoints")
        return ConsoleTarget(
            kind="lxd",
            socket_path=self.client.socket_path,
            fd_secrets={str(k): str(v) for k, v in fds.items()},
            url=f"ws://localhost/1.0/operations/{op_id}/websocket",
        )


async def local_capacity() -> dict[str, Any]:
    """Coarse capacity facts for the control-plane host (for the nodes row)."""
    client = LocalLXDClient()
    try:
        info = await client.server_info()
        res = await client.resources()
        store = await client.storage_usage()
    finally:
        await client.close()
    return {
        **info,
        "cpu_cores": res["cpu_cores"] or 1,
        "ram_total_mb": max(1, res["memory_total_bytes"] // (1024 * 1024)),
        "storage_total_gb": max(
            1, store["storage_total_bytes"] // (1024 * 1024 * 1024)
        ),
        "storage_used_gb": store["storage_used_bytes"] // (1024 * 1024 * 1024),
    }


async def local_status() -> dict[str, Any]:
    """Full local-host status for the admin/local-machine endpoints."""
    cap = await local_capacity()
    return {
        "available": True,
        "socket_path": LocalLXDClient().socket_path,
        **cap,
    }


def _to_state(data: dict[str, Any]) -> InstanceState:
    return InstanceState(
        name=data.get("name", ""),
        status=data.get("status", "unknown"),
        pid=data.get("pid"),
        process_count=data.get("process_count"),
        ips=data.get("ips", {}) or {},
        created_at=data.get("created_at"),
        raw=data.get("raw", {}) or {},
    )


def _image_source(ref: str) -> dict[str, Any]:
    if ":" in ref:
        remote, identifier = ref.split(":", 1)
        if remote == "ubuntu":
            return {
                "type": "image",
                "protocol": "simplestreams",
                "server": "https://cloud-images.ubuntu.com/releases",
                "alias": identifier,
            }
        return {
            "type": "image",
            "protocol": "simplestreams",
            "server": "https://images.lxd.canonical.com",
            "alias": f"{remote}:{identifier}" if remote != "images" else identifier,
        }
    return {"type": "image", "alias": ref}


def _first_mac(state: dict[str, Any]) -> str | None:
    for iface, details in (state.get("network") or {}).items():
        if iface == "lo":
            continue
        hw = details.get("hwaddr")
        if hw:
            return hw
    return None
