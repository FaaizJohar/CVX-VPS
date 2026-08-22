"""Minimal LXD client over the local unix socket.

Uses the LXD REST API directly (no pylxd dependency). Only the operations
the control plane can request are implemented.
"""

import asyncio
import ipaddress
from pathlib import Path
from typing import Any

import httpx

LXD_SOCKET_CANDIDATES = [
    "/var/lib/lxd/unix.socket",          # apt/deb
    "/var/snap/lxd/common/lxd/unix.socket",  # snap
]


class LXDError(Exception):
    """LXD API error carrying the HTTP status code."""

    def __init__(self, status: int, message: str) -> None:
        self.status = status
        self.message = message
        super().__init__(f"LXD error {status}: {message}")


def find_lxd_socket() -> str | None:
    for p in LXD_SOCKET_CANDIDATES:
        if Path(p).exists():
            return p
    return None


class LXDClient:
    def __init__(self, socket_path: str | None = None) -> None:
        self.socket_path = socket_path or find_lxd_socket()
        if self.socket_path is None:
            raise RuntimeError("LXD unix socket not found. Is LXD installed?")
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
        params = {"project": "default"}
        if wait:
            params["wait"] = "60"
        resp = await self._client.request(
            method, path, json=json_body, params=params
        )
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

    # --- server info ---

    async def server_info(self) -> dict[str, Any]:
        data = await self._request("GET", "/1.0")
        env = data.get("metadata", {}).get("environment", {})
        return {
            "lxd_version": env.get("server_version"),
            "os_name": env.get("server_os") or env.get("distribution"),
            "os_version": env.get("server_release") or env.get("kernel_architecture"),
            "kernel_version": env.get("kernel_version"),
            "architecture": env.get("kernel_architecture"),
            "storage_drivers": env.get("storage_supported_drivers", []),
        }

    # --- instances ---

    async def create_instance(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = payload["name"]
        devices: dict[str, Any] = {}
        disk = payload.get("disk") or {}
        root: dict[str, Any] = {"path": "/", "pool": "default", "type": "disk"}
        if disk.get("size"):
            root["size"] = disk["size"]
        devices["root"] = root

        net = payload.get("network") or "lxdbr0"
        eth0: dict[str, Any] = {"name": "eth0", "nictype": "bridged", "parent": net, "type": "nic"}
        if payload.get("ipv4"):
            eth0["ipv4.address"] = payload["ipv4"]
        if payload.get("ipv6"):
            eth0["ipv6.address"] = payload["ipv6"]
        devices["eth0"] = eth0

        body = {
            "name": name,
            "source": _image_source(payload.get("image", "")),
            "config": payload.get("config", {}),
            "devices": devices,
            "instance_type": "container",
        }
        await self._request("POST", "/1.0/instances", body)
        await self.start_instance(name)
        info = await self.get_instance(name)
        # Apply DNS inside the instance when requested.
        dns = (payload.get("config", {}).get("user.cvx_dns") or "").split()
        if dns:
            await self.apply_dns(name, dns)
        return info

    async def apply_dns(self, name: str, dns_servers: list[str]) -> None:
        # Defense in depth: re-validate upstream-supplied values before they
        # reach any command construction.
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

    @staticmethod
    def _parse_image(image_ref: str) -> dict[str, Any]:
        if ":" in image_ref:
            remote, identifier = image_ref.split(":", 1)
            return {"type": "image", "protocol": "simplestreams", "server": f"https://{remote}.images.lxd.canonical.com" if remote == "images" else remote, "alias": identifier}
        return {"type": "image", "alias": image_ref}

    async def get_instance(self, name: str) -> dict[str, Any] | None:
        try:
            data = await self._request("GET", f"/1.0/instances/{name}", wait=False)
        except LXDError as e:
            if e.status == 404:
                return None
            raise
        md = data.get("metadata", {})
        status_code = md.get("status_code")
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
        data = await self._request("GET", f"/1.0/instances/{name}/state", wait=False)
        return data.get("metadata", {})

    async def start_instance(self, name: str) -> None:
        await self._request("PUT", f"/1.0/instances/{name}/state", {"action": "start"})

    async def stop_instance(self, name: str, timeout: int = 30, force: bool = False) -> None:
        await self._request(
            "PUT",
            f"/1.0/instances/{name}/state",
            {"action": "stop", "timeout": timeout, "force": force},
        )

    async def restart_instance(self, name: str, timeout: int = 30) -> None:
        await self._request(
            "PUT", f"/1.0/instances/{name}/state",
            {"action": "restart", "timeout": timeout},
        )

    async def delete_instance(self, name: str) -> None:
        # Delete snapshots explicitly first: some storage drivers refuse to
        # remove an instance that still has snapshots.
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
                continue  # best effort; instance delete below is authoritative
        try:
            await self.stop_instance(name, timeout=15)
        except Exception:
            pass
        await self._request("DELETE", f"/1.0/instances/{name}")

    async def patch_config(self, name: str, config: dict[str, str]) -> None:
        await self._request("PATCH", f"/1.0/instances/{name}", {"config": config})

    async def list_instances(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/1.0/instances", wait=False)
        urls = data.get("metadata", [])
        names = [u.rsplit("/", 1)[-1] for u in urls]
        out = []
        for n in names:
            inst = await self.get_instance(n)
            if inst is not None:
                out.append({"name": inst["name"], "status": inst["status"]})
        return out

    # --- metrics ---

    async def instance_metrics(self, name: str) -> dict[str, Any]:
        state = await self.get_state(name)
        cpu = state.get("cpu", {}) or {}
        memory = state.get("memory", {}) or {}
        disk = (state.get("disk") or {}).get("root", {}) or {}
        net_rx = sum((n or {}).get("bytes_received", 0) for n in (state.get("network") or {}).values())
        net_tx = sum((n or {}).get("bytes_sent", 0) for n in (state.get("network") or {}).values())
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

    async def create_snapshot(self, name: str, snap_name: str, stateful: bool = False) -> dict[str, Any]:
        data = await self._request(
            "POST", f"/1.0/instances/{name}/snapshots",
            {"name": snap_name, "stateful": stateful},
        )
        size = None
        try:
            snap = await self._request(
                "GET", f"/1.0/instances/{name}/snapshots/{snap_name}", wait=False
            )
            md = snap.get("metadata", {})
            size = int(md.get("size") or 0) or None
            created = md.get("created_at")
        except Exception:
            created = None
        return {"uuid": f"{name}/{snap_name}", "size": size, "created_at": created}

    async def list_snapshots(self, name: str) -> list[dict[str, Any]]:
        data = await self._request("GET", f"/1.0/instances/{name}/snapshots", wait=False)
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
            "POST", f"/1.0/instances/{name}/snapshots/{snap_name}",
            {"name": new_name},
        )

    async def restore_snapshot(self, name: str, snap_name: str) -> None:
        await self._request(
            "PUT", f"/1.0/instances/{name}/snapshots/{snap_name}",
            {"restore": True},
        )

    async def create_backup(self, name: str, backup_name: str, optimized: bool = True) -> dict[str, Any]:
        await self._request(
            "POST", f"/1.0/instances/{name}/backups",
            {"name": backup_name, "instance_only": False, "optimized_storage": optimized},
        )
        info = await self._request(
            "GET", f"/1.0/instances/{name}/backups/{backup_name}", wait=False
        )
        md = info.get("metadata", {})
        path = f"/var/snap/lxd/common/lxd/backups/{backup_name}" if Path("/var/snap/lxd").exists() else f"/var/lib/lxd/backups/{backup_name}"
        return {
            "size": int(md.get("size") or 0) or None,
            "path": path,
            "checksum": None,
        }

    async def delete_backup(self, backup_name: str) -> None:
        # Backups are per-instance in LXD; scan instances is expensive — the
        # control plane always names backups uniquely, so try direct lookup.
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
        raise RuntimeError(f"Backup {backup_name} not found on any instance")

    # --- exec (restricted internal use only) ---

    async def exec_command(self, name: str, command: list[str]) -> tuple[int, str]:
        """Execute a fixed command inside an instance. Never exposed via API."""
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


def _image_source(ref: str) -> dict[str, Any]:
    if ":" in ref:
        remote, identifier = ref.split(":", 1)
        if remote == "ubuntu":
            return {"type": "image", "protocol": "simplestreams", "server": "https://cloud-images.ubuntu.com/releases", "alias": identifier}
        return {"type": "image", "protocol": "simplestreams", "server": "https://images.lxd.canonical.com", "alias": f"{remote}:{identifier}" if remote != "images" else identifier}
    return {"type": "image", "alias": ref}


def _first_mac(state: dict[str, Any]) -> str | None:
    for iface, details in (state.get("network") or {}).items():
        if iface == "lo":
            continue
        hw = details.get("hwaddr")
        if hw:
            return hw
    return None
