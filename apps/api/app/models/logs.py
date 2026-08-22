import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class SecurityEventSeverity(str, enum.Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AuditLog(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "audit_logs"

    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(), index=True)
    actor_api_key_id: Mapped[uuid.UUID | None] = mapped_column(Uuid())
    action: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    resource_type: Mapped[str | None] = mapped_column(String(64), index=True)
    resource_id: Mapped[str | None] = mapped_column(String(64))
    node_id: Mapped[uuid.UUID | None] = mapped_column(Uuid())
    vps_id: Mapped[uuid.UUID | None] = mapped_column(Uuid())
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, index=True
    )

    __table_args__ = (Index("ix_audit_created_action", "created_at", "action"),)


class SecurityEvent(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "security_events"

    severity: Mapped[SecurityEventSeverity] = mapped_column(
        String(16), default=SecurityEventSeverity.INFO, nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    node_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(), index=True)
    vps_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(), index=True)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, index=True
    )


class LogSource(str, enum.Enum):
    SYSTEM = "system"
    AUTH = "auth"
    NETWORK = "network"
    VPS = "vps"
    CVX = "cvx"
    SECURITY = "security"


class LogEntry(Base, UUIDPrimaryKeyMixin):
    """Unified log stream surfaced in the Logs UI."""

    __tablename__ = "log_entries"

    source: Mapped[LogSource] = mapped_column(String(16), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), default="info", nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(), index=True)
    node_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(), index=True)
    vps_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(), index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, index=True
    )

    __table_args__ = (Index("ix_logs_created_source", "created_at", "source"),)


__all__ = ["AuditLog", "SecurityEvent", "SecurityEventSeverity", "LogEntry", "LogSource"]
