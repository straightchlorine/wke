"""Admission rules: ready dossiers, force, the gate, queue caps and the stored record."""

from __future__ import annotations

import pytest

from tests.support.constants import FIXTURE_PAGE_ID, FIXTURE_REV_ID, FIXTURE_TITLE
from wke.clients.redis import RedisClient
from wke.core import keys
from wke.core.errors import ApiException
from wke.jobs.queue import JobQueue
from wke.logging_setup import request_id_var

PIPELINE_VERSION = "test-pv"


async def _store_dossier(redis_client: RedisClient) -> None:
    key = keys.dossier(FIXTURE_PAGE_ID, FIXTURE_REV_ID, PIPELINE_VERSION)
    await redis_client.set(key, "{}", ex=3600)


async def test_admit_returns_ready_without_gate_or_queue_write_when_a_dossier_exists(
    redis_client: RedisClient,
) -> None:
    queue = JobQueue(redis_client, PIPELINE_VERSION, queue_cap=20)
    await _store_dossier(redis_client)
    gate_calls: list[None] = []

    result = await queue.admit(
        FIXTURE_PAGE_ID, FIXTURE_REV_ID, FIXTURE_TITLE, gate=lambda: gate_calls.append(None)
    )

    assert result == "ready"
    assert gate_calls == []
    assert await redis_client.llen(keys.QUEUE_INTERACTIVE) == 0


async def test_force_enqueues_a_rebuild_and_keeps_the_existing_dossier(
    redis_client: RedisClient,
) -> None:
    queue = JobQueue(redis_client, PIPELINE_VERSION, queue_cap=20)
    await _store_dossier(redis_client)

    first = await queue.admit(FIXTURE_PAGE_ID, FIXTURE_REV_ID, FIXTURE_TITLE, force=True)
    second = await queue.admit(FIXTURE_PAGE_ID, FIXTURE_REV_ID, FIXTURE_TITLE, force=True)

    assert first != "ready"
    assert second != "ready"
    assert second.id == first.id
    assert await redis_client.llen(keys.QUEUE_INTERACTIVE) == 1
    assert await redis_client.exists(
        keys.dossier(FIXTURE_PAGE_ID, FIXTURE_REV_ID, PIPELINE_VERSION)
    )


async def test_a_refusing_gate_queues_nothing(redis_client: RedisClient) -> None:
    queue = JobQueue(redis_client, PIPELINE_VERSION, queue_cap=20)

    def refuse() -> None:
        raise ApiException(429, "rate_limited")

    with pytest.raises(ApiException):
        await queue.admit(FIXTURE_PAGE_ID, FIXTURE_REV_ID, FIXTURE_TITLE, gate=refuse)

    assert await redis_client.get(keys.jobkey(FIXTURE_PAGE_ID, FIXTURE_REV_ID)) is None
    assert await redis_client.llen(keys.QUEUE_INTERACTIVE) == 0


async def test_admit_at_the_cap_raises_queue_full_and_releases_the_jobkey(
    redis_client: RedisClient,
) -> None:
    queue = JobQueue(redis_client, PIPELINE_VERSION, queue_cap=1)
    await queue.admit(1, 100, "One")

    with pytest.raises(ApiException) as caught:
        await queue.admit(FIXTURE_PAGE_ID, FIXTURE_REV_ID, FIXTURE_TITLE)

    assert (caught.value.status_code, caught.value.code) == (503, "queue_full")
    assert caught.value.retry_after == 5
    assert await redis_client.get(keys.jobkey(FIXTURE_PAGE_ID, FIXTURE_REV_ID)) is None
    assert await redis_client.llen(keys.QUEUE_INTERACTIVE) == 1


async def test_background_admission_at_its_own_cap_raises_queue_full(
    redis_client: RedisClient,
) -> None:
    queue = JobQueue(redis_client, PIPELINE_VERSION, queue_cap=20, background_queue_cap=1)
    await queue.admit(1, 100, "One", background=True)

    with pytest.raises(ApiException) as caught:
        await queue.admit(2, 200, "Two", background=True)

    assert caught.value.code == "queue_full"
    assert await redis_client.llen(keys.QUEUE_BACKGROUND) == 1


async def test_full_background_queue_does_not_reject_interactive_admission(
    redis_client: RedisClient,
) -> None:
    queue = JobQueue(redis_client, PIPELINE_VERSION, queue_cap=2, background_queue_cap=2)
    await queue.admit(1, 100, "One", background=True)
    await queue.admit(2, 200, "Two", background=True)

    # q:background is now at its cap; an interactive admission must not
    # be rejected because of it.
    result = await queue.admit(3, 300, "Three", background=False)

    assert result != "ready"
    assert result.status == "queued"


async def test_full_interactive_queue_does_not_reject_background_admission(
    redis_client: RedisClient,
) -> None:
    queue = JobQueue(redis_client, PIPELINE_VERSION, queue_cap=1, background_queue_cap=2)
    await queue.admit(1, 100, "One", background=False)

    result = await queue.admit(2, 200, "Two", background=True)

    assert result != "ready"
    assert result.status == "queued"


async def test_admit_stores_the_job_with_its_queue_position_and_request_id(
    redis_client: RedisClient,
) -> None:
    queue = JobQueue(redis_client, PIPELINE_VERSION, queue_cap=20)
    await queue.admit(1, 100, "One")
    await queue.admit(2, 200, "Two", background=True)
    token = request_id_var.set("req-abc12345")
    try:
        admitted = await queue.admit(FIXTURE_PAGE_ID, FIXTURE_REV_ID, FIXTURE_TITLE)
    finally:
        request_id_var.reset(token)
    assert admitted != "ready"

    stored = await queue.get_job(admitted.id)

    assert stored is not None
    assert stored.queue_position == 3
    assert stored.request_id == "req-abc12345"
    assert await queue.queue_depth() == 3


async def test_enqueue_summary_item_pushes_to_the_matching_summary_queue(
    redis_client: RedisClient,
) -> None:
    queue = JobQueue(redis_client, PIPELINE_VERSION, queue_cap=20)

    await queue.enqueue_summary_item("job1", "sec-a")
    await queue.enqueue_summary_item("job2", "sec-b", background=True)

    assert await redis_client.llen(keys.QUEUE_SUM_INTERACTIVE) == 1
    assert await redis_client.llen(keys.QUEUE_SUM_BACKGROUND) == 1
    assert await queue.next_item(timeout=1.0) == (keys.QUEUE_SUM_INTERACTIVE, "job1:sec-a")
