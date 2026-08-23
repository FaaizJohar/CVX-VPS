"""Provisioning job status endpoints (polling + SSE live stream)."""

import asyncio
import json
import uuid

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.deps.auth import ActorDep, DbDep
from app.core.errors import NotFoundError
from app.models import ProvisioningJob, User, UserRole, VPS
from app.schemas.job import JobOut
from app.services.vps_service import VPSService

router = APIRouter(prefix="/jobs", tags=["jobs"])

_SSE_POLL_INTERVAL = 0.6
_SSE_MAX_LIFETIME = 30 * 60


async def _get_job_checked(
    db, *, job_id: uuid.UUID, user: User
) -> ProvisioningJob:
    from sqlalchemy.ext.asyncio import AsyncSession

    assert isinstance(db, AsyncSession)
    job = await db.get(ProvisioningJob, job_id)
    if job is None:
        raise NotFoundError("Job not found.")
    if user.role not in (UserRole.OWNER, UserRole.ADMIN):
        if job.user_id != user.id:
            # Non-owners must not learn that other users' jobs exist.
            raise NotFoundError("Job not found.")
        if job.vps_id is not None:
            vps = await db.get(VPS, job.vps_id)
            if vps is not None and not VPSService.can_access(user, vps):
                raise NotFoundError("Job not found.")
    return job


@router.get("/by-vps/{vps_id}", response_model=JobOut | None)
async def get_job_for_vps(vps_id: uuid.UUID, actor: ActorDep, db: DbDep) -> JobOut | None:
    """Latest non-terminal provisioning job for a VPS (None when finished)."""
    from sqlalchemy.ext.asyncio import AsyncSession

    assert isinstance(db, AsyncSession)
    vps = await VPSService.get_vps_checked(db, vps_id=vps_id, user=actor.user)
    job = (
        await db.execute(
            select(ProvisioningJob)
            .where(
                ProvisioningJob.vps_id == vps.id,
                ProvisioningJob.status.in_(["queued", "running"]),
            )
            .order_by(ProvisioningJob.created_at.desc())
            .limit(1)
        )
    ).scalars().first()
    return JobOut.model_validate(job) if job else None


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: uuid.UUID, actor: ActorDep, db: DbDep) -> JobOut:
    job = await _get_job_checked(db, job_id=job_id, user=actor.user)
    return JobOut.model_validate(job)


@router.get("/{job_id}/events")
async def stream_job(job_id: uuid.UUID, actor: ActorDep, db: DbDep) -> StreamingResponse:
    """Server-Sent Events stream of job progress; closes on terminal state."""
    await _get_job_checked(db, job_id=job_id, user=actor.user)

    from app.db.session import get_session_factory

    async def event_stream():
        last_payload: str | None = None
        elapsed = 0.0
        yield ": connected\n\n"
        factory = get_session_factory()
        while elapsed < _SSE_MAX_LIFETIME:
            # Fresh session per poll: the request session's identity map would
            # return cached objects and never observe worker updates.
            async with factory() as poll_db:
                try:
                    job = await _get_job_checked(poll_db, job_id=job_id, user=actor.user)
                except NotFoundError:
                    break
                payload = json.dumps(
                    {
                        "id": str(job.id),
                        "status": (
                            job.status.value if hasattr(job.status, "value") else str(job.status)
                        ),
                        "stage": job.stage,
                        "progress": job.progress,
                        "error": job.error,
                        "vps_id": str(job.vps_id) if job.vps_id else None,
                    }
                )
                status = (
                    job.status.value if hasattr(job.status, "value") else str(job.status)
                )
            if payload != last_payload:
                last_payload = payload
                yield f"data: {payload}\n\n"
            if status in ("succeeded", "failed"):
                break
            await asyncio.sleep(_SSE_POLL_INTERVAL)
            elapsed += _SSE_POLL_INTERVAL

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
