"""LXD provider — implements ComputeProvider on top of the CVX Node Agent.

The agent owns the LXD unix socket; this provider only speaks the CVX agent
protocol. LXD-specific knowledge lives here and in the agent, nowhere else.
"""

import base64
import json
from typing import Any

from app.providers.agent_client import AgentClient
from app.providers.base import (
    ComputeProvider,
    ConsoleTarget,
    InstanceSpec,
    InstanceState,
)


def build_cloud_init_user_data(
    *,
    hostname: str | None,
    ssh_keys: list[str] | None,
    root_password: str | None,
) -> str:
    """Build cloud-init user-data for a new instance.

    Returns "" when there is nothing to configure (keeps LXD config clean).
    Output is base64-encoded JSON so values survive agent transport verbatim
    and are never shell-interpolated anywhere.
    """
    cfg: dict[str, Any] = {}
    if hostname:
        cfg["hostname"] = hostname
        cfg["fqdn"] = hostname
        cfg["manage_etc_hosts"] = True
    if ssh_keys:
        # Only well-formed "ssh-<type> <b64> [comment]" lines are accepted upstream;
        # here they land verbatim in ssh_authorized_keys (never shell-interpolated).
        cfg["ssh_authorized_keys"] = list(ssh_keys)
        cfg["packages"] = ["openssh-server"]
        cfg["package_update"] = True
    if root_password:
        cfg["chpasswd"] = {
            "expire": False,
            "users": [{"name": "root", "password": root_password, "type": "text"}],
        }
    if not cfg:
        return ""
    return base64.b64encode(json.dumps(cfg).encode()).decode()


class LXDProvider(ComputeProvider):
    def __init__(self, client: AgentClient) -> None:
        self.client = client

    async def ping(self) -> dict[str, Any]:
        return await self.client.get("/v1/info")

    async def create_instance(self, spec: InstanceSpec) -> InstanceState:
        payload = {
            "name": spec.name,
            "image": spec.image_source,
            "config": self._build_config(spec),
            "disk": {"size": f"{spec.disk_gb}GiB"},
            "network": spec.network_name,
            "ipv4": spec.ipv4,
            "ipv6": spec.ipv6,
        }
        data = await self.client.post("/v1/instances", json=payload)
        return self._to_state(data)

    @staticmethod
    def _build_config(spec: InstanceSpec) -> dict[str, str]:
        config: dict[str, str] = {
            "limits.cpu": str(spec.cpu_limit),
            "limits.memory": f"{spec.ram_mb}MiB",
            "limits.processes": str(spec.process_limit),
        }
        if spec.swap_mb > 0:
            config["limits.memory.swap"] = "true"
        else:
            config["limits.memory.swap"] = "false"
        if spec.hostname:
            config["user.cvx_hostname"] = spec.hostname
        if spec.dns_servers:
            config["user.cvx_dns"] = " ".join(spec.dns_servers)
        user_data = build_cloud_init_user_data(
            hostname=spec.hostname or None,
            ssh_keys=spec.ssh_keys or None,
            root_password=spec.root_password,
        )
        if user_data:
            config["user.user-data"] = user_data
        return config

    @staticmethod
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

    async def get_instance(self, name: str) -> InstanceState | None:
        try:
            data = await self.client.get(f"/v1/instances/{name}")
        except Exception:
            return None
        if data is None:
            return None
        return self._to_state(data)

    async def delete_instance(self, name: str) -> None:
        await self.client.delete(f"/v1/instances/{name}")

    async def start(self, name: str) -> dict[str, Any]:
        return await self.client.post(f"/v1/instances/{name}/start")

    async def stop(self, name: str, timeout: int = 30) -> dict[str, Any]:
        return await self.client.post(
            f"/v1/instances/{name}/stop", json={"timeout": timeout, "force": False}
        )

    async def restart(self, name: str, timeout: int = 30) -> dict[str, Any]:
        return await self.client.post(
            f"/v1/instances/{name}/restart", json={"timeout": timeout, "force": False}
        )

    async def shutdown(self, name: str, timeout: int = 120) -> dict[str, Any]:
        return await self.client.post(
            f"/v1/instances/{name}/shutdown", json={"timeout": timeout}
        )

    async def set_config(self, name: str, config: dict[str, str]) -> dict[str, Any]:
        return await self.client.patch(f"/v1/instances/{name}/config", json={"config": config})

    async def instance_metrics(self, name: str) -> dict[str, Any]:
        return await self.client.get(f"/v1/instances/{name}/metrics")

    # --- Snapshots ---

    async def create_snapshot(
        self, name: str, snapshot_name: str, stateful: bool = False
    ) -> dict[str, Any]:
        return await self.client.post(
            f"/v1/instances/{name}/snapshots",
            json={"name": snapshot_name, "stateful": stateful},
        )

    async def delete_snapshot(self, name: str, snapshot_name: str) -> None:
        await self.client.delete(f"/v1/instances/{name}/snapshots/{snapshot_name}")

    async def rename_snapshot(self, name: str, snapshot_name: str, new_name: str) -> None:
        await self.client.post(
            f"/v1/instances/{name}/snapshots/{snapshot_name}/rename",
            json={"name": new_name},
        )

    async def restore_snapshot(self, name: str, snapshot_name: str) -> dict[str, Any]:
        return await self.client.post(
            f"/v1/instances/{name}/snapshots/{snapshot_name}/restore"
        )

    async def list_snapshots(self, name: str) -> list[dict[str, Any]]:
        data = await self.client.get(f"/v1/instances/{name}/snapshots")
        return list(data.get("snapshots", []))

    # --- Backups ---

    async def create_backup(
        self, name: str, backup_name: str, optimized_storage: bool = True
    ) -> dict[str, Any]:
        return await self.client.post(
            f"/v1/instances/{name}/backups",
            json={"name": backup_name, "optimized_storage": optimized_storage},
        )

    async def delete_backup(self, backup_name: str) -> None:
        await self.client.delete(f"/v1/backups/{backup_name}")

    async def restore_backup(self, name: str, backup_path: str) -> dict[str, Any]:
        return await self.client.post(
            f"/v1/instances/{name}/restore-backup",
            json={"backup_path": backup_path},
        )

    def console_ws_url(self, name: str) -> str:
        return self.client.ws_url(f"/v1/instances/{name}/console")

    async def console_target(self, name: str, cols: int, rows: int) -> ConsoleTarget:
        return ConsoleTarget(kind="agent", url=self.console_ws_url(name))
