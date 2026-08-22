import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator
from pydantic import model_validator

from app.schemas.user import ORMModel

VALID_HOSTNAME = r"^[a-zA-Z0-9][a-zA-Z0-9.-]*$"


class VPSCreate(BaseModel):
    # Deployment target: "node" (default) requires node_id; "local" deploys on
    # the control-plane host itself and must not carry a node_id.
    deployment_mode: Literal["node", "local"] = "node"
    node_id: uuid.UUID | None = None
    image_id: uuid.UUID
    name: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
    hostname: str = Field(min_length=1, max_length=255, pattern=VALID_HOSTNAME)

    # Resources
    cpu_limit: int = Field(default=1, ge=1, le=64)
    ram_mb: int = Field(default=1024, ge=128, le=262144)
    swap_mb: int = Field(default=0, ge=0, le=65536)
    disk_gb: int = Field(default=10, ge=5, le=4096)
    process_limit: int = Field(default=256, ge=32, le=8192)

    # Network
    network_name: str | None = Field(default=None, max_length=64)
    ipv4: str | None = None
    ipv6: str | None = None
    dns_servers: list[str] = Field(default_factory=list, max_length=4)

    # Access
    ssh_keys: list[str] = Field(default_factory=list, max_length=20)
    password_auth_enabled: bool = False
    root_password: str | None = Field(default=None, max_length=128)

    @field_validator("ipv4", "ipv6")
    @classmethod
    def validate_ips(cls, v: str | None) -> str | None:
        if v is None:
            return v
        import ipaddress

        ipaddress.ip_address(v)  # raises on invalid
        return v

    @field_validator("dns_servers")
    @classmethod
    def validate_dns(cls, v: list[str]) -> list[str]:
        import ipaddress

        for s in v:
            ipaddress.ip_address(s)
        return v

    @field_validator("ssh_keys")
    @classmethod
    def validate_ssh_keys(cls, v: list[str]) -> list[str]:
        for k in v:
            keytype = k.split(" ")[0] if " " in k else ""
            if keytype not in {"ssh-rsa", "ssh-ed25519", "ecdsa-sha2-nistp256",
                               "ecdsa-sha2-nistp384", "ecdsa-sha2-nistp521"}:
                raise ValueError(f"unsupported ssh key type: {keytype!r}")
        return v

    @model_validator(mode="after")
    def validate_target(self) -> "VPSCreate":
        if self.deployment_mode == "node" and self.node_id is None:
            raise ValueError("node_id is required when deployment_mode is 'node'.")
        if self.deployment_mode == "local" and self.node_id is not None:
            raise ValueError("node_id must be omitted when deployment_mode is 'local'.")
        return self


class VPSOut(ORMModel):
    id: uuid.UUID
    node_id: uuid.UUID
    owner_id: uuid.UUID
    image_id: uuid.UUID | None = None
    name: str
    hostname: str
    status: str
    deployment_mode: str = "node"
    cpu_limit: int
    ram_mb: int
    swap_mb: int
    disk_gb: int
    process_limit: int
    ipv4: str | None
    ipv6: str | None
    mac_address: str | None
    network_name: str | None
    dns_servers: list[Any]
    ssh_keys: list[Any]
    password_auth_enabled: bool
    root_password_set: bool = False
    privileged: bool
    provision_error: str | None
    created_at: datetime
    updated_at: datetime


class VPSUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=64)
    cpu_limit: int | None = Field(default=None, ge=1, le=64)
    ram_mb: int | None = Field(default=None, ge=128, le=262144)
    swap_mb: int | None = Field(default=None, ge=0, le=65536)
    disk_gb: int | None = Field(default=None, ge=5, le=4096)
    process_limit: int | None = Field(default=None, ge=32, le=8192)
    dns_servers: list[str] | None = None


class VPSActionResponse(BaseModel):
    id: uuid.UUID
    status: str
    action: str


class RawConfigUpdate(BaseModel):
    """Advanced configuration (Configuration tab). Keys are provider config keys."""

    config: dict[str, str] = Field(max_length=200)
