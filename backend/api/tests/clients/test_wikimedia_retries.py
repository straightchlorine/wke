"""Wikimedia transport: maxlag, unusable bodies, rate limits and 5xx retries."""

from __future__ import annotations

import httpx
import pytest

from tests.support.constants import (
    FIXTURE_TITLE,
    REQUIRED_ENV,
)
from tests.support.wikimedia import make_wikimedia_client, no_sleep
from wke.core.errors import ApiException

ACTION_API_URL = REQUIRED_ENV["WIKIPEDIA_API_URL"]
REST_API_URL = REQUIRED_ENV["WIKIPEDIA_REST_URL"]


async def test_search_params_include_maxlag(redis_client, wm_fixtures) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json=wm_fixtures.json("search.json"))

    client = make_wikimedia_client(redis_client, handler, sleep=no_sleep)
    await client.search(FIXTURE_TITLE, 8)

    assert seen["params"]["maxlag"] == "5"
    assert seen["params"]["action"] == "query"
    assert seen["params"]["generator"] == "search"
    assert seen["params"]["gsrsearch"] == FIXTURE_TITLE
    assert seen["params"]["prop"] == "pageprops"
    assert seen["params"]["ppprop"] == "disambiguation"


async def test_revision_html_has_no_maxlag_param(redis_client, wm_fixtures) -> None:
    seen = {}
    rev_id = wm_fixtures.revision_id

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            content=wm_fixtures.text("parsoid.html").encode("utf-8"),
            headers={"content-revision-id": str(rev_id)},
        )

    client = make_wikimedia_client(redis_client, handler, sleep=no_sleep)
    await client.revision_html(rev_id)

    assert "maxlag" not in seen["params"]


async def test_resolve_403_html_body_raises_upstream_unavailable(redis_client) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            text="<html><body>Access denied</body></html>",
            headers={"content-type": "text/html"},
        )

    client = make_wikimedia_client(redis_client, handler, sleep=no_sleep)

    with pytest.raises(ApiException) as exc_info:
        await client.resolve(FIXTURE_TITLE)

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "upstream_unavailable"


async def test_resolve_400_json_error_body_raises_upstream_unavailable(redis_client) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"code": "badtitle", "info": "Bad title."}})

    client = make_wikimedia_client(redis_client, handler, sleep=no_sleep)

    with pytest.raises(ApiException) as exc_info:
        await client.resolve(FIXTURE_TITLE)

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "upstream_unavailable"


async def test_maxlag_body_on_200_retries_once_then_503(redis_client) -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(
            200,
            json={"error": {"code": "maxlag", "info": "lag"}},
            headers={"retry-after": "1"},
        )

    sleeps = []

    async def spy_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    client = make_wikimedia_client(redis_client, handler, sleep=spy_sleep)
    with pytest.raises(ApiException) as exc_info:
        await client.search(FIXTURE_TITLE, 8)

    assert calls["count"] == 2
    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "upstream_rate_limited"
    assert exc_info.value.retry_after == 1
    assert sleeps == [1.0]


async def test_maxlag_body_retry_succeeds(redis_client, wm_fixtures) -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(200, json={"error": {"code": "maxlag", "info": "lag"}})
        return httpx.Response(200, json=wm_fixtures.json("search.json"))

    client = make_wikimedia_client(redis_client, handler, sleep=no_sleep)
    results = await client.search(FIXTURE_TITLE, 8)

    assert calls["count"] == 2
    assert results[0]["title"] == FIXTURE_TITLE


async def test_429_retry_after_honoured_then_succeeds(redis_client, wm_fixtures) -> None:
    calls = {"count": 0}
    sleeps = []

    async def spy_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(429, headers={"retry-after": "3"}, text="slow down")
        return httpx.Response(200, json=wm_fixtures.json("search.json"))

    client = make_wikimedia_client(redis_client, handler, sleep=spy_sleep)
    results = await client.search(FIXTURE_TITLE, 8)

    assert calls["count"] == 2
    assert sleeps == [3.0]
    assert results[0]["title"] == FIXTURE_TITLE


async def test_429_twice_raises_upstream_rate_limited(redis_client) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"retry-after": "2"}, text="slow down")

    client = make_wikimedia_client(redis_client, handler, sleep=no_sleep)
    with pytest.raises(ApiException) as exc_info:
        await client.search(FIXTURE_TITLE, 8)

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "upstream_rate_limited"
    assert exc_info.value.retry_after == 2


async def test_5xx_retries_three_times_then_503(redis_client) -> None:
    calls = {"count": 0}
    sleeps = []

    async def spy_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(502, text="bad gateway")

    client = make_wikimedia_client(redis_client, handler, sleep=spy_sleep)
    with pytest.raises(ApiException) as exc_info:
        await client.search(FIXTURE_TITLE, 8)

    assert calls["count"] == 3
    assert exc_info.value.code == "upstream_unavailable"
    assert len(sleeps) == 2
    assert all(1.0 <= s <= 8.0 for s in sleeps)


async def test_5xx_then_success(redis_client, wm_fixtures) -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(500, text="oops")
        return httpx.Response(200, json=wm_fixtures.json("search.json"))

    client = make_wikimedia_client(redis_client, handler, sleep=no_sleep)
    results = await client.search(FIXTURE_TITLE, 8)

    assert calls["count"] == 2
    assert results[0]["title"] == FIXTURE_TITLE
