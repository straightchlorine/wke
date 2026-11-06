"""GET /api/v1/trending: snapshot, live edit counts and conditional GET."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from tests.support.apps import app_client
from tests.support.constants import FIXTURE_PAGE_ID, FIXTURE_REV_ID, FIXTURE_TITLE
from tests.support.snapshots import make_snapshot
from wke.core import keys
from wke.core.viewcache import invalidate_views


async def test_get_trending_no_snapshot_is_503(app) -> None:
    async with app_client(app) as client:
        response = await client.get("/api/v1/trending")

    assert response.status_code == 503
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "upstream_unavailable"
    assert ";" not in response.json()["detail"]
    assert response.json()["detail"] == ("No most-read snapshot yet. The nightly job has not run.")


async def test_get_trending_seeded_snapshot_is_200(app, fake_redis) -> None:

    await fake_redis.set(keys.TRENDING_LATEST, json.dumps(make_snapshot()))

    async with app_client(app) as client:
        response = await client.get("/api/v1/trending")

    assert response.status_code == 200
    assert "etag" in response.headers
    body = response.json()
    assert len(body["topics"]) == 1
    assert body["topics"][0]["title"] == FIXTURE_TITLE


async def test_get_trending_edits_last_hour_is_computed_live(app, fake_redis) -> None:
    """The Home card labels this "edits, last 1 h"; it must not be the
    all-time count frozen at the nightly snapshot."""

    await fake_redis.set(keys.TRENDING_LATEST, json.dumps(make_snapshot()))

    now = datetime.now(UTC).timestamp()
    await fake_redis.zadd(
        keys.pageedits(FIXTURE_PAGE_ID),
        {
            f"{FIXTURE_REV_ID}": now - 600,  # 10 min ago: within the last hour
            "1377040313": now - 7200,  # 2 h ago: outside the last hour
        },
    )

    async with app_client(app) as client:
        response = await client.get("/api/v1/trending")

    assert response.status_code == 200
    assert response.json()["topics"][0]["edits_last_hour"] == 1


async def test_get_trending_serves_a_full_forty_topics(app, fake_redis) -> None:
    template = make_snapshot()["topics"][0]
    topics = [{**template, "rank": rank, "page_id": 1000 + rank} for rank in range(1, 41)]
    await fake_redis.set(keys.TRENDING_LATEST, json.dumps(make_snapshot(topics=topics)))

    async with app_client(app) as client:
        response = await client.get("/api/v1/trending")

    assert [topic["rank"] for topic in response.json()["topics"]] == list(range(1, 41))


async def test_get_trending_etag_changes_with_a_topic_dossier_state(
    app, fake_redis, built_page
) -> None:
    snapshot = make_snapshot(page_id=built_page, views=1, rev_id=FIXTURE_REV_ID)
    await fake_redis.set(keys.TRENDING_LATEST, json.dumps(snapshot))

    async with app_client(app) as client:
        before = await client.get("/api/v1/trending")
        await fake_redis.delete(keys.ptr(built_page))
        invalidate_views()
        after = await client.get(
            "/api/v1/trending", headers={"If-None-Match": before.headers["etag"]}
        )

    assert before.json()["topics"][0]["dossier_state"] == "ready"
    assert after.status_code == 200
    assert after.json()["topics"][0]["dossier_state"] == "none"
    assert after.headers["etag"] != before.headers["etag"]
