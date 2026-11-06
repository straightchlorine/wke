"""In-process caching, ETag and 304 for the dossier list and trending views."""

from __future__ import annotations

import json

from tests.support.apps import app_client
from tests.support.redis_counting import count_redis
from tests.support.snapshots import make_snapshot
from wke.core import keys
from wke.core.viewcache import invalidate_views


async def test_list_route_warm_cache_makes_no_redis_calls(app, built_page) -> None:
    async with app_client(app) as client:
        counter = count_redis(app)
        first = await client.get("/api/v1/dossiers")
        cold_calls = len(counter.calls)
        second = await client.get("/api/v1/dossiers")
        third = await client.get("/api/v1/dossiers", params={"q": "turing", "limit": 5})

    assert first.status_code == second.status_code == third.status_code == 200
    assert first.json() == second.json()
    assert len(counter.calls) == cold_calls
    assert counter.calls.count("zrevrange") == 1


async def test_list_cache_is_dropped_when_a_build_finishes(app, built_page, fake_redis) -> None:
    async with app_client(app) as client:
        first = await client.get("/api/v1/dossiers")
        await fake_redis.delete(keys.BUILT)
        stale = await client.get("/api/v1/dossiers")
        invalidate_views()
        fresh = await client.get("/api/v1/dossiers")

    assert len(first.json()["items"]) == 1
    assert stale.json() == first.json()
    assert fresh.json()["items"] == []


async def test_trending_warm_hits_make_no_redis_calls(app, fake_redis, built_page) -> None:
    await fake_redis.set(
        keys.TRENDING_LATEST, json.dumps(make_snapshot(page_id=built_page, views=1, rev_id=1))
    )

    async with app_client(app) as client:
        counter = count_redis(app)
        first = await client.get("/api/v1/trending")
        cold_calls = list(counter.calls)
        etag = first.headers["etag"]
        second = await client.get("/api/v1/trending", headers={"If-None-Match": etag})
        third = await client.get("/api/v1/trending")

    assert first.json()["topics"][0]["dossier_state"] == "ready"
    assert cold_calls
    assert second.status_code == 304
    assert third.json() == first.json()
    assert counter.calls == cold_calls
