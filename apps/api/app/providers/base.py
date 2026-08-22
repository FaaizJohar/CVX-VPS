"""Provider abstraction.

The control plane never talks to LXD directly; it programs nodes through
their CVX Node Agent. ComputeProvider is the seam that keeps LXD details
out of the service layer so future providers (Incus, KVM, Proxmox) can be
added without rewriting the application.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class InstanceSpec:
    name: str
    image_source: str  # provider-specific image reference
    cpu_limit: int
    ram_mb: int
    swap_mb: int
    disk_gb: int
    process_limit: int
    hostname: str
    network_name: str | None = None
    ipv4: str | None = None
    ipv6: str | None = None
    dns_servers: list[str] = field(default_factory=list)
    ssh_keys: list[str] = field(default_factory=list)
    root_password: str | None = None
    privileged: bool = False


@dataclass(slots=True)
class InstanceState:
    name: str
    status: str
    pid: int | None = None
    process_count: int | None = None
    ips: dict[str, str] = field(default_factory=dict)
    created_at: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class ComputeProvider(ABC):
    """Operations the control plane can perform on a node's compute backend."""

    @abstractmethod
    async def ping(self) -> dict[str, Any]: ...

    @abstractmethod
    async def create_instance(self, spec: InstanceSpec) -> InstanceState: ...

    @abstractmethod
    async def get_instance(self, name: str) -> InstanceState | None: ...

    @abstractmethod
    async def delete_instance(self, name: str) -> None: ...

    @abstractmethod
    async def start(self, name: str) -> dict[str, Any]: ...

    @abstractmethod
    async def stop(self, name: str, timeout: int = 30) -> dict[str, Any]: ...

    @abstractmethod
    async def restart(self, name: str, timeout: int = 30) -> dict[str, Any]: ...

    @abstractmethod
    async def shutdown(self, name: str, timeout: int = 120) -> dict[str, Any]: ...

    @abstractmethod
    async def set_config(self, name: str, config: dict[str, str]) -> dict[str, Any]: ...

    @abstractmethod
    async def instance_metrics(self, name: str) -> dict[str, Any]: ...

    # Snapshots
    @abstractmethod
    async def create_snapshot(
        self, name: str, snapshot_name: str, stateful: bool = False
    ) -> dict[str, Any]: ...

    @abstractmethod
    async def delete_snapshot(self, name: str, snapshot_name: str) -> None: ...

    @abstractmethod
    async def rename_snapshot(
        self, name: str, snapshot_name: str, new_name: str
    ) -> None: ...

    @abstractmethod
    async def restore_snapshot(self, name: str, snapshot_name: str) -> dict[str, Any]: ...

    @abstractmethod
    async def list_snapshots(self, name: str) -> list[dict[str, Any]]: ...

    # Backups
    @abstractmethod
    async def create_backup(
        self, name: str, backup_name: str, optimized_storage: bool = True
    ) -> dict[str, Any]: ...

    @abstractmethod
    async def delete_backup(self, backup_name: str) -> None: ...

    @abstractmethod
    async def restore_backup(self, name: str, backup_path: str) -> dict[str, Any]: ...

    # Console — returns a websocket URL on the agent to connect to.
    @abstractmethod
    def console_ws_url(self, name: str) -> str: ...
