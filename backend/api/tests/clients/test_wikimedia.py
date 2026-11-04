"""WikimediaClient calls: request parameters and the answers they return.

Runs against the recorded article fixtures through httpx.MockTransport.
"""

from __future__ import annotations

import httpx
import pytest

from tests.support.constants import (
    FIXTURE_PAGE_ID,
    FIXTURE_REV_ID,
    FIXTURE_REV_TIMESTAMP,
    FIXTURE_TITLE,
    REQUIRED_ENV,
)
from tests.support.wikimedia import make_wikimedia_client, no_sleep
from wke.clients.redis import RedisClient
from wke.clients.user_agent import build_user_agent
from wke.clients.wikimedia import WikifeedsNotFound
from wke.core.errors import ApiException

ACTION_API_URL = REQUIRED_ENV["WIKIPEDIA_API_URL"]
REST_API_URL = REQUIRED_ENV["WIKIPEDIA_REST_URL"]


async def test_user_agent_format(settings, redis_client, wm_fixtures) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["ua"] = request.headers.get("user-agent")
        return httpx.Response(200, json=wm_fixtures.json("search.json"))

    client = make_wikimedia_client(redis_client, handler, sleep=no_sleep)
    await client.search(FIXTURE_TITLE, 8)

    assert seen["ua"] == build_user_agent()
    assert seen["ua"].startswith("wke/")
    assert "httpx/" in seen["ua"]
    assert settings.wke_contact_email in seen["ua"]


async def test_gzip_accepted(redis_client, wm_fixtures) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["accept_encoding"] = request.headers.get("accept-encoding", "")
        return httpx.Response(200, json=wm_fixtures.json("search.json"))

    client = make_wikimedia_client(redis_client, handler, sleep=no_sleep)
    await client.search(FIXTURE_TITLE, 8)

    assert "gzip" in seen["accept_encoding"]


async def test_search_returns_results(redis_client, wm_fixtures) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=wm_fixtures.json("search.json"))

    client = make_wikimedia_client(redis_client, handler, sleep=no_sleep)
    results = await client.search(FIXTURE_TITLE, 8)

    assert results[0]["title"] == FIXTURE_TITLE
    assert results[0]["pageid"] == FIXTURE_PAGE_ID


async def test_resolve_returns_page(redis_client, wm_fixtures) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=wm_fixtures.json("resolve.json"))

    client = make_wikimedia_client(redis_client, handler, sleep=no_sleep)
    page = await client.resolve(FIXTURE_TITLE)

    assert page["pageid"] == FIXTURE_PAGE_ID
    assert page["ns"] == 0


async def test_morelike_returns_pages(redis_client, wm_fixtures) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=wm_fixtures.json("morelike.json"))

    client = make_wikimedia_client(redis_client, handler, sleep=no_sleep)
    pages = await client.morelike(FIXTURE_TITLE)

    assert isinstance(pages, list)
    assert len(pages) > 0


async def test_revision_timestamp_returns_real_edit_time(redis_client, wm_fixtures) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=wm_fixtures.json("revision.json"))

    client = make_wikimedia_client(redis_client, handler, sleep=no_sleep)
    timestamp = await client.revision_timestamp(FIXTURE_REV_ID)

    assert timestamp == FIXTURE_REV_TIMESTAMP


async def test_revision_timestamp_missing_raises(redis_client) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"query": {"pages": [{"pageid": 1, "ns": 0}]}})

    client = make_wikimedia_client(redis_client, handler, sleep=no_sleep)

    with pytest.raises(ApiException) as exc_info:
        await client.revision_timestamp(999)

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "upstream_unavailable"


async def test_content_revision_id_mismatch_raises(redis_client, wm_fixtures) -> None:
    rev_id = wm_fixtures.revision_id

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=wm_fixtures.text("parsoid.html").encode("utf-8"),
            headers={"content-revision-id": "999999999"},
        )

    client = make_wikimedia_client(redis_client, handler, sleep=no_sleep)
    with pytest.raises(ApiException) as exc_info:
        await client.revision_html(rev_id)

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "upstream_unavailable"


async def test_revision_html_body_cap(redis_client) -> None:
    oversized = b"x" * (5 * 1024 * 1024 + 1)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=oversized, headers={"content-revision-id": "1"})

    client = make_wikimedia_client(redis_client, handler, sleep=no_sleep)
    with pytest.raises(ApiException) as exc_info:
        await client.revision_html(1)

    assert exc_info.value.code == "upstream_unavailable"


async def test_mostread_requests_the_dated_feed_and_returns_its_list(
    redis_client: RedisClient, wm_fixtures
) -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(200, json={"mostread": wm_fixtures.json("mostread.json")})

    client = make_wikimedia_client(redis_client, handler)
    mostread = await client.mostread("2026-09-27")

    assert paths == ["/api/rest_v1/feed/featured/2026/09/27"]
    assert mostread == wm_fixtures.json("mostread.json")


async def test_mostread_not_published_yet_raises(redis_client: RedisClient) -> None:
    client = make_wikimedia_client(redis_client, lambda request: httpx.Response(404))
    with pytest.raises(WikifeedsNotFound) as caught:
        await client.mostread("2026-09-27")
    assert caught.value.date == "2026-09-27"


async def test_pageviews_top_returns_the_first_item_or_no_articles(
    redis_client: RedisClient, wm_fixtures
) -> None:
    recorded = wm_fixtures.json("pageviews_top.json")
    client = make_wikimedia_client(redis_client, lambda request: httpx.Response(200, json=recorded))
    assert await client.pageviews_top("2026-09-26") == recorded["items"][0]

    empty = make_wikimedia_client(redis_client, lambda request: httpx.Response(200, json={}))
    assert await empty.pageviews_top("2026-09-26") == {"articles": []}


async def test_page_extracts_asks_for_at_most_20_titles(redis_client: RedisClient) -> None:
    params: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params.append(dict(request.url.params))
        return httpx.Response(200, json={"query": {"pages": [{"pageid": 1}]}})

    client = make_wikimedia_client(redis_client, handler)
    pages = await client.page_extracts([f"Title {n}" for n in range(25)])

    assert pages == [{"pageid": 1}]
    assert params[0]["titles"].split("|") == [f"Title {n}" for n in range(20)]
    assert params[0]["exlimit"] == "20"
