"""Persistence of the partial dossier of the ML path and the queueing of its summaries."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from pydantic import HttpUrl

from wke.clients.redis import RedisClient
from wke.core import keys
from wke.core.models import Dossier, Job
from wke.core.titles import normalize_title
from wke.jobs.build.finalize import finalize
from wke.jobs.build.payload import dossier_payload, ptr_json
from wke.jobs.build.progress import bump_done
from wke.jobs.queue import JobQueue

logger = logging.getLogger(__name__)


async def persist_and_queue_summaries(
    *,
    redis: RedisClient,
    job_queue: JobQueue,
    job: Job,
    dossier: Dossier,
    selected_ids: list[str],
    pipeline_version: str,
    background: bool,
    ttl_seconds: int,
    result_url: HttpUrl | None = None,
) -> None:
    """Store the partial dossier and queue one summary item per selected section.

    Args:
        redis: Redis client.
        job_queue: JobQueue, for set_job and enqueue_summary_item.
        job: the running build job.
        dossier: the partial dossier.
        selected_ids: ids of the sections to summarise.
        pipeline_version: PIPELINE_VERSION setting.
        background: True to queue the items on the background list.
        ttl_seconds: lifetime of the stored dossier.
        result_url: Job.result_url, or None.
    """
    assert job.rev_id is not None
    dossier_key = keys.dossier(dossier.topic.page_id, job.rev_id, pipeline_version)
    await redis.set(dossier_key, dossier_payload(dossier), ex=ttl_seconds)
    await redis.set(
        keys.ptr(dossier.topic.page_id),
        ptr_json(job.rev_id, pipeline_version, dossier.build.built_at),
    )
    await redis.sadd(keys.TRACKED, str(dossier.topic.page_id))
    await redis.hset(
        keys.TRACKED_PAGE_IDS, normalize_title(dossier.topic.title), str(dossier.topic.page_id)
    )

    job.result_url = result_url
    job.updated_at = datetime.now(UTC)
    bump_done(job)  # persist complete
    await job_queue.set_job(job)

    if not selected_ids:
        # No section had chunks to summarize: nothing more will finalize
        # this job through a summary item, so finalize it here.
        await finalize(redis, job_queue, job, dossier, pipeline_version)
        return

    for section_id in selected_ids:
        await job_queue.enqueue_summary_item(job.id, section_id, background=background)
    job.stage = "summarize"
    await job_queue.set_job(job)
