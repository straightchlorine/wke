"""Job progress counters and stage transitions shared by the build and summary stages."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from wke.core.models import Job
from wke.jobs.queue import JobQueue

JobStage = Literal[
    "resolve", "fetch", "parse", "related", "embed", "cluster", "summarize", "persist"
]


def bump_done(job: Job) -> None:
    """Advance Job.progress.done by one completed stage, never past total.

    Args:
        job: the job whose progress is advancing.
    """
    job.progress.done = min(job.progress.done + 1, job.progress.total)


def set_total(job: Job, total: int) -> None:
    """Widen Job.progress.total once the real stage count is known.

    Args:
        job: the job whose progress total is being set.
        total: the real total, superseding the admission-time estimate.
    """
    job.progress.total = total


async def begin_job(job: Job, job_queue: JobQueue) -> None:
    """Mark the job running at the fetch stage once admission is complete.

    Args:
        job: the admitted job.
        job_queue: JobQueue, for set_job.
    """
    bump_done(job)  # resolve complete: it ran before admission
    job.status = "running"
    job.stage = "fetch"
    job.queue_position = None
    if job.started_at is None:
        job.started_at = datetime.now(UTC)
    await job_queue.set_job(job)


async def enter_stage(job: Job, job_queue: JobQueue, stage: JobStage) -> None:
    """Count the previous stage as done and publish the next one.

    Args:
        job: the running job.
        job_queue: JobQueue, for set_job.
        stage: the stage the job is entering.
    """
    bump_done(job)
    job.stage = stage
    await job_queue.set_job(job)
