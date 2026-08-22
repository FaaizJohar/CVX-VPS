import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class VPSStatus(str, enum.Enum):
    CREATING = "creating"
    PROVISIONING = "provisioning"
    RUNNING = "running"
    STOPPED = "stopped"
    FROZEN = "frozen"
    ERROR = "error"
    DELETING = "deleting"
    DELETED = "deleted"


class VPS(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "vps"

    node_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("nodes.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    image_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(), ForeignKey("images.id"))

    name: Mapped[str] = mapped_column(String(64), nullable=False)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    # Reference used by the provider (LXD instance name). Opaque to users.
    provider_ref: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)

    status: Mapped[VPSStatus] = mapped_column(
        String(16), default=VPSStatus.CREATING, nullable=False, index=True
    )

    # Resources
    cpu_limit: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    ram_mb: Mapped[int] = mapped_column(Integer, default=1024, nullable=False)
    swap_mb: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    disk_gb: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    process_limit: Mapped[int] = mapped_column(Integer, default=256, nullable=False)

    # Network
    ipv4: Mapped[str | None] = mapped_column(String(64))
    ipv6: Mapped[str | None] = mapped_column(String(128))
    mac_address: Mapped[str | None] = mapped_column(String(32))
    network_name: Mapped[str | None] = mapped_column(String(64))
    dns_servers: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)

    # Access
    ssh_keys: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    password_auth_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    root_password_set: Mapped[bool] = mapped_column(Boolean, default=False)

    # Security posture
    privileged: Mapped[bool] = mapped_column(Boolean, default=False)

    # Raw provider config (advanced configuration tab mirrors this)
    raw_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # "node" (deployed on an enrolled agent node) or "local" (control-plane host).
    deployment_mode: Mapped[str] = mapped_column(
        String(16), default="node", server_default="node", nullable=False
    )

    provision_error: Mapped[str | None] = mapped_column(Text)

    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    node: Mapped["Node"] = relationship(back_populates="vps_list")  # type: ignore[name-defined]  # noqa: F821

    __table_args__ = (
        Index("ix_vps_owner_status", "owner_id", "status"),
        Index("ix_vps_node_status", "node_id", "status"),
        CheckConstraint(
            "deployment_mode IN ('node', 'local')",
            name="ck_vps_deployment_mode",
        ),
    )


__all__ = ["VPS", "VPSStatus"]
