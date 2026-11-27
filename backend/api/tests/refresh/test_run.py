"""The refresh run: what it extends, rebuilds, skips and leaves, and in which order."""

from __future__ import annotations

import pytest
from fakeredis.aioredis import FakeRedis

from tests.support.constants import PIPELINE_VERSION
from tests.support.refresh import DAY, FakeTime, make_stale, store
from wke.clients.redis import RedisClient
from wke.core import keys
from wke.core.citations import seed_pin
from wke.jobs.build.rating import rating_key
from wke.jobs.queue import JobQueue
from wke.refresh import run as refresh
from wke.refresh.run import RefreshSummary, run_refresh


def _queue(redis_client: RedisClient, cap: int = 50) -> JobQueue:
    return JobQueue(redis_client, PIPELINE_VERSION, cap, cap)


async def _run(
    fake_redis: FakeRedis,
    redis_client: RedisClient,
    fake_time: FakeTime | None = None,
    queue: JobQueue | None = None,
) -> RefreshSummary:
    fake_time = fake_time or FakeTime()
    return await run_refresh(
        fake_redis,
        redis_client,
        queue or _queue(redis_client),
        PIPELINE_VERSION,
        sleep=fake_time.sleep,
        clock=fake_time.clock,
    )


async def _ttl(fake_redis: FakeRedis, page_id: int, rev_id: int) -> int:
    return await fake_redis.ttl(keys.dossier(page_id, rev_id, PIPELINE_VERSION))


async def test_the_limits_are_the_documented_ones() -> None:
    assert refresh.EXPIRY_WINDOW_SECONDS == 2 * DAY
    assert refresh.MAX_REBUILDS_PER_RUN == 200
    assert refresh.REBUILD_PHASE_SECONDS == 30 * 60
    assert refresh.QUEUE_FULL_WAIT_SECONDS == 30


async def test_a_fresh_dossier_close_to_expiry_gets_the_full_lifetime_and_nothing_else(
    fake_redis: FakeRedis, redis_client: RedisClient
) -> None:
    dossier = await store(redis_client, fake_redis, 11, DAY)
    rev_id = seed_pin(dossier).rev_id
    key = keys.dossier(11, rev_id, PIPELINE_VERSION)
    value, pointer = await fake_redis.get(key), await fake_redis.get(keys.ptr(11))
    built = await fake_redis.zscore(keys.BUILT, "11")

    summary = await _run(fake_redis, redis_client)

    assert (summary.stored, summary.extended, summary.left_alone) == (1, 1, 0)
    assert await _ttl(fake_redis, 11, rev_id) == keys.DOSSIER_TTL_SECONDS
    assert await fake_redis.get(key) == value
    assert await fake_redis.get(keys.ptr(11)) == pointer
    assert await fake_redis.zscore(keys.BUILT, "11") == built
    assert await fake_redis.ttl(keys.ptr(11)) == -1


async def test_a_dossier_with_more_than_two_days_left_is_not_touched(
    fake_redis: FakeRedis, redis_client: RedisClient
) -> None:
    dossier = await store(redis_client, fake_redis, 12, 3 * DAY)
    rev_id = seed_pin(dossier).rev_id

    summary = await _run(fake_redis, redis_client)

    assert (summary.extended, summary.left_alone) == (0, 1)
    assert 3 * DAY - 5 <= await _ttl(fake_redis, 12, rev_id) <= 3 * DAY


async def test_the_rating_of_an_extended_dossier_is_extended_with_it(
    fake_redis: FakeRedis, redis_client: RedisClient
) -> None:
    dossier = await store(redis_client, fake_redis, 13, DAY, rating=True)
    rev_id = seed_pin(dossier).rev_id

    await _run(fake_redis, redis_client)

    assert (
        await fake_redis.ttl(rating_key(13, rev_id, PIPELINE_VERSION)) == keys.DOSSIER_TTL_SECONDS
    )


async def test_a_stale_dossier_within_the_window_is_asked_to_rebuild_and_extended(
    fake_redis: FakeRedis, redis_client: RedisClient
) -> None:
    dossier = await store(redis_client, fake_redis, 14, DAY)
    rev_id = seed_pin(dossier).rev_id
    await make_stale(redis_client, dossier)

    summary = await _run(fake_redis, redis_client)

    assert (summary.stale, summary.admitted, summary.extended, summary.left_alone) == (1, 1, 1, 0)
    assert await redis_client.llen(keys.QUEUE_BACKGROUND) == 1
    assert await _ttl(fake_redis, 14, rev_id) == keys.DOSSIER_TTL_SECONDS


async def test_a_stale_dossier_with_more_than_the_window_left_is_asked_and_not_extended(
    fake_redis: FakeRedis, redis_client: RedisClient
) -> None:
    dossier = await store(redis_client, fake_redis, 21, 4 * DAY)
    rev_id = seed_pin(dossier).rev_id
    await make_stale(redis_client, dossier)

    summary = await _run(fake_redis, redis_client)

    assert (summary.stale, summary.admitted, summary.extended, summary.left_alone) == (1, 1, 0, 0)
    assert 4 * DAY - 5 <= await _ttl(fake_redis, 21, rev_id) <= 4 * DAY


