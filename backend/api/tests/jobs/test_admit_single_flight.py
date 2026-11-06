"""Concurrent admits for the same build = one job.

The jobkey SET NX loser must not fall through to a second RPUSH.
"""

from __future__ import annotations

import asyncio
from typing import Literal

import pytest
from fakeredis.aioredis import FakeRedis

from tests.support.constants import FIXTURE_PAGE_ID, FIXTURE_REV_ID, FIXTURE_TITLE
from wke.clients.redis import RedisClient
from wke.core import keys
from wke.jobs import queue as queue_module
from wke.jobs.queue import JobQueue

PIPELINE_VERSION = "test-pv"


async def test_concurrent_admits_enqueue_exactly_one_job(redis_client: RedisClient) -> None:
    queue = JobQueue(redis_client, PIPELINE_VERSION, queue_cap=20)

    results = await asyncio.gather(
        *(queue.admit(FIXTURE_PAGE_ID, FIXTURE_REV_ID, FIXTURE_TITLE) for _ in range(10))
    )

    job_ids = {job.id for job in results if job != "ready"}
    assert len(job_ids) == 1

    depth = await redis_client.llen(keys.QUEUE_INTERACTIVE)
    assert depth == 1


async def test_admit_reclaims_jobkey_when_job_record_never_appeared(
    redis_client: RedisClient, fake_redis: FakeRedis
) -> None:
    """A caller crashed after SET NX but before writing job:{id}."""
    queue = JobQueue(redis_client, PIPELINE_VERSION, queue_cap=20)
    job_id = "0" * 16
    jobkey = keys.jobkey(FIXTURE_PAGE_ID, FIXTURE_REV_ID)
    await redis_client.set(jobkey, job_id, ex=30, nx=True)

    result = await queue.admit(FIXTURE_PAGE_ID, FIXTURE_REV_ID, FIXTURE_TITLE)

    assert result != "ready"
    depth = await redis_client.llen(keys.QUEUE_INTERACTIVE)
    assert depth == 1
    # The reclaim refreshes the jobkey's TTL and drops its own lock.
    assert await fake_redis.ttl(jobkey) > 30
    assert await redis_client.get(keys.jobkey_reclaim(FIXTURE_PAGE_ID, FIXTURE_REV_ID)) is None


@pytest.mark.parametrize("finished_status", ["done", "failed"])
async def test_admit_treats_a_finished_job_with_no_dossier_as_absent(
    redis_client: RedisClient, finished_status: Literal["done", "failed"]
) -> None:
    """A structural build's job stayed finished after its short-TTL dossier expired."""
    queue = JobQueue(redis_client, PIPELINE_VERSION, queue_cap=20)
    first = await queue.admit(FIXTURE_PAGE_ID, FIXTURE_REV_ID, FIXTURE_TITLE)
    assert first != "ready"
    first.status = finished_status
    await queue.set_job(first)

    second = await queue.admit(FIXTURE_PAGE_ID, FIXTURE_REV_ID, FIXTURE_TITLE)

    assert second != "ready"
    assert second.status == "queued"
    depth = await redis_client.llen(keys.QUEUE_INTERACTIVE)
    assert depth == 2


async def test_concurrent_admits_racing_a_stale_done_job_enqueue_exactly_one(
    redis_client: RedisClient,
) -> None:
    """Concurrent reclaim of stale done job enqueues exactly once via SET NX serialization."""
    queue = JobQueue(redis_client, PIPELINE_VERSION, queue_cap=20)
    first = await queue.admit(FIXTURE_PAGE_ID, FIXTURE_REV_ID, FIXTURE_TITLE)
    assert first != "ready"
    first.status = "done"
    await queue.set_job(first)
    # Drain the first (now-stale) job's own queue entry so only the
    # reclaim race's entries are being counted below.
    await redis_client.lrem(keys.QUEUE_INTERACTIVE, 0, first.id)

    results = await asyncio.gather(
        *(queue.admit(FIXTURE_PAGE_ID, FIXTURE_REV_ID, FIXTURE_TITLE) for _ in range(10))
    )

    job_ids = {job.id for job in results if job != "ready"}
    assert len(job_ids) == 1
    depth = await redis_client.llen(keys.QUEUE_INTERACTIVE)
    assert depth == 1


async def test_admit_enqueues_anyway_when_the_reclaim_holder_never_finishes(
    redis_client: RedisClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Another caller holds the reclaim lock and no job record ever shows up."""
    monkeypatch.setattr(queue_module, "JOBKEY_RECLAIM_POLL_ATTEMPTS", 2)
    monkeypatch.setattr(queue_module, "JOBKEY_RECLAIM_POLL_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(queue_module, "JOBKEY_WINNER_POLL_ATTEMPTS", 1)
    monkeypatch.setattr(queue_module, "JOBKEY_WINNER_POLL_INTERVAL_SECONDS", 0)
    queue = JobQueue(redis_client, PIPELINE_VERSION, queue_cap=20)
    jobkey = keys.jobkey(FIXTURE_PAGE_ID, FIXTURE_REV_ID)
    await redis_client.set(jobkey, "0" * 16, ex=3600, nx=True)
    await redis_client.set(
        keys.jobkey_reclaim(FIXTURE_PAGE_ID, FIXTURE_REV_ID), "0" * 16, ex=3600, nx=True
    )

    result = await queue.admit(FIXTURE_PAGE_ID, FIXTURE_REV_ID, FIXTURE_TITLE)

    assert result != "ready"
    assert await redis_client.llen(keys.QUEUE_INTERACTIVE) == 1
