"""Bounded-concurrency background worker for asynchronous provisioning.

Design notes:
- Jobs are persisted in ``provisioning_jobs``; the in-process asyncio queue is
  only a wakeup channel, never the source of truth.
- Concurrency is bounded by a semaphore so a burst of creates cannot exhaust
  the DB pool or hammer LXD with unbounded parallelism.
- The worker never blocks the event loop: provider calls are async HTTP.
- On startup, jobs left ``queued``/``running`` by a previous crash are
  re-enqueued (idempotent — provisioning is guarded by VPS status checks).
"""

import asyncio

from app.core.logging import get_logger
from app.db.session import get_session_factory
from app.models import JobStatus, ProvisioningJob

log = get_logger("cvx.provisioning")

MAX_CONCURRENT_PROVISIONS = 4
_PROVISION_TIMEOUT_SECONDS = 20 * 60


class ProvisioningWorker:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[str] = asyncio.Queue(maxsize=1000)
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_PROVISIONS)
        self._tasks: set[asyncio.Task[None]] = set()
        self._pump_task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()
        self._started = False

    # ------------------------------------------------------------- lifecycle

    def start(self) -> None:
        if self._pump_task is not None and not self._pump_task.done():
            return
        self._stopping.clear()
        self._started = True
        self._pump_task = asyncio.get_running_loop().create_task(self._pump())
        self._tasks.add(asyncio.get_running_loop().create_task(self._recover_stuck()))
        log.info("provisioning worker started (max_concurrent=%s)", MAX_CONCURRENT_PROVISIONS)

    async def stop(self) -> None:
        self._started = False
        self._stopping.set()
        for t in list(self._tasks):
            t.cancel()
        if self._pump_task is not None:
            self._pump_task.cancel()
            try:
                await self._pump_task
            except asyncio.CancelledError:
                pass
        self._pump_task = None
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    # ---------------------------------------------------------------- enqueue

    def enqueue(self, job_id: str) -> None:
        """Schedule a persisted job for execution (non-blocking).

        When the worker is not running (e.g. tests drive provisioning
        synchronously) this is a no-op — jobs remain ``queued`` until the
        worker starts and crash-recovery re-enqueues them.
        """
        if not self._started:
            return

        async def _delayed() -> None:
            # The route's transaction commits when the request dependency tears
            # down; give it a beat so the worker always sees the row.
            await asyncio.sleep(0.3)
            try:
                self._queue.put_nowait(job_id)
            except asyncio.QueueFull:
                log.error("provision queue full; job %s will be recovered on restart", job_id)

        self._tasks.add(asyncio.get_running_loop().create_task(_delayed()))

    async def _recover_stuck(self) -> None:
        """Re-enqueue jobs abandoned by a previous process (crash recovery)."""
        await asyncio.sleep(2)  # let migrations/boot settle
        from sqlalchemy import select

        factory = get_session_factory()
        async with factory() as db:
            rows = (
                await db.execute(
                    select(ProvisioningJob.id).where(
                        ProvisioningJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING])
                    )
                )
            ).scalars().all()
        for job_id in rows:
            self.enqueue(str(job_id))
        if rows:
            log.info("re-enqueued %d stuck provisioning job(s)", len(rows))

    # ------------------------------------------------------------------- pump

    async def _pump(self) -> None:
        while not self._stopping.is_set():
            job_id = await self._queue.get()
            task = asyncio.get_running_loop().create_task(self._run(job_id))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def _run(self, job_id: str) -> None:
        async with self._semaphore:
            try:
                await self._execute(job_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("provisioning job %s crashed", job_id)

    async def _wait_for_row(self, job_id: str) -> ProvisioningJob | None:
        from uuid import UUID

        factory = get_session_factory()
        for _ in range(40):  # up to ~10s
            async with factory() as db:
                row = await db.get(ProvisioningJob, UUID(job_id))
            if row is not None:
                return row
            await asyncio.sleep(0.25)
        return None

    async def _set_stage(self, job_id: str, stage: str, progress: int) -> None:
        from datetime import UTC, datetime
        from uuid import UUID

        from sqlalchemy import update

        factory = get_session_factory()
        async with factory() as db:
            await db.execute(
                update(ProvisioningJob)
                .where(ProvisioningJob.id == UUID(job_id))
                .values(stage=stage, progress=progress, updated_at=datetime.now(UTC))
                .execution_options(synchronize_session=False)
            )
            await db.commit()

    async def _finish(
        self, job_id: str, status: JobStatus, *, error: str | None = None
    ) -> None:
        from datetime import UTC, datetime
        from uuid import UUID

        from sqlalchemy import update

        factory = get_session_factory()
        async with factory() as db:
            await db.execute(
                update(ProvisioningJob)
                .where(ProvisioningJob.id == UUID(job_id))
                .values(
                    status=status,
                    stage="done" if status == JobStatus.SUCCEEDED else "failed",
                    progress=100 if status == JobStatus.SUCCEEDED else None,
                    error=error,
                    updated_at=datetime.now(UTC),
                )
                .execution_options(synchronize_session=False)
            )
            await db.commit()

    async def _execute(self, job_id: str) -> None:
        from datetime import UTC, datetime
        from uuid import UUID

        from sqlalchemy import update

        from app.services.vps_service import VPSService

        row = await self._wait_for_row(job_id)
        if row is None:
            log.error("job %s vanished before execution", job_id)
            return
        if row.status in (JobStatus.SUCCEEDED, JobStatus.FAILED):
            return

        factory = get_session_factory()
        async with factory() as db:
            claimed = await db.execute(
                update(ProvisioningJob)
                .where(
                    ProvisioningJob.id == UUID(job_id),
                    ProvisioningJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
                )
                .values(
                    status=JobStatus.RUNNING, stage="preparing", progress=10,
                    updated_at=datetime.now(UTC),
                )
                .execution_options(synchronize_session=False)
            )
            await db.commit()
            if claimed.rowcount != 1:
                return

        vps_id = row.vps_id
        if vps_id is None:
            await self._finish(job_id, JobStatus.FAILED, error="job has no target VPS")
            return

        await self._set_stage(job_id, "creating_instance", 45)
        try:
            outcome = await asyncio.wait_for(
                VPSService.provision_vps(vps_id=vps_id),
                timeout=_PROVISION_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            await VPSService.mark_provision_failed(vps_id=vps_id, error="provisioning_timeout")
            await self._finish(job_id, JobStatus.FAILED, error="Provisioning timed out.")
            return
        except Exception as e:
            await VPSService.mark_provision_failed(vps_id=vps_id, error=str(e)[:2000])
            await self._finish(job_id, JobStatus.FAILED, error="Provisioning failed on the host.")
            return

        await self._set_stage(job_id, "finalizing", 90)
        if outcome is not None:
            await self._finish(job_id, JobStatus.FAILED, error=outcome)
        else:
            await self._finish(job_id, JobStatus.SUCCEEDED)


worker = ProvisioningWorker()


def start_worker() -> None:
    worker.start()


async def stop_worker() -> None:
    await worker.stop()


def enqueue_vps_create(job_id: str) -> None:
    worker.enqueue(job_id)
