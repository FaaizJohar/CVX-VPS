import uuid
from datetime import datetime

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.deps.auth import ActorDep, AdminDep, DbDep
from app.models import AuditLog, LogEntry, LogSource, SecurityEvent

router = APIRouter(prefix="/logs", tags=["logs"])


def _parse_dt(v: str | None) -> datetime | None:
    if not v:
        return None
    return datetime.fromisoformat(v)


@router.get("")
async def query_logs(
    actor: ActorDep,
    db: DbDep,
    source: LogSource | None = None,
    severity: str | None = None,
    vps_id: uuid.UUID | None = None,
    node_id: uuid.UUID | None = None,
    search: str | None = None,
    since: str | None = None,
    until: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> dict:
    q = select(LogEntry)
    if source:
        q = q.where(LogEntry.source == source)
    if severity:
        q = q.where(LogEntry.severity == severity)
    if vps_id:
        q = q.where(LogEntry.vps_id == vps_id)
    if node_id:
        q = q.where(LogEntry.node_id == node_id)
    if search:
        q = q.where(LogEntry.message.ilike(f"%{search}%"))
    sd, ud = _parse_dt(since), _parse_dt(until)
    if sd:
        q = q.where(LogEntry.created_at >= sd)
    if ud:
        q = q.where(LogEntry.created_at <= ud)

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (
        await db.execute(
            q.order_by(LogEntry.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return {
        "items": [
            {
                "id": str(r.id),
                "source": r.source.value if hasattr(r.source, "value") else r.source,
                "severity": r.severity,
                "message": r.message,
                "meta": r.meta,
                "vps_id": str(r.vps_id) if r.vps_id else None,
                "node_id": str(r.node_id) if r.node_id else None,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/audit")
async def audit_logs(
    _admin: AdminDep,
    db: DbDep,
    action: str | None = None,
    actor_user_id: uuid.UUID | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> dict:
    q = select(AuditLog)
    if action:
        q = q.where(AuditLog.action == action)
    if actor_user_id:
        q = q.where(AuditLog.actor_user_id == actor_user_id)
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (
        await db.execute(
            q.order_by(AuditLog.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return {
        "items": [
            {
                "id": str(r.id),
                "action": r.action,
                "actor_user_id": str(r.actor_user_id) if r.actor_user_id else None,
                "resource_type": r.resource_type,
                "resource_id": r.resource_id,
                "detail": r.detail,
                "ip_address": r.ip_address,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/security-events")
async def security_events(
    actor: ActorDep,
    db: DbDep,
    severity: str | None = None,
    node_id: uuid.UUID | None = None,
    vps_id: uuid.UUID | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> dict:
    q = select(SecurityEvent)
    if severity:
        q = q.where(SecurityEvent.severity == severity)
    if node_id:
        q = q.where(SecurityEvent.node_id == node_id)
    if vps_id:
        q = q.where(SecurityEvent.vps_id == vps_id)
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (
        await db.execute(
            q.order_by(SecurityEvent.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return {
        "items": [
            {
                "id": str(r.id),
                "severity": r.severity.value if hasattr(r.severity, "value") else r.severity,
                "category": r.category,
                "message": r.message,
                "detail": r.detail,
                "node_id": str(r.node_id) if r.node_id else None,
                "vps_id": str(r.vps_id) if r.vps_id else None,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
