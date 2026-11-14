"""The worker routes queue items, binds log ids, heartbeats, reaps stalls and requeues on stop."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
from datetime import UTC, datetime
from typing import Any

import pytest

from tests.support.builds import make_queue
from tests.support.constants import JOB_ID
from tests.support.jobs import make_job
from tests.support.workers import make_worker
from wke.clients.redis import RedisClient
from wke.core import keys
from wke.core.models import Job
from wke.jobs import worker as worker_module
from wke.logging_setup import job_id_var, request_id_var
from wke.worker.__main__ import _run_until_sigterm

SECTION_ITEM = f"{JOB_ID}:s1"
LONG_AGO = datetime(2000, 1, 1, tzinfo=UTC)


def _running_job(request_id: str | None = None, **overrides: Any) -> Job:
    return make_job(
        id=JOB_ID,
        rev_id=1,
        title=None,
        status="running",
        stage="fetch",
        request_id=request_id,
        **overrides,
    )


async def _hang(_queue_name: str, _value: str) -> None:
    await asyncio.sleep(10)


@pytest.mark.parametrize(
    ("queue_name", "item", "expected"),
    [
        (keys.QUEUE_INTERACTIVE, JOB_ID, ("build", JOB_ID, False)),
        (keys.QUEUE_BACKGROUND, JOB_ID, ("build", JOB_ID, True)),
        (keys.QUEUE_SUM_INTERACTIVE, SECTION_ITEM, ("summary", JOB_ID, "s1")),
        (keys.QUEUE_SUM_BACKGROUND, SECTION_ITEM, ("summary", JOB_ID, "s1")),
    ],
)
async def test_each_queue_runs_its_stage_and_the_item_leaves_processing(
    redis_client: RedisClient,
    monkeypatch: pytest.MonkeyPatch,
    queue_name: str,
    item: str,
    expected: tuple[str, str, bool | str],
) -> None:
    queue = make_queue(redis_client)
    await queue.set_job(_running_job())
    await redis_client.rpush(queue_name, item)
    ran: list[tuple[str, str, bool | str]] = []

    async def fake_run_build(job: Job, **kwargs: Any) -> None:
        ran.append(("build", job.id, kwargs["background"]))

    async def fake_run_summary_item(job_id: str, section_id: str, **_kwargs: Any) -> None:
        ran.append(("summary", job_id, section_id))

    monkeypatch.setattr(worker_module, "run_build", fake_run_build)
    monkeypatch.setattr(worker_module, "run_summary_item", fake_run_summary_item)

    await make_worker(redis_client, queue)._run_once()

    assert ran == [expected]
    assert await redis_client.lrange(keys.QUEUE_PROCESSING, 0, -1) == []


async def test_a_build_item_without_a_job_record_is_dropped(
    redis_client: RedisClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fail(*_args: Any, **_kwargs: Any) -> None:
        pytest.fail("no build for a missing job")

    monkeypatch.setattr(worker_module, "run_build", fail)
    await redis_client.rpush(keys.QUEUE_INTERACTIVE, JOB_ID)

    await make_worker(redis_client, make_queue(redis_client))._run_once()

    assert await redis_client.lrange(keys.QUEUE_PROCESSING, 0, -1) == []


async def test_a_failing_item_is_logged_and_cleared_without_stopping_the_worker(
    redis_client: RedisClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    queue = make_queue(redis_client)
    await queue.set_job(_running_job())
    await redis_client.rpush(keys.QUEUE_INTERACTIVE, JOB_ID)

    async def boom(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(worker_module, "run_build", boom)
    caplog.set_level(logging.ERROR, logger="wke.jobs.worker")

    await make_worker(redis_client, queue)._run_once()

    assert f"worker item failed: {keys.QUEUE_INTERACTIVE} {JOB_ID}" in caplog.text
    assert await redis_client.lrange(keys.QUEUE_PROCESSING, 0, -1) == []


@pytest.mark.parametrize(
    ("request_id", "expected"), [("req-12345678", "req-12345678"), (None, f"job-{JOB_ID}")]
)
async def test_worker_binds_the_request_and_job_ids_while_running_a_build(
    redis_client: RedisClient,
    monkeypatch: pytest.MonkeyPatch,
    request_id: str | None,
    expected: str,
) -> None:
    queue = make_queue(redis_client)
    await queue.set_job(_running_job(request_id))
    await redis_client.rpush(keys.QUEUE_INTERACTIVE, JOB_ID)
    bound: list[tuple[str | None, str | None]] = []

    async def fake_run_build(_job: Job, **_kwargs: Any) -> None:
        bound.append((request_id_var.get(), job_id_var.get()))

    monkeypatch.setattr(worker_module, "run_build", fake_run_build)

    await make_worker(redis_client, queue)._run_once()

    assert bound == [(expected, JOB_ID)]
    assert request_id_var.get() is None
    assert job_id_var.get() is None


async def test_run_forever_requeues_in_flight_item_on_cancellation(
    redis_client: RedisClient,
) -> None:
    await redis_client.lpush(keys.QUEUE_INTERACTIVE, "job-1")
    worker = make_worker(redis_client, make_queue(redis_client))
    worker._process = _hang  # type: ignore[method-assign]

    task = asyncio.create_task(worker.run_forever())
    await _until_processing(redis_client)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert await redis_client.lrange(keys.QUEUE_PROCESSING, 0, -1) == []
    assert await redis_client.lrange(keys.QUEUE_BACKGROUND, 0, -1) == ["job-1"]


async def test_run_until_sigterm_requeues_in_flight_item_on_real_signal(
    redis_client: RedisClient,
) -> None:
    """Sends a real SIGTERM, so the signal handler is exercised, not task cancellation."""
    await redis_client.lpush(keys.QUEUE_INTERACTIVE, "job-sigterm")
    worker = make_worker(redis_client, make_queue(redis_client))
    worker._process = _hang  # type: ignore[method-assign]

    task = asyncio.create_task(_run_until_sigterm(worker))
    await _until_processing(redis_client)
    os.kill(os.getpid(), signal.SIGTERM)
    await asyncio.wait_for(task, timeout=1.0)

    assert await redis_client.lrange(keys.QUEUE_PROCESSING, 0, -1) == []
    assert await redis_client.lrange(keys.QUEUE_BACKGROUND, 0, -1) == ["job-sigterm"]


async def _until_processing(redis_client: RedisClient) -> None:
    async with asyncio.timeout(1.0):
        while not await redis_client.lrange(keys.QUEUE_PROCESSING, 0, -1):
            await asyncio.sleep(0.01)


async def test_heartbeat_writes_separate_key_and_never_clobbers_job(
    redis_client: RedisClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Interval 0 so a beat runs after the concurrent write below; at the real
    # interval the heartbeat would not tick again and a clobber would go unseen.
    monkeypatch.setattr(worker_module, "HEARTBEAT_INTERVAL_SECONDS", 0)
    queue = make_queue(redis_client)
    job = _running_job()
    await queue.set_job(job)
    worker = make_worker(redis_client, queue)

    task = asyncio.create_task(worker._heartbeat(job.id))
    try:
        await asyncio.sleep(0.05)
        assert await redis_client.get(keys.job_heartbeat(job.id)) is not None

        # A pipeline update lands after the heartbeat wrote.
        job.status = "done"
        job.stage = "persist"
        await queue.set_job(job)
        await asyncio.sleep(0.05)
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    stored = await queue.get_job(job.id)
    assert stored is not None
    assert (stored.status, stored.stage) == ("done", "persist")


@pytest.mark.parametrize(
    ("item", "heartbeat_fresh", "requeued_to"),
    [
        (JOB_ID, False, keys.QUEUE_BACKGROUND),
        (SECTION_ITEM, False, keys.QUEUE_SUM_BACKGROUND),
        (JOB_ID, True, None),
        ("ffffffffffffffff", False, keys.QUEUE_BACKGROUND),
    ],
    ids=["stale build", "stale summary item", "fresh heartbeat", "job record gone"],
)
async def test_reap_stalled_requeues_only_items_without_a_fresh_heartbeat(
    redis_client: RedisClient, item: str, heartbeat_fresh: bool, requeued_to: str | None
) -> None:
    queue = make_queue(redis_client)
    await queue.set_job(_running_job(updated_at=LONG_AGO))
    if heartbeat_fresh:
        await redis_client.set(
            keys.job_heartbeat(JOB_ID),
            datetime.now(UTC).isoformat(),
            ex=keys.JOB_HEARTBEAT_TTL_SECONDS,
        )
    await redis_client.lpush(keys.QUEUE_PROCESSING, item)

    await make_worker(redis_client, queue).reap_stalled()

    if requeued_to is None:
        assert await redis_client.lrange(keys.QUEUE_PROCESSING, 0, -1) == [item]
    else:
        assert await redis_client.lrange(keys.QUEUE_PROCESSING, 0, -1) == []
        assert await redis_client.lrange(requeued_to, 0, -1) == [item]
