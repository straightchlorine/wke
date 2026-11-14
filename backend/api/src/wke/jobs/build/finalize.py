"""Final job transition once every selected summary is settled."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from wke.clients.redis import RedisClient
from wke.core import keys
from wke.core.models import Dossier, Job
from wke.core.viewcache import invalidate_views
from wke.jobs.build.payload import dossier_payload
from wke.jobs.build.progress import bump_done
from wke.jobs.queue import JobQueue
from wke.metrics import DOSSIER_BUILD_SECONDS, JOB_STAGE_SECONDS, SUMMARY_STATE_TOTAL

logger = logging.getLogger(__name__)


async def finalize(
    redis: RedisClient,
    job_queue: JobQueue,
    job: Job,
    dossier: Dossier,
    pipeline_version: str,
) -> None:
    """Settle skipped summaries, mark the dossier complete and finish the job.

    Args:
        redis: Redis client.
        job_queue: JobQueue, for set_job.
        job: the build job.
        dossier: the dossier, changed in place.
        pipeline_version: PIPELINE_VERSION setting.
    """
    for section in dossier.sections:
        if section.summary_state == "pending":
            section.summary_state = "skipped"
            SUMMARY_STATE_TOTAL.labels(state="skipped").inc()
    dossier.build.state = "complete"
    dossier.build.summaries_done = sum(1 for s in dossier.sections if s.summary_state == "done")

    now = datetime.now(UTC)
    stage_seconds = dict(dossier.build.stage_seconds or {})
    summarize_seconds = max((now - dossier.build.built_at).total_seconds(), 0.0)
    stage_seconds["summarize"] = summarize_seconds
    stage_seconds["total"] = stage_seconds.get("build", 0.0) + summarize_seconds
    dossier.build.stage_seconds = stage_seconds
    JOB_STAGE_SECONDS.labels(stage="summarize").observe(summarize_seconds)
    DOSSIER_BUILD_SECONDS.labels(outcome="complete", analysis=dossier.build.analysis).observe(
        stage_seconds["total"]
    )

    assert job.rev_id is not None
    dossier_key = keys.dossier(dossier.topic.page_id, job.rev_id, pipeline_version)
    await redis.set(dossier_key, dossier_payload(dossier), ex=keys.DOSSIER_TTL_SECONDS)
    await redis.zadd(keys.BUILT, {str(dossier.topic.page_id): now.timestamp()})
    invalidate_views()

    bump_done(job)  # finalize complete
    job.status = "done"
    job.queue_position = None
    job.finished_at = now
    job.updated_at = now
    await job_queue.set_job(job)
    await redis.delete(keys.jobkey(job.page_id, job.rev_id))
    logger.info(
        "job_done job_id=%s page_id=%s rev_id=%s stage_seconds=%.2f",
        job.id,
        job.page_id,
        job.rev_id,
        stage_seconds["total"],
    )
