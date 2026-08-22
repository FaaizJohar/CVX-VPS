import ipaddress
import os
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.schemas.user import ORMModel

NODE_STATUSES = {"pending", "online", "offline", "maintenance", "disabled", "removed"}


def _allow_private_node_ips() -> bool:
    return os.getenv("CVX_ALLOW_PRIVATE_NODE_IPS", "false").lower() in ("1", "true", "yes")


def validate_public_ip(value: str) -> str:
    """Reject loopback/link-local/RFC1918 targets unless explicitly allowed.

    Node addresses are used by the control plane to reach agents; accepting
    internal ranges turns admin accounts into an SSRF pivot.
    """
    try:
        addr = ipaddress.ip_address(value)
    except ValueError as e:
        raise ValueError("public_ip must be a valid IPv4 or IPv6 address") from e
    if not _allow_private_node_ips() and not addr.is_global:
        raise ValueError(
            "public_ip must be a public address "
            "(set CVX_ALLOW_PRIVATE_NODE_IPS=true for lab deployments)"
        )
    return value


class NodeCreate(BaseModel):
    name: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
    location: str = Field(min_length=2, max_length=120)
    hostname: str = Field(min_length=1, max_length=255)
    public_ip: str = Field(min_length=3, max_length=64)
    description: str = Field(default="", max_length=2000)

    @field_validator("public_ip")
    @classmethod
    def validate_ip(cls, v: str) -> str:
        return validate_public_ip(v)


class NodeOut(ORMModel):
    id: uuid.UUID
    name: str
    location: str
    hostname: str
    public_ip: str
    description: str
    status: str
    kind: str = "agent"  # "agent" | "local"
    agent_version: str | None
    lxd_version: str | None
    os_name: str | None
    os_version: str | None
    architecture: str | None
    cpu_model: str | None
    cpu_cores: int | None
    ram_total_mb: int | None
    storage_total_gb: float | None
    storage_driver: str | None
    cpu_percent: float | None
    ram_used_mb: int | None
    storage_used_gb: float | None
    load1: float | None
    uptime_seconds: int | None
    enrolled_at: datetime | None
    last_heartbeat_at: datetime | None
    created_at: datetime


class NodeEnrollmentTokenOut(BaseModel):
    node_id: uuid.UUID
    token: str
    expires_at: datetime
    install_command: str


class AgentHello(BaseModel):
    """Facts reported by the agent during enrollment."""

    agent_version: str = Field(min_length=1, max_length=64)
    hostname: str = Field(min_length=1, max_length=255)
    os_name: str = Field(max_length=64)
    os_version: str = Field(max_length=128)
    kernel_version: str = Field(max_length=128)
    architecture: str = Field(max_length=32)
    lxd_version: str | None = Field(default=None, max_length=32)
    cpu_model: str | None = Field(default=None, max_length=255)
    cpu_cores: int | None = Field(default=None, ge=1, le=16384)
    ram_total_mb: int | None = Field(default=None, ge=64, le=33_554_432)  # ≤ 32 TiB
    storage_total_gb: float | None = Field(default=None, ge=1, le=33_554_432)
    storage_driver: str | None = Field(default=None, max_length=32)


class EnrollRequest(AgentHello):
    token: str


class AgentHeartbeat(BaseModel):
    agent_version: str = Field(min_length=1, max_length=64)
    lxd_version: str | None = Field(default=None, max_length=32)
    cpu_percent: float | None = Field(default=None, ge=0, le=100)
    ram_used_mb: int | None = Field(default=None, ge=0, le=33_554_432)
    ram_total_mb: int | None = Field(default=None, ge=0, le=33_554_432)
    storage_used_gb: float | None = Field(default=None, ge=0, le=33_554_432)
    storage_total_gb: float | None = Field(default=None, ge=0, le=33_554_432)
    load1: float | None = Field(default=None, ge=0, le=100_000)
    uptime_seconds: int | None = Field(default=None, ge=0, le=2_147_483_647)
    instances: list[dict[str, Any]] = Field(default_factory=list, max_length=10_000)

    @field_validator("instances")
    @classmethod
    def validate_instances(cls, v: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for item in v:
            name = item.get("name")
            if not isinstance(name, str) or not name or len(name) > 128:
                raise ValueError("each instance needs a 'name' string of 1-128 chars")
            status = item.get("status")
            if status is not None and (not isinstance(status, str) or len(status) > 32):
                raise ValueError("instance 'status' must be a short string")
        return v
