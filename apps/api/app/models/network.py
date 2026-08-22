import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class NetworkType(str, enum.Enum):
    BRIDGE = "bridge"
    MACVLAN = "macvlan"
    OVN = "ovn"
    PHYSICAL = "physical"


class Network(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "networks"

    node_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    type: Mapped[NetworkType] = mapped_column(String(16), default=NetworkType.BRIDGE)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)

    ipv4_subnet: Mapped[str | None] = mapped_column(String(64))
    ipv6_subnet: Mapped[str | None] = mapped_column(String(128))
    ipv4_gateway: Mapped[str | None] = mapped_column(String(64))
    managed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class IPStatus(str, enum.Enum):
    AVAILABLE = "available"
    RESERVED = "reserved"
    ASSIGNED = "assigned"


class IPAddress(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ip_addresses"

    node_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), ForeignKey("nodes.id", ondelete="CASCADE"), index=True
    )
    family: Mapped[int] = mapped_column(Integer, nullable=False)  # 4 or 6
    address: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    cidr: Mapped[int | None] = mapped_column(Integer)
    gateway: Mapped[str | None] = mapped_column(String(128))
    reverse_dns: Mapped[str | None] = mapped_column(String(255))

    status: Mapped[IPStatus] = mapped_column(
        String(16), default=IPStatus.AVAILABLE, nullable=False, index=True
    )
    vps_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), ForeignKey("vps.id", ondelete="SET NULL"), index=True
    )
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)


__all__ = ["Network", "NetworkType", "IPAddress", "IPStatus"]
