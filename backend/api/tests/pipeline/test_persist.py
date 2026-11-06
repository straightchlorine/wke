"""The first persist of a build: indexes written, summary items queued or the job finalized."""

from __future__ import annotations

from tests.factories.dossier import make_fixture_dossier
from tests.support.builds import make_queue, queued_summary_items
from tests.support.constants import PIPELINE_VERSION
from tests.support.jobs import make_job
from wke.clients.redis import RedisClient
from wke.core import keys
from wke.core.models import Dossier, Job, SummaryState
from wke.core.titles import normalize_title
from wke.jobs.build.persist import persist_and_queue_summaries
from wke.jobs.queue import JobQueue


def _partial_dossier(summary_state: SummaryState) -> Dossier:
    dossier = make_fixture_dossier()
    dossier.build.state = "partial"
    for section in dossier.sections:
        section.summary_state = summary_state
        section.summary = None
    return dossier


async def _persist(
    redis_client: RedisClient, dossier: Dossier, selected_ids: list[str]
) -> tuple[Job, JobQueue]:
    job = make_job(page_id=dossier.topic.page_id, rev_id=7, status="running", stage="persist")
    queue = make_queue(redis_client)
    await queue.set_job(job)
    await redis_client.set(keys.jobkey(job.page_id, 7), job.id)
    await persist_and_queue_summaries(
        redis=redis_client,
        job_queue=queue,
        job=job,
        dossier=dossier,
        selected_ids=selected_ids,
        pipeline_version=PIPELINE_VERSION,
        background=False,
        ttl_seconds=keys.DOSSIER_TTL_SECONDS,
    )
    return job, queue


async def test_persist_writes_the_indexes_and_queues_one_item_per_selected_section(
    redis_client: RedisClient,
) -> None:
    dossier = _partial_dossier("pending")
    selected = [s.id for s in dossier.sections[:2]]

    job, queue = await _persist(redis_client, dossier, selected)

    page_id = str(dossier.topic.page_id)
    assert await redis_client.get(keys.dossier(dossier.topic.page_id, 7, PIPELINE_VERSION))
    assert await redis_client.get(keys.ptr(dossier.topic.page_id))
    assert await redis_client.sismember(keys.TRACKED, page_id)
    assert (
        await redis_client.hget(keys.TRACKED_PAGE_IDS, normalize_title(dossier.topic.title))
        == page_id
    )
    assert await queued_summary_items(redis_client) == [f"{job.id}:{sid}" for sid in selected]
    stored = await queue.get_job(job.id)
    assert stored is not None
    assert (stored.status, stored.stage) == ("running", "summarize")


async def test_persist_without_selected_sections_finalizes_the_job(
    redis_client: RedisClient,
) -> None:
    dossier = _partial_dossier("pending")

    job, queue = await _persist(redis_client, dossier, [])

    assert await queued_summary_items(redis_client) == []
    stored = await queue.get_job(job.id)
    assert stored is not None
    assert stored.status == "done"
    assert await redis_client.get(keys.jobkey(job.page_id, 7)) is None
    assert {s.summary_state for s in dossier.sections} == {"skipped"}
    assert dossier.build.state == "complete"
