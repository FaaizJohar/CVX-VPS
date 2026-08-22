"""Audit logging helper. Never log secrets or passwords."""

import uuid as _uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models import AuditLog, LogEntry, LogSource, SecurityEvent, SecurityEventSeverity

log = get_logger("cvx.audit")

_REDACT_KEYS = {"password", "secret", "token", "credential", "key", "authorization"}


def _as_uuid(value: Any) -> _uuid.UUID | None:
    if value is None or isinstance(value, _uuid.UUID):
        return value
    try:
        return _uuid.UUID(str(value))
    except (ValueError, AttributeError):
        return None


def _redact(detail: dict[str, Any]) -> dict[str, Any]:
    def clean(d: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k, v in d.items():
            if any(r in k.lower() for r in _REDACT_KEY_FRAGMENTS):
                out[k] = "[REDACTED]"
            elif isinstance(v, dict):
                out[k] = clean(v)
            else:
                out[k] = v
        return out

    return clean(detail)


_REDACT_KEY_FRAGMENTS = ("password", "secret", "token", "credential", "key_hash")


async def record_audit(
    db: AsyncSession,
    *,
    action: str,
    actor_user_id: str | None = None,
    actor_api_key_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    node_id: str | None = None,
    vps_id: str | None = None,
    detail: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> None:
    entry = AuditLog(
        actor_user_id=_as_uuid(actor_user_id),
        actor_api_key_id=_as_uuid(actor_api_key_id),
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        node_id=_as_uuid(node_id),
        vps_id=_as_uuid(vps_id),
        detail=_redact(detail or {}),
        ip_address=ip_address,
    )
    db.add(entry)
    log.info("audit action=%s resource=%s/%s", action, resource_type, resource_id)


async def record_log(
    db: AsyncSession,
    *,
    source: LogSource,
    message: str,
    severity: str = "info",
    meta: dict[str, Any] | None = None,
    user_id: str | None = None,
    node_id: str | None = None,
    vps_id: str | None = None,
) -> None:
    db.add(
        LogEntry(
            source=source,
            severity=severity,
            message=message,
            meta=meta or {},
            user_id=_as_uuid(user_id),
            node_id=_as_uuid(node_id),
            vps_id=_as_uuid(vps_id),
        )
    )


async def record_security_event(
    db: AsyncSession,
    *,
    category: str,
    message: str,
    severity: SecurityEventSeverity = SecurityEventSeverity.INFO,
    node_id: str | None = None,
    vps_id: str | None = None,
    user_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    db.add(
        SecurityEvent(
            category=category,
            message=message,
            severity=severity,
            node_id=_as_uuid(node_id),
            vps_id=_as_uuid(vps_id),
            user_id=_as_uuid(user_id),
            detail=_redact(detail or {}),
        )
    )