async def test_a_stale_dossier_with_more_than_the_window_left_and_no_ask_is_left_alone(
    fake_redis: FakeRedis, redis_client: RedisClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(refresh, "MAX_REBUILDS_PER_RUN", 0)
    await make_stale(redis_client, await store(redis_client, fake_redis, 22, 4 * DAY))

    summary = await _run(fake_redis, redis_client)

    assert (summary.stale, summary.deferred, summary.extended, summary.left_alone) == (1, 1, 0, 1)


async def test_a_stale_dossier_in_its_debounce_is_counted_as_refused(
    fake_redis: FakeRedis, redis_client: RedisClient
) -> None:
    dossier = await store(redis_client, fake_redis, 15, DAY)
    await make_stale(redis_client, dossier)
    await redis_client.set(keys.rebuild_debounce(15), "1", ex=600)

    summary = await _run(fake_redis, redis_client)

    assert (summary.stale, summary.admitted, summary.refused, summary.extended) == (1, 0, 1, 1)
    assert await redis_client.llen(keys.QUEUE_BACKGROUND) == 0


async def test_a_page_whose_dossier_key_is_gone_is_skipped(
    fake_redis: FakeRedis, redis_client: RedisClient
) -> None:
    dossier = await store(redis_client, fake_redis, 16, DAY)
    await fake_redis.delete(keys.dossier(16, seed_pin(dossier).rev_id, PIPELINE_VERSION))

    summary = await _run(fake_redis, redis_client)

    assert (summary.stored, summary.skipped, summary.extended) == (0, 1, 0)


async def test_a_page_with_no_pointer_is_skipped(
    fake_redis: FakeRedis, redis_client: RedisClient
) -> None:
    await store(redis_client, fake_redis, 17, DAY)
    await fake_redis.delete(keys.ptr(17))

    summary = await _run(fake_redis, redis_client)

    assert (summary.stored, summary.skipped) == (0, 1)


async def test_a_dossier_of_another_pipeline_version_is_skipped(
    fake_redis: FakeRedis, redis_client: RedisClient
) -> None:
    dossier = await store(redis_client, fake_redis, 18, DAY, pipeline_version="older-pv")
    rev_id = seed_pin(dossier).rev_id

    summary = await _run(fake_redis, redis_client)

    assert (summary.stored, summary.skipped, summary.extended) == (0, 1, 0)
    assert 0 < await fake_redis.ttl(keys.dossier(18, rev_id, "older-pv")) <= DAY


async def test_a_structural_dossier_is_left_to_expire(
    fake_redis: FakeRedis, redis_client: RedisClient
) -> None:
    dossier = await store(redis_client, fake_redis, 19, 300, analysis="structural")
    rev_id = seed_pin(dossier).rev_id

    summary = await _run(fake_redis, redis_client)

    assert (summary.stored, summary.skipped, summary.extended) == (0, 1, 0)
    assert await _ttl(fake_redis, 19, rev_id) <= 300


async def test_an_unreadable_dossier_is_skipped(
    fake_redis: FakeRedis, redis_client: RedisClient
) -> None:
    dossier = await store(redis_client, fake_redis, 20, DAY)
    await fake_redis.set(keys.dossier(20, seed_pin(dossier).rev_id, PIPELINE_VERSION), "{}", ex=DAY)

    summary = await _run(fake_redis, redis_client)

    assert (summary.stored, summary.skipped) == (0, 1)


async def test_the_dossiers_closest_to_expiry_come_first(
    fake_redis: FakeRedis, redis_client: RedisClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    order: list[int] = []

    async def record(_redis, _queue, page_id, _title, _built_at) -> bool:
        order.append(page_id)
        return True

    monkeypatch.setattr(refresh, "maybe_enqueue_rebuild", record)
    for page_id, left in ((31, 5 * DAY), (32, DAY), (33, 3 * DAY), (34, 100)):
        await make_stale(redis_client, await store(redis_client, fake_redis, page_id, left))

    await _run(fake_redis, redis_client)

    assert order == [34, 32, 33, 31]


async def test_rebuilds_stop_at_the_limit_and_the_rest_waits_for_the_next_run(
    fake_redis: FakeRedis, redis_client: RedisClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(refresh, "MAX_REBUILDS_PER_RUN", 2)
    for page_id in (41, 42, 43, 44):
        await make_stale(redis_client, await store(redis_client, fake_redis, page_id, DAY))
    fresh = await store(redis_client, fake_redis, 45, DAY + 10)

    summary = await _run(fake_redis, redis_client)

    assert (summary.stale, summary.admitted, summary.deferred) == (4, 2, 2)
    assert await redis_client.llen(keys.QUEUE_BACKGROUND) == 2
    # Every dossier is within the window, so all five are extended, the deferred ones too.
    assert summary.extended == 5
    assert await _ttl(fake_redis, 45, seed_pin(fresh).rev_id) == keys.DOSSIER_TTL_SECONDS


async def test_rebuilds_stop_after_thirty_minutes(
    fake_redis: FakeRedis, redis_client: RedisClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_time = FakeTime()
    asked: list[int] = []

    async def slow(_redis, _queue, page_id, _title, _built_at) -> bool:
        asked.append(page_id)
        fake_time.now += 20 * 60
        return True

    monkeypatch.setattr(refresh, "maybe_enqueue_rebuild", slow)
    for page_id, left in ((51, 100), (52, 200), (53, 300)):
        await make_stale(redis_client, await store(redis_client, fake_redis, page_id, left))

    summary = await _run(fake_redis, redis_client, fake_time)

    assert asked == [51, 52]
    assert (summary.admitted, summary.deferred, summary.extended) == (2, 1, 3)


async def test_a_full_queue_waits_thirty_seconds_and_goes_on(
    fake_redis: FakeRedis, redis_client: RedisClient
) -> None:
    fake_time = FakeTime()
    for page_id, left in ((61, 100), (62, 200), (63, 300)):
        await make_stale(redis_client, await store(redis_client, fake_redis, page_id, left))

    summary = await _run(fake_redis, redis_client, fake_time, _queue(redis_client, cap=1))

    assert (summary.admitted, summary.deferred, summary.extended) == (1, 2, 3)
    assert fake_time.sleeps == [30, 30]
    assert await redis_client.llen(keys.QUEUE_BACKGROUND) == 1
