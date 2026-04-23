"""
Queue abstraction for job management.

Provides a BaseQueue interface with three implementations:
    - InMemoryQueue   — dev-only fallback, loses jobs on restart.
    - PostgresQueue   — durable baseline queue used in production.
    - (Redis, Task 8) — deferred to the scalability workshop.

The interface is narrow on purpose (enqueue / dequeue / get / update) so the
worker loop and processor never need to know which backend is active. This
is the Strategy pattern — swap backends by changing config, not code.

Why Postgres for the baseline queue
-----------------------------------
We already depend on Postgres for chat sessions and users, so adding a
`batch_jobs` table costs nothing extra in ops. For the baseline's throughput
(human-driven batches, not millions of events per second), Postgres is more
than fast enough, and `SELECT ... FOR UPDATE SKIP LOCKED` is a well-known,
well-documented pattern for competing consumers against a single table.

Task 8 will introduce Redis for the queue when we care about latency and
throughput enough to justify the extra infra.
"""

import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from shared.logging import get_logger
from shared.models import BatchJob
from shared.schemas import JobResponse, JobStatus, JobSubmission

logger = get_logger(__name__)


def _job_to_response(job: BatchJob) -> JobResponse:
    """Convert an ORM row to the public JobResponse schema."""
    return JobResponse(
        job_id=str(job.id),
        status=JobStatus(job.status),
        created_at=job.created_at,
        completed_at=job.completed_at,
        total_prompts=job.total_prompts,
        completed_prompts=job.completed_prompts,
        results=list(job.results or []),
        error=job.error,
    )


class BaseQueue(ABC):
    """Abstract queue interface. All queue backends implement this."""

    @abstractmethod
    async def enqueue(self, submission: JobSubmission) -> JobResponse:
        """Add a job to the queue. Returns the initial job response."""
        ...

    @abstractmethod
    async def dequeue(self) -> tuple[str, JobSubmission] | None:
        """Get the next pending job. Returns (job_id, submission) or None."""
        ...

    @abstractmethod
    async def get_job(self, job_id: str) -> JobResponse | None:
        """Get job status and results by ID."""
        ...

    @abstractmethod
    async def update_job(self, job_id: str, **kwargs) -> None:
        """Update job fields (status, results, error, etc.)."""
        ...


class InMemoryQueue(BaseQueue):
    """Dict-backed queue for local development. Not suitable for production.

    Jobs are stored in a dictionary keyed by job_id. A simple list serves as
    the pending queue. This implementation is single-process only — in production,
    use Redis or another shared queue backend.
    """

    def __init__(self):
        self._jobs: dict[str, JobResponse] = {}
        self._submissions: dict[str, JobSubmission] = {}
        self._pending: list[str] = []

    async def enqueue(self, submission: JobSubmission) -> JobResponse:
        job_id = str(uuid.uuid4())
        job = JobResponse(
            job_id=job_id,
            status=JobStatus.PENDING,
            created_at=datetime.now(timezone.utc),
            total_prompts=len(submission.prompts),
        )
        self._jobs[job_id] = job
        self._submissions[job_id] = submission
        self._pending.append(job_id)

        logger.info("job_enqueued", job_id=job_id, prompts=len(submission.prompts))
        return job

    async def dequeue(self) -> tuple[str, JobSubmission] | None:
        if not self._pending:
            return None

        job_id = self._pending.pop(0)
        submission = self._submissions[job_id]

        # Mark as running
        self._jobs[job_id].status = JobStatus.RUNNING

        logger.info("job_dequeued", job_id=job_id)
        return job_id, submission

    async def get_job(self, job_id: str) -> JobResponse | None:
        return self._jobs.get(job_id)

    async def update_job(self, job_id: str, **kwargs) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            return

        for key, value in kwargs.items():
            if hasattr(job, key):
                setattr(job, key, value)

        logger.info("job_updated", job_id=job_id, updates=list(kwargs.keys()))


