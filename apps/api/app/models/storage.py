import uuid
from typing import Any

from sqlalchemy import JSON, Boolean, Float, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class StoragePool(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "storage_pools"

    node_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    driver: Mapped[str] = mapped_column(String(32), nullable=False)  # zfs/btrfs/dir/lvm
    total_gb: Mapped[float | None] = mapped_column(Float)
    used_gb: Mapped[float | None] = mapped_column(Float)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class Volume(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "volumes"

    node_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vps_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), ForeignKey("vps.id", ondelete="CASCADE"), index=True
    )
    pool_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(), ForeignKey("storage_pools.id"))
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    volume_type: Mapped[str] = mapped_column(String(24), default="custom")
    size_gb: Mapped[float | None] = mapped_column(Float)
    used_gb: Mapped[float | None] = mapped_column(Float)
    mount_point: Mapped[str | None] = mapped_column(String(255))
    read_only: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


__all__ = ["StoragePool", "Volume"]
