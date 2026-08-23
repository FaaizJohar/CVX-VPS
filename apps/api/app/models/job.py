"""Asynchronous provisioning jobs.

VPS creation is queued: the API returns a job id immediately (202) while a
bounded-concurrency worker performs the actual provider call in the
background. Job state is persisted so progress survives restarts and can be
polled or streamed to the frontend.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ProvisioningJob(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "provisioning_jobs"

    kind: Mapped[str] = mapped_column(String(32), default="vps_create", nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        String(16), default=JobStatus.QUEUED, nullable=False, index=True
    )
    stage: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)

    vps_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), ForeignKey("vps.id", ondelete="SET NULL"), index=True
    )
    node_id: Mapped[uuid.UUID | None] = mapped_column(Uuid())
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(), index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (Index("ix_jobs_status_created", "status", "created_at"),)


__all__ = ["JobStatus", "ProvisioningJob"]
