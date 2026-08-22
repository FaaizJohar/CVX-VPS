import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class VPSMetricSample(Base):
    __tablename__ = "vps_metric_samples"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    vps_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    cpu_percent: Mapped[float | None]
    mem_used_mb: Mapped[float | None]
    mem_total_mb: Mapped[float | None]
    swap_used_mb: Mapped[float | None]
    disk_used_gb: Mapped[float | None]
    disk_total_gb: Mapped[float | None]
    disk_read_bps: Mapped[float | None]
    disk_write_bps: Mapped[float | None]
    net_rx_bps: Mapped[float | None]
    net_tx_bps: Mapped[float | None]

    __table_args__ = (
        Index("ix_vpsmetrics_vps_ts", "vps_id", "ts"),
    )


class NodeMetricSample(Base):
    __tablename__ = "node_metric_samples"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    node_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    cpu_percent: Mapped[float | None]
    mem_used_mb: Mapped[float | None]
    mem_total_mb: Mapped[float | None]
    storage_used_gb: Mapped[float | None]
    storage_total_gb: Mapped[float | None]
    net_rx_bps: Mapped[float | None]
    net_tx_bps: Mapped[float | None]
    load1: Mapped[float | None]
    uptime_seconds: Mapped[int | None]

    __table_args__ = (
        Index("ix_nodemetrics_node_ts", "node_id", "ts"),
    )


__all__ = ["VPSMetricSample", "NodeMetricSample"]
