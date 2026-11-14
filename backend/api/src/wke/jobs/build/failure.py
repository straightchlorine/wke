"""Mapping of build exceptions to the job's terminal failure."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime

from wke.clients.redis import RedisClient
from wke.core import keys
from wke.core.errors import PROBLEM_BASE_URI, ApiException
from wke.core.models import ApiError, ErrorCode, Job
from wke.jobs.queue import JobQueue

logger = logging.getLogger(__name__)


def job_failure_error(exc: Exception, job_id: str, request_id: str | None = None) -> ApiError:
    """Build the ApiError stored on a Job that a build failed with.

    Job.error is served verbatim by GET /api/v1/jobs/{id}, so a non-
    ApiException exception (a bug, not an expected failure) never leaks
    its message; the real exception is logged instead, keyed by the same
    request_id.

    Args:
        exc: the exception that failed the build or summary item.
        job_id: the job this failure belongs to, for the log line.
        request_id: the submitting request's id; a fresh uuid when the job
            was admitted without one (trending prebuild, old records).

    Returns:
        ApiError: ApiException's own status/code/detail if it was one,
        else a generic 500 "internal" error with a fixed detail.
    """
    request_id = request_id or str(uuid.uuid4())
    code: ErrorCode
    if isinstance(exc, ApiException):
        code = exc.code
        status_code, detail = exc.status_code, exc.detail
    else:
        status_code = 500
        code = "internal"
        detail = "Build failed; see server logs with this request_id."
        logger.exception(
            "job_failed_unexpectedly job_id=%s",
            job_id,
            exc_info=exc,
            extra={"job_id": job_id, "request_id": request_id},
        )
    return ApiError(
        type=f"{PROBLEM_BASE_URI}/{code}",
        title="Build failed",
        status=status_code,
        detail=detail,
        code=code,
        request_id=request_id,
    )


async def fail_job(
    job: Job, redis: RedisClient, job_queue: JobQueue, pipeline_version: str, exc: Exception
) -> None:
    """Mark a job failed and never leave an invalid dossier behind it.

    The single-flight jobkey is deleted at job end; otherwise a failure
    would leave the job "running" until its 1 h TTL and every new POST for
    that page/rev would get the same stuck job back. Any partial dossier
    this build already persisted is deleted too (a no-op DELETE if nothing
    was ever written), and `ptr:{page_id}` is deleted with it only if it
    still points at this exact build (rev_id and pipeline_version), never
    at a previously complete dossier from an earlier build.

    Args:
        job: the job that failed.
        redis: Redis client, to delete the dossier/ptr/jobkey.
        job_queue: JobQueue, to persist the failed status.
        pipeline_version: PIPELINE_VERSION setting, part of the dossier key.
        exc: the exception that failed the job.
    """
    job.status = "failed"
    job.queue_position = None
    job.error = job_failure_error(exc, job.id, job.request_id)
    job.updated_at = datetime.now(UTC)
    job.finished_at = job.updated_at
    await job_queue.set_job(job)
    logger.warning(
        "job_failed job_id=%s page_id=%s rev_id=%s code=%s",
        job.id,
        job.page_id,
        job.rev_id,
        job.error.code,
        extra={"job_id": job.id, "request_id": job.request_id},
    )
    if job.rev_id is not None:
        dossier_key = keys.dossier(job.page_id, job.rev_id, pipeline_version)
        await redis.delete(dossier_key)

        ptr_key = keys.ptr(job.page_id)
        raw_ptr = await redis.get(ptr_key)
        if raw_ptr is not None:
            ptr_data = json.loads(raw_ptr)
            if (
                ptr_data.get("rev_id") == job.rev_id
                and ptr_data.get("pipeline_version") == pipeline_version
            ):
                await redis.delete(ptr_key)

        await redis.delete(keys.jobkey(job.page_id, job.rev_id))
