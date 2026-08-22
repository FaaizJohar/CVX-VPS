import time
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query

from app.api.deps.auth import ActorDep, DbDep
from app.models import NodeMetricSample, VPSMetricSample
from app.services.node_service import NodeService
from app.services.vps_service import VPSService

router = APIRouter(prefix="/metrics", tags=["metrics"])

RANGES = {
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


def _since(range_key: str) -> datetime:
    return datetime.now(UTC) - RANGES.get(range_key, RANGES["1h"])


def _downsample(rows: list[VPSMetricSample] | list[NodeMetricSample], max_points: int = 180) -> list:
    if len(rows) <= max_points:
        return rows
    step = len(rows) / max_points
    return [rows[int(i * step)] for i in range(max_points)]


@router.get("/vps/{vps_id}")
async def vps_metrics(
    vps_id: uuid.UUID,
    actor: ActorDep,
    db: DbDep,
    range: str = Query(default="1h"),
) -> dict:
    from sqlalchemy import select

    await VPSService.get_vps_checked(db, vps_id=vps_id, user=actor.user)
    since = _since(range)
    rows = (
        await db.execute(
            select(VPSMetricSample)
            .where(VPSMetricSample.vps_id == vps_id, VPSMetricSample.ts >= since)
            .order_by(VPSMetricSample.ts.asc())
        )
    ).scalars().all()
    samples = _downsample(list(rows))
    return {
        "range": range,
        "series": [
            {
                "ts": s.ts.isoformat(),
                "cpu_percent": s.cpu_percent,
                "mem_used_mb": s.mem_used_mb,
                "mem_total_mb": s.mem_total_mb,
                "swap_used_mb": s.swap_used_mb,
                "disk_used_gb": s.disk_used_gb,
                "disk_total_gb": s.disk_total_gb,
                "disk_read_bps": s.disk_read_bps,
                "disk_write_bps": s.disk_write_bps,
                "net_rx_bps": s.net_rx_bps,
                "net_tx_bps": s.net_tx_bps,
            }
            for s in samples
        ],
    }


@router.get("/nodes/{node_id}")
async def node_metrics(
    node_id: uuid.UUID,
    actor: ActorDep,
    db: DbDep,
    range: str = Query(default="1h"),
) -> dict:
    from sqlalchemy import select

    node = await NodeService.get_node(db, node_id)
    since = _since(range)
    rows = (
        await db.execute(
            select(NodeMetricSample)
            .where(NodeMetricSample.node_id == node.id, NodeMetricSample.ts >= since)
            .order_by(NodeMetricSample.ts.asc())
        )
    ).scalars().all()
    samples = _downsample(list(rows))
    return {
        "range": range,
        "series": [
            {
                "ts": s.ts.isoformat(),
                "cpu_percent": s.cpu_percent,
                "mem_used_mb": s.mem_used_mb,
                "mem_total_mb": s.mem_total_mb,
                "storage_used_gb": s.storage_used_gb,
                "storage_total_gb": s.storage_total_gb,
                "net_rx_bps": s.net_rx_bps,
                "net_tx_bps": s.net_tx_bps,
                "load1": s.load1,
            }
            for s in samples
        ],
    }
