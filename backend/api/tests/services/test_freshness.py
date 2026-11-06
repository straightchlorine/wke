"""Read-time state classification and settle-window background-rebuild rule."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tests.support.constants import FIXTURE_PAGE_ID, FIXTURE_TITLE
from wke.clients.redis import RedisClient
from wke.core import keys
from wke.jobs.queue import JobQueue
from wke.services import freshness

PIPELINE_VERSION = "test-pv"
PAGE_ID = FIXTURE_PAGE_ID
PINNED_REV_ID = 1_000_000


def _queue(redis_client: RedisClient) -> JobQueue:
    return JobQueue(redis_client, PIPELINE_VERSION, queue_cap=20)


async def test_unknown_when_no_watcher_pointer(redis_client: RedisClient) -> None:
    result = await freshness.compute_freshness(
        redis_client, PAGE_ID, PINNED_REV_ID, datetime.now(UTC)
    )

    assert result.state == "unknown"
    assert result.source == "none"
    assert result.latest_rev_id is None
    assert result.edits_since is None
    assert result.checked_at is None


async def test_checked_at_is_the_watchers_observation_time(redis_client: RedisClient) -> None:
    observed = datetime(2026, 9, 29, 8, 30, tzinfo=UTC)
    await redis_client.set(keys.latest_rev(PAGE_ID), str(PINNED_REV_ID))
    await redis_client.zadd(keys.pageedits(PAGE_ID), {str(PINNED_REV_ID): observed.timestamp()})

    result = await freshness.compute_freshness(
        redis_client, PAGE_ID, PINNED_REV_ID, datetime(2026, 9, 29, 8, 0, tzinfo=UTC)
    )

    assert result.source == "watcher"
    assert result.checked_at == observed


async def test_unknown_when_latest_rev_is_malformed(redis_client: RedisClient) -> None:
    await redis_client.set(keys.latest_rev(PAGE_ID), "not-a-number")

    result = await freshness.compute_freshness(
        redis_client, PAGE_ID, PINNED_REV_ID, datetime.now(UTC)
    )

    assert result.state == "unknown"


async def test_fresh_when_pinned_rev_is_the_latest(redis_client: RedisClient) -> None:
    await redis_client.set(keys.latest_rev(PAGE_ID), str(PINNED_REV_ID))

    result = await freshness.compute_freshness(
        redis_client, PAGE_ID, PINNED_REV_ID, datetime.now(UTC)
    )

    assert result.state == "fresh"
    assert result.source == "watcher"
    assert result.latest_rev_id == PINNED_REV_ID
    assert result.edits_since == 0


async def test_stale_counts_edits_after_built_at_only(redis_client: RedisClient) -> None:
    latest_rev_id = PINNED_REV_ID + 1
    await redis_client.set(keys.latest_rev(PAGE_ID), str(latest_rev_id))
    built_at = datetime.now(UTC) - timedelta(minutes=10)

    before_build = (built_at - timedelta(minutes=5)).timestamp()
    after_build_1 = (built_at + timedelta(minutes=1)).timestamp()
    after_build_2 = (built_at + timedelta(minutes=2)).timestamp()
    await redis_client.zadd(
        keys.pageedits(PAGE_ID),
        {
            str(PINNED_REV_ID): before_build,
            str(latest_rev_id): after_build_1,
            str(latest_rev_id + 1): after_build_2,
            str(latest_rev_id + 2): built_at.timestamp(),
        },
    )

    result = await freshness.compute_freshness(redis_client, PAGE_ID, PINNED_REV_ID, built_at)

    assert result.state == "stale"
    assert result.latest_rev_id == latest_rev_id
    assert result.edits_since == 2


async def test_no_rebuild_when_build_is_not_yet_30_minutes_old(redis_client: RedisClient) -> None:
    queue = _queue(redis_client)
    built_at = datetime.now(UTC) - timedelta(minutes=29)
    latest_rev_id = PINNED_REV_ID + 1
    await redis_client.set(keys.latest_rev(PAGE_ID), str(latest_rev_id))
    settled_edit = (datetime.now(UTC) - timedelta(minutes=10)).timestamp()
    await redis_client.zadd(keys.pageedits(PAGE_ID), {str(latest_rev_id): settled_edit})

    admitted = await freshness.maybe_enqueue_rebuild(
        redis_client, queue, PAGE_ID, FIXTURE_TITLE, built_at
    )

    assert admitted is False
    assert await redis_client.llen(keys.QUEUE_BACKGROUND) == 0


async def test_no_rebuild_when_last_edit_is_within_the_quiet_window(
    redis_client: RedisClient,
) -> None:
    queue = _queue(redis_client)
    built_at = datetime.now(UTC) - timedelta(minutes=45)
    latest_rev_id = PINNED_REV_ID + 1
    await redis_client.set(keys.latest_rev(PAGE_ID), str(latest_rev_id))
    recent_edit = (datetime.now(UTC) - timedelta(minutes=1)).timestamp()
    await redis_client.zadd(keys.pageedits(PAGE_ID), {str(latest_rev_id): recent_edit})

    admitted = await freshness.maybe_enqueue_rebuild(
        redis_client, queue, PAGE_ID, FIXTURE_TITLE, built_at
    )

    assert admitted is False
    assert await redis_client.llen(keys.QUEUE_BACKGROUND) == 0


async def test_rebuild_admitted_once_settled_and_quiet(redis_client: RedisClient) -> None:
    queue = _queue(redis_client)
    built_at = datetime.now(UTC) - timedelta(minutes=45)
    latest_rev_id = PINNED_REV_ID + 1
    await redis_client.set(keys.latest_rev(PAGE_ID), str(latest_rev_id))
    settled_edit = (datetime.now(UTC) - timedelta(minutes=10)).timestamp()
    await redis_client.zadd(keys.pageedits(PAGE_ID), {str(latest_rev_id): settled_edit})

    admitted = await freshness.maybe_enqueue_rebuild(
        redis_client, queue, PAGE_ID, FIXTURE_TITLE, built_at
    )

    assert admitted is True
    queued = await redis_client.lrange(keys.QUEUE_BACKGROUND, 0, -1)
    assert len(queued) == 1


async def test_second_call_within_debounce_window_is_a_no_op(redis_client: RedisClient) -> None:
    queue = _queue(redis_client)
    built_at = datetime.now(UTC) - timedelta(minutes=45)
    latest_rev_id = PINNED_REV_ID + 1
    await redis_client.set(keys.latest_rev(PAGE_ID), str(latest_rev_id))
    settled_edit = (datetime.now(UTC) - timedelta(minutes=10)).timestamp()
    await redis_client.zadd(keys.pageedits(PAGE_ID), {str(latest_rev_id): settled_edit})

    first = await freshness.maybe_enqueue_rebuild(
        redis_client, queue, PAGE_ID, FIXTURE_TITLE, built_at
    )
    second = await freshness.maybe_enqueue_rebuild(
        redis_client, queue, PAGE_ID, FIXTURE_TITLE, built_at
    )

    assert first is True
    assert second is False
    queued = await redis_client.lrange(keys.QUEUE_BACKGROUND, 0, -1)
    assert len(queued) == 1


async def test_no_rebuild_without_a_watcher_pointer(redis_client: RedisClient) -> None:
    queue = _queue(redis_client)
    built_at = datetime.now(UTC) - timedelta(minutes=45)

    admitted = await freshness.maybe_enqueue_rebuild(
        redis_client, queue, PAGE_ID, FIXTURE_TITLE, built_at
    )

    assert admitted is False


@pytest.mark.parametrize("latest_rev", ["not-a-number", None], ids=["malformed", "no-edit-record"])
async def test_no_rebuild_when_the_watcher_record_is_unusable(
    redis_client: RedisClient, latest_rev: str | None
) -> None:
    built_at = datetime.now(UTC) - timedelta(minutes=45)
    await redis_client.set(keys.latest_rev(PAGE_ID), latest_rev or str(PINNED_REV_ID + 1))

    admitted = await freshness.maybe_enqueue_rebuild(
        redis_client, _queue(redis_client), PAGE_ID, FIXTURE_TITLE, built_at
    )

    assert admitted is False
    assert await redis_client.llen(keys.QUEUE_BACKGROUND) == 0
