import enum
import uuid
from typing import Any

from sqlalchemy import JSON, Boolean, Float, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Image(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Admin-managed OS image catalog. The create-VPS wizard lists only enabled images."""

    __tablename__ = "images"

    alias: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    os_family: Mapped[str] = mapped_column(String(48), nullable=False)  # ubuntu/debian/...
    version: Mapped[str] = mapped_column(String(48), nullable=False)
    architecture: Mapped[str] = mapped_column(String(32), default="amd64", nullable=False)

    # Where the image comes from in provider terms (e.g. LXD remote alias/image fingerprint)
    source_type: Mapped[str] = mapped_column(String(24), default="remote", nullable=False)
    source_remote: Mapped[str] = mapped_column(String(64), default="ubuntu", nullable=False)
    source_identifier: Mapped[str] = mapped_column(String(255), nullable=False)

    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    size_mb: Mapped[int | None] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    min_cpu: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    min_ram_mb: Mapped[int] = mapped_column(Integer, default=256, nullable=False)
    min_disk_gb: Mapped[int] = mapped_column(Integer, default=5, nullable=False)

    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


__all__ = ["Image"]
