"""Wikimedia transport: the shared budget, the lock and the pacing between calls."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from tests.support.constants import (
    FIXTURE_TITLE,
    REQUIRED_ENV,
)
from tests.support.metrics import metric_sample
from tests.support.wikimedia import FakeClock, make_wikimedia_client, no_sleep
from wke.clients.redis import RedisClient
from wke.clients.wikimedia_transport import CallMode
from wke.core import keys
from wke.core.errors import ApiException

ACTION_API_URL = REQUIRED_ENV["WIKIPEDIA_API_URL"]
REST_API_URL = REQUIRED_ENV["WIKIPEDIA_REST_URL"]


async def test_budget_rejects_call_151(redis_client, wm_fixtures) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=wm_fixtures.json("search.json"))

    wall_clock = lambda: 0.0  # noqa: E731 - fixed epoch minute for every call
    client = make_wikimedia_client(
        redis_client, handler, wall_clock=wall_clock, sleep=no_sleep, budget_per_minute=150
    )

    for _ in range(150):
        await client.search(FIXTURE_TITLE, 8)

    with pytest.raises(ApiException) as exc_info:
        await client.search(FIXTURE_TITLE, 8)

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "upstream_budget"


async def test_budget_resets_next_minute(redis_client, wm_fixtures) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=wm_fixtures.json("search.json"))

    minute = {"value": 0.0}
    wall_clock = lambda: minute["value"]  # noqa: E731

    client = make_wikimedia_client(
        redis_client, handler, wall_clock=wall_clock, sleep=no_sleep, budget_per_minute=1
    )

    await client.search(FIXTURE_TITLE, 8)
    with pytest.raises(ApiException):
        await client.search(FIXTURE_TITLE, 8)

    minute["value"] = 60.0
    # Should succeed again in the new epoch minute bucket.
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
    ttl_after_first = await redis_client.ttl("wm:pace")
    assert ttl_after_first > 0

    await client.search(FIXTURE_TITLE, 8)

    assert any(s > 0 for s in sleeps)


async def test_pace_wait_happens_before_lock_is_taken(redis_client, wm_fixtures) -> None:
    """The lock must only be held for the request itself, not the pace delay.

    If the pace wait ran after the lock was taken, wm:lock would still be
    set while this sleep runs; asserting it is absent during the sleep
    pins the reordering that keeps the lock's hold time short.
    """
    await redis_client.set("wm:pace", "1", ex=5)
    observed_lock_during_sleep = []

    async def spy_sleep(seconds: float) -> None:
        observed_lock_during_sleep.append(await redis_client.get("wm:lock"))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=wm_fixtures.json("search.json"))

    client = make_wikimedia_client(redis_client, handler, sleep=spy_sleep)
    await client.search(FIXTURE_TITLE, 8)

    assert observed_lock_during_sleep == [None]
    assert await redis_client.get("wm:lock") is None


async def test_lock_release_does_not_delete_another_holders_lock(redis_client, wm_fixtures) -> None:
    """A stale release (its token no longer matches) must not evict a new holder."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=wm_fixtures.json("search.json"))

    client = make_wikimedia_client(redis_client, handler, sleep=no_sleep)
    await client.search(FIXTURE_TITLE, 8)

    # Simulate another caller having since taken the lock under its own token.
    await redis_client.set("wm:lock", "someone-elses-token", px=90_000)
    await client._release_lock("a-stale-token-this-client-no-longer-holds")

    assert await redis_client.get("wm:lock") == "someone-elses-token"


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
        sleep=no_sleep,
        budget_per_minute=3,
    )

    await client.search(FIXTURE_TITLE, 8)

    assert calls["count"] == 3
    with pytest.raises(ApiException) as exc_info:
        await client.search(FIXTURE_TITLE, 8)
    assert exc_info.value.code == "upstream_budget"


async def test_wikimedia_budget_rejection_is_counted(redis_client: RedisClient) -> None:
    before = metric_sample("wke_wikimedia_budget_rejections_total", {})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"query": {}})

    client = make_wikimedia_client(
        redis_client, handler, wall_clock=lambda: 0.0, budget_per_minute=1
    )
    await client.search(FIXTURE_TITLE, 8)
    with pytest.raises(ApiException):
        await client.search(FIXTURE_TITLE, 8)

    assert metric_sample("wke_wikimedia_budget_rejections_total", {}) == before + 1


@pytest.mark.parametrize(
    ("mode", "code", "retry_after"),
    [("inline", "upstream_budget", 2), ("worker", "upstream_unavailable", 5)],
)
async def test_a_lock_held_past_the_deadline_gives_up(
    redis_client: RedisClient, wm_fixtures, mode: CallMode, code: str, retry_after: int
) -> None:
    """An inline request asks the user to retry soon; a worker job fails as unavailable."""
    await redis_client.set(keys.WM_LOCK, "another-holder", px=keys.WM_LOCK_TTL_MS)
    clock = FakeClock()

    async def advancing_sleep(seconds: float) -> None:
        clock.advance(seconds)

    client = make_wikimedia_client(
        redis_client, lambda request: httpx.Response(500), clock=clock, sleep=advancing_sleep
    )
    with pytest.raises(ApiException) as caught:
        await client.revision_html(wm_fixtures.revision_id, mode=mode)

    assert (caught.value.code, caught.value.retry_after) == (code, retry_after)
    assert await redis_client.get(keys.WM_LOCK) == "another-holder"
