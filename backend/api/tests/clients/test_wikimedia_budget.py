"""Wikimedia transport: the shared budget, the lock and the pacing between calls."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from tests.support.constants import (
    FIXTURE_TITLE,
)
from tests.support.metrics import metric_sample
from tests.support.wikimedia import FakeClock, make_wikimedia_client
from wke.clients.redis import RedisClient
from wke.core import keys
from wke.core.errors import ApiException


async def test_budget_resets_next_minute(redis_client, wm_fixtures) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=wm_fixtures.json("search.json"))

    minute = {"value": 0.0}
    wall_clock = lambda: minute["value"]  # noqa: E731

    client = make_wikimedia_client(
        redis_client, handler, wall_clock=wall_clock, budget_per_minute=1
    )

    await client.search(FIXTURE_TITLE, 8)
    with pytest.raises(ApiException):
        await client.search(FIXTURE_TITLE, 8)

    minute["value"] = 60.0
    # The next minute has a budget of its own.
    await client.search(FIXTURE_TITLE, 8)


async def test_lock_serialises_20_concurrent_callers(redis_client, wm_fixtures) -> None:
    in_flight = 0
    peak = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return httpx.Response(200, json=wm_fixtures.json("search.json"))

    # Real sleeps: the 20 callers must yield to each other while the lock is held.
    client = make_wikimedia_client(
        redis_client, handler, sleep=asyncio.sleep, budget_per_minute=1000
    )

    await asyncio.gather(*(client.search(FIXTURE_TITLE, 8) for _ in range(20)))

    assert peak == 1


async def test_pacing_waits_after_slow_call(redis_client, wm_fixtures) -> None:
    clock = FakeClock(0.0)
    sleeps = []

    async def spy_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        # A real clock would have advanced by roughly `seconds`; a fake one
        # does not, so nudge it forward to keep _call's elapsed math sane.
        clock.advance(seconds)

    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] == 1:
            clock.advance(1.5)  # first call "took" 1.5s
        return httpx.Response(200, json=wm_fixtures.json("search.json"))

    client = make_wikimedia_client(redis_client, handler, clock=clock, sleep=spy_sleep)

    await client.search(FIXTURE_TITLE, 8)
    ttl_after_first = await redis_client.ttl(keys.WM_PACE)
    assert ttl_after_first > 0

    await client.search(FIXTURE_TITLE, 8)

    # The second call waited out the whole pause the slow first call set.
    assert sleeps == [float(keys.WM_PACE_TTL_SECONDS)]


async def test_pace_wait_happens_before_lock_is_taken(redis_client, wm_fixtures) -> None:
    """The pause after a slow call runs before the lock is taken, so other processes
    are never kept waiting on the lock through it."""
    await redis_client.set(keys.WM_PACE, "1", ex=keys.WM_PACE_TTL_SECONDS)
    observed_lock_during_sleep = []

    async def spy_sleep(seconds: float) -> None:
        observed_lock_during_sleep.append(await redis_client.get(keys.WM_LOCK))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=wm_fixtures.json("search.json"))

    client = make_wikimedia_client(redis_client, handler, sleep=spy_sleep)
    await client.search(FIXTURE_TITLE, 8)

    assert observed_lock_during_sleep == [None]
    assert await redis_client.get(keys.WM_LOCK) is None


async def test_lock_release_does_not_delete_another_holders_lock(redis_client, wm_fixtures) -> None:
    """A stale release (its token no longer matches) must not evict a new holder."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=wm_fixtures.json("search.json"))

    client = make_wikimedia_client(redis_client, handler)
    await client.search(FIXTURE_TITLE, 8)

    # Simulate another caller having since taken the lock under its own token.
    await redis_client.set(keys.WM_LOCK, "someone-elses-token", px=90_000)
    await client._release_lock("a-stale-token-this-client-no-longer-holds")

    assert await redis_client.get(keys.WM_LOCK) == "someone-elses-token"


async def test_retries_are_counted_against_the_shared_budget(redis_client, wm_fixtures) -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] < 3:
            return httpx.Response(500, text="oops")
        return httpx.Response(200, json=wm_fixtures.json("search.json"))

    wall_clock = lambda: 0.0  # noqa: E731
    # 2 retries + 1 success = 3 HTTP requests for a single search() call;
    # a budget of 3 must be exhausted, not merely "1 call = 1 unit".
    client = make_wikimedia_client(
        redis_client,
        handler,
        wall_clock=wall_clock,
        budget_per_minute=3,
    )

    await client.search(FIXTURE_TITLE, 8)

    assert calls["count"] == 3
    with pytest.raises(ApiException) as exc_info:
        await client.search(FIXTURE_TITLE, 8)
    assert exc_info.value.code == "upstream_budget"


async def test_a_call_over_the_budget_is_rejected_and_counted(
    redis_client: RedisClient, wm_fixtures
) -> None:
    before = metric_sample("wke_wikimedia_budget_rejections_total", {})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=wm_fixtures.json("search.json"))

    client = make_wikimedia_client(
        redis_client, handler, wall_clock=lambda: 0.0, budget_per_minute=3
    )
    for _ in range(3):
        await client.search(FIXTURE_TITLE, 8)
    with pytest.raises(ApiException) as caught:
        await client.search(FIXTURE_TITLE, 8)

    assert (caught.value.code, caught.value.retry_after) == ("upstream_budget", 60)
    assert metric_sample("wke_wikimedia_budget_rejections_total", {}) == before + 1