class PostgresQueue(BaseQueue):
    """Postgres-backed durable job queue.

    Each job is a row in `batch_jobs`. Dequeue uses
    `SELECT ... FOR UPDATE SKIP LOCKED` so multiple worker processes can
    consume the queue concurrently without stepping on each other — a
    single row is handed to exactly one worker, and the rest are skipped.

    Why SKIP LOCKED:
        Without it, two workers could both grab the same pending row. With
        it, Postgres only considers rows not currently locked by another
        transaction; the losing worker silently moves on to the next
        available row. No retries, no contention storms.
    """

    def __init__(self, sessionmaker: async_sessionmaker):
        self._sm = sessionmaker

    async def enqueue(self, submission: JobSubmission) -> JobResponse:
        job_id = uuid.uuid4()
        async with self._sm() as session:
            job = BatchJob(
                id=job_id,
                status=JobStatus.PENDING.value,
                model=submission.model,
                max_tokens=submission.max_tokens,
                prompts=list(submission.prompts),
                results=[],
                total_prompts=len(submission.prompts),
                completed_prompts=0,
            )
            session.add(job)
            await session.commit()
            await session.refresh(job)
            logger.info("job_enqueued", job_id=str(job.id), prompts=len(submission.prompts))
            return _job_to_response(job)

    async def dequeue(self) -> tuple[str, JobSubmission] | None:
        """Atomically claim the oldest pending job.

        The `with_for_update(skip_locked=True)` clause translates to
        `SELECT ... FOR UPDATE SKIP LOCKED` — the row we select is locked
        for the duration of the transaction, and any concurrent worker
        running the same query skips past locked rows.
        """
        async with self._sm() as session:
            stmt = (
                select(BatchJob)
                .where(BatchJob.status == JobStatus.PENDING.value)
                .order_by(BatchJob.created_at.asc())
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            result = await session.execute(stmt)
            job = result.scalar_one_or_none()
            if job is None:
                return None

            # Flip to RUNNING within the same transaction — another worker
            # that queries after our commit will see the new status and
            # won't reconsider this row.
            job.status = JobStatus.RUNNING.value
            submission = JobSubmission(
                prompts=list(job.prompts),
                model=job.model,
                max_tokens=job.max_tokens,
            )
            await session.commit()
            logger.info("job_dequeued", job_id=str(job.id))
            return str(job.id), submission

    async def get_job(self, job_id: str) -> JobResponse | None:
        async with self._sm() as session:
            try:
                pk = uuid.UUID(job_id)
            except ValueError:
                return None
            job = await session.get(BatchJob, pk)
            return _job_to_response(job) if job is not None else None

    async def update_job(self, job_id: str, **kwargs) -> None:
        """Patch a subset of job fields. Unknown keys are ignored.

        We translate the public field names used by the processor
        (`status`, `results`, `completed_prompts`, `completed_at`, `error`)
        into direct column updates. `status` may be a JobStatus enum or its
        string value — we normalise to string for storage.
        """
        if not kwargs:
            return

        allowed = {"status", "results", "completed_prompts", "completed_at", "error"}
        values: dict = {}
        for key, value in kwargs.items():
            if key not in allowed:
                continue
            if key == "status" and isinstance(value, JobStatus):
                values[key] = value.value
            else:
                values[key] = value

        if not values:
            return

        try:
            pk = uuid.UUID(job_id)
        except ValueError:
            return

        async with self._sm() as session:
            await session.execute(
                update(BatchJob).where(BatchJob.id == pk).values(**values)
            )
            await session.commit()
        logger.info("job_updated", job_id=job_id, updates=list(values.keys()))


def create_queue(
    queue_type: str = "memory",
    sessionmaker: async_sessionmaker | None = None,
) -> BaseQueue:
    """Factory function to create the appropriate queue backend.

    Args:
        queue_type: "memory" | "postgres" | "redis".
        sessionmaker: required when queue_type == "postgres". Ignored otherwise.
    """
    if queue_type == "memory":
        return InMemoryQueue()
    if queue_type == "postgres":
        if sessionmaker is None:
            raise ValueError("PostgresQueue requires a sessionmaker")
        return PostgresQueue(sessionmaker)
    if queue_type == "redis":
        raise NotImplementedError(
            "Redis queue is implemented in Task 8 (Load Balancing & Caching). "
            "Use queue_type='postgres' for the baseline."
        )
    raise ValueError(f"Unknown queue type: {queue_type}")
