"""Admin dashboard aggregates — all values computed from real data."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps.auth import AdminDep, DbDep
from app.models import (
    Node,
    NodeStatus,
    SecurityEvent,
    User,
    VPS,
    VPSStatus,
)
from app.services.node_service import NodeService

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/dashboard")
async def dashboard(_admin: AdminDep, db: DbDep) -> dict:
    now = datetime.now(UTC)

    total_vps = (
        await db.execute(select(func.count(VPS.id)).where(VPS.status != VPSStatus.DELETED))
    ).scalar_one()
    running_vps = (
        await db.execute(select(func.count(VPS.id)).where(VPS.status == VPSStatus.RUNNING))
    ).scalar_one()

    nodes = (
        await db.execute(select(Node).where(Node.status != NodeStatus.REMOVED))
    ).scalars().all()
    nodes_online = sum(1 for n in nodes if NodeService.effective_status(n) == "online")

    cpu_allocated = (
        await db.execute(
            select(func.coalesce(func.sum(VPS.cpu_limit), 0)).where(
                VPS.status.notin_([VPSStatus.DELETED])
            )
        )
    ).scalar_one()
    ram_allocated_mb = (
        await db.execute(
            select(func.coalesce(func.sum(VPS.ram_mb), 0)).where(
                VPS.status.notin_([VPSStatus.DELETED])
            )
        )
    ).scalar_one()

    node_cpu_total = sum(n.cpu_cores or 0 for n in nodes)
    node_ram_total_mb = sum(n.ram_total_mb or 0 for n in nodes)
    storage_used_gb = sum(n.storage_used_gb or 0 for n in nodes)
    storage_total_gb = sum(n.storage_total_gb or 0 for n in nodes)

    recent_events = (
        await db.execute(
            select(SecurityEvent)
            .where(SecurityEvent.created_at >= now - timedelta(days=7))
            .order_by(SecurityEvent.created_at.desc())
            .limit(10)
        )
    ).scalars().all()

    return {
        "vps": {
            "total": total_vps,
            "running": running_vps,
        },
        "nodes": {
            "total": len(nodes),
            "online": nodes_online,
            "items": [
                {
                    "id": str(n.id),
                    "name": n.name,
                    "location": n.location,
                    "status": NodeService.effective_status(n),
                    "cpu_percent": n.cpu_percent,
                    "ram_used_mb": n.ram_used_mb,
                    "ram_total_mb": n.ram_total_mb,
                }
                for n in nodes
            ],
        },
        "allocation": {
            "cpu_allocated": int(cpu_allocated),
            "cpu_capacity": node_cpu_total,
            "ram_allocated_mb": int(ram_allocated_mb),
            "ram_capacity_mb": node_ram_total_mb,
            "storage_used_gb": round(storage_used_gb, 1),
            "storage_total_gb": round(storage_total_gb, 1),
        },
        "security_alerts": [
            {
                "id": str(e.id),
                "severity": e.severity.value if hasattr(e.severity, "value") else e.severity,
                "category": e.category,
                "message": e.message,
                "created_at": e.created_at.isoformat(),
            }
            for e in recent_events
        ],
    }


@router.get("/stats/users")
async def user_stats(_admin: AdminDep, db: DbDep) -> dict:
    total = (await db.execute(select(func.count(User.id)))).scalar_one()
    active = (
        await db.execute(select(func.count(User.id)).where(User.status == "active"))
    ).scalar_one()
    return {"total": total, "active": active}
