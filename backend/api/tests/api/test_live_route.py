"""GET /api/v1/live: live edit counters and the since parameter."""

from __future__ import annotations

from datetime import UTC, datetime

import limits

from tests.support.apps import app_client
from tests.support.redis_counting import count_redis
from wke.api.ratelimit import LIVE_RATE_LIMIT
from wke.core import keys
from wke.core.models import EditEvent


async def test_get_live_empty_is_200_no_store(app) -> None:
    async with app_client(app) as client:
        response = await client.get("/api/v1/live")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["edits"] == []


async def test_get_live_returns_only_edits_after_since(app, fake_redis) -> None:
    for cursor in (1, 2, 3):
        event = EditEvent(
            cursor=cursor,
            title=f"Edited page {cursor}",
            rev_new=cursor,
            ts=datetime.now(UTC),
            user_kind="registered",
        )
        await fake_redis.lpush(keys.EDITS_RING, event.model_dump_json())
    await fake_redis.set(keys.EDITS_SEQ, "3")

    async with app_client(app) as client:
        everything = await client.get("/api/v1/live")
        later = await client.get("/api/v1/live", params={"since": 1})

    assert [edit["cursor"] for edit in everything.json()["edits"]] == [3, 2, 1]
    assert [edit["cursor"] for edit in later.json()["edits"]] == [3, 2]
    assert later.json()["cursor"] == 3


async def test_get_live_bad_since_is_422(app) -> None:
    async with app_client(app) as client:
        response = await client.get("/api/v1/live", params={"since": -1})

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


async def test_live_counters_use_one_mget_and_sum_buckets(app, fake_redis, monkeypatch) -> None:
    frozen = datetime(2026, 9, 28, 12, 0, 30, tzinfo=UTC)

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen

    monkeypatch.setattr("wke.services.live.datetime", FrozenDatetime)
    now = frozen.timestamp()
    await fake_redis.set(keys.rc_counter("enwiki", keys.minute_bucket(now)), "7")
    await fake_redis.set(keys.rc_counter("enwiki", keys.minute_bucket(now - 60)), "5")
    await fake_redis.set(keys.rc_counter("tracked", keys.minute_bucket(now)), "2")

    async with app_client(app) as client:
        counter = count_redis(app)
        response = await client.get("/api/v1/live")

    counters = response.json()["counters"]
    assert counters["enwiki_edits_last_hour"] == 12
    assert counters["tracked_edits_last_hour"] == 2
    assert counter.calls.count("mget") == 1
    assert counter.calls.count("get") <= 2


async def test_live_429_carries_retry_after(app) -> None:
    item = limits.parse(LIVE_RATE_LIMIT)
    for _ in range(item.amount):
        assert app.state.limiter.limiter.hit(item, "127.0.0.1", "/api/v1/live")

    async with app_client(app) as client:
        response = await client.get("/api/v1/live")

    assert response.status_code == 429
    assert response.headers["retry-after"] == "60"
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["retry_after"] == 60
