import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
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


class NodeStatus(str, enum.Enum):
    PENDING = "pending"          # created, awaiting agent enrollment
    ONLINE = "online"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"
    DISABLED = "disabled"
    REMOVED = "removed"


class Node(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "nodes"

    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    location: Mapped[str] = mapped_column(String(120), nullable=False)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    public_ip: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)

    status: Mapped[NodeStatus] = mapped_column(
        String(16), default=NodeStatus.PENDING, nullable=False, index=True
    )

    # Agent identity / auth
    # credential_hash: fast verification of presented credentials.
    # credential_encrypted: AES-encrypted copy used for outbound agent calls.
    # Neither is ever stored or logged in plaintext.
    credential_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    credential_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    enrolled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Discovered facts (reported by agent)
    agent_version: Mapped[str | None] = mapped_column(String(32))
    lxd_version: Mapped[str | None] = mapped_column(String(32))
    os_name: Mapped[str | None] = mapped_column(String(120))
    os_version: Mapped[str | None] = mapped_column(String(120))
    kernel_version: Mapped[str | None] = mapped_column(String(120))
    architecture: Mapped[str | None] = mapped_column(String(32))
    cpu_model: Mapped[str | None] = mapped_column(String(255))
    cpu_cores: Mapped[int | None] = mapped_column(Integer)
    ram_total_mb: Mapped[int | None] = mapped_column(BigInteger)
    storage_total_gb: Mapped[float | None] = mapped_column(Float)
    storage_driver: Mapped[str | None] = mapped_column(String(32))

    # Live load (latest heartbeat)
    cpu_percent: Mapped[float | None] = mapped_column(Float)
    ram_used_mb: Mapped[int | None] = mapped_column(BigInteger)
    storage_used_gb: Mapped[float | None] = mapped_column(Float)
    load1: Mapped[float | None] = mapped_column(Float)
    uptime_seconds: Mapped[int | None] = mapped_column(BigInteger)

    vps_list: Mapped[list["VPS"]] = relationship(back_populates="node")  # type: ignore[name-defined]  # noqa: F821


class EnrollmentToken(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "enrollment_tokens"

    node_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    @property
    def is_usable(self) -> bool:
        from app.core.security import ensure_aware, utcnow

        return (
            self.used_at is None
            and self.revoked_at is None
            and ensure_aware(self.expires_at) > utcnow()
        )


__all__ = ["Node", "NodeStatus", "EnrollmentToken"]

