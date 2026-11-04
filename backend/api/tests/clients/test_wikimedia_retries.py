"""Wikimedia transport: maxlag, unusable answers, rate limits, server and network failures."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest

from tests.support.constants import FIXTURE_TITLE
from tests.support.metrics import metric_sample
from tests.support.wikimedia import WmFixtures, make_wikimedia_client
from wke.clients.redis import RedisClient
from wke.clients.wikimedia import WikimediaClient
from wke.core.errors import ApiException

Answer = Callable[[httpx.Request], httpx.Response]
Call = Callable[[WikimediaClient], Awaitable[Any]]


def _maxlag(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200, json={"error": {"code": "maxlag", "info": "lag"}}, headers={"retry-after": "1"}
    )


def _too_many_requests(request: httpx.Request) -> httpx.Response:
    return httpx.Response(429, headers={"retry-after": "3"}, text="slow down")


def _bad_gateway(request: httpx.Request) -> httpx.Response:
    return httpx.Response(502, text="bad gateway")


def _network(error: type[httpx.RequestError]) -> Answer:
    def answer(request: httpx.Request) -> httpx.Response:
        raise error("no answer", request=request)

    return answer


class _Sleeps:
    """Records every sleep the client asks for instead of sleeping."""

    def __init__(self) -> None:
        self.seconds: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.seconds.append(seconds)


def _client(redis_client: RedisClient, answers: list[Answer], sleeps: _Sleeps) -> WikimediaClient:
    """A client whose Nth request gets answers[N], the last answer repeating."""
    served = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal served
        answer = answers[min(served, len(answers) - 1)]
        served += 1
        return answer(request)

    return make_wikimedia_client(redis_client, handler, sleep=sleeps)


async def test_action_api_calls_carry_maxlag_and_rest_calls_do_not(
    redis_client: RedisClient, wm_fixtures: WmFixtures
) -> None:
    params: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params.append(dict(request.url.params))
        if "/revision/" in request.url.path:
            return httpx.Response(
                200, text="<html/>", headers={"content-revision-id": str(wm_fixtures.revision_id)}
            )
        return httpx.Response(200, json=wm_fixtures.json("search.json"))

    client = make_wikimedia_client(redis_client, handler)
    await client.search(FIXTURE_TITLE, 8)
    await client.revision_html(wm_fixtures.revision_id)

    assert params[0]["maxlag"] == "5"
    assert "maxlag" not in params[1]


@pytest.mark.parametrize(
    ("call", "response"),
    [
        pytest.param(
            lambda c: c.resolve(FIXTURE_TITLE),
            httpx.Response(403, text="<html>Access denied</html>"),
            id="action-api-403-html",
        ),
        pytest.param(
            lambda c: c.resolve(FIXTURE_TITLE),
            httpx.Response(400, json={"error": {"code": "badtitle", "info": "Bad title."}}),
            id="action-api-error-object",
        ),
        pytest.param(
            lambda c: c.resolve(FIXTURE_TITLE),
            httpx.Response(200, text="<html>maintenance</html>"),
            id="action-api-200-html",
        ),
        pytest.param(
            lambda c: c.mostread("2026-09-27"),
            httpx.Response(403, json={"detail": "forbidden"}),
            id="wikifeeds-403",
        ),
        pytest.param(
            lambda c: c.pageviews_top("2026-09-26"),
            httpx.Response(200, text="<html>maintenance</html>"),
            id="pageviews-200-html",
        ),
        pytest.param(
            lambda c: c.pageviews_top("2026-09-26"),
            httpx.Response(200, json=["not", "an", "object"]),
            id="pageviews-json-list",
        ),
    ],
)
async def test_an_unusable_answer_is_upstream_unavailable(
    redis_client: RedisClient, call: Call, response: httpx.Response
) -> None:
    """Never passed on as an empty answer, which a caller would cache as real."""
    client = make_wikimedia_client(redis_client, lambda request: response)
    with pytest.raises(ApiException) as caught:
        await call(client)
    assert (caught.value.status_code, caught.value.code) == (503, "upstream_unavailable")


TRANSIENT = [
    pytest.param(_maxlag, id="maxlag"),
    pytest.param(_too_many_requests, id="429"),
    pytest.param(_bad_gateway, id="502"),
    pytest.param(_network(httpx.ConnectTimeout), id="connect-timeout"),
    pytest.param(_network(httpx.ReadTimeout), id="read-timeout"),
    pytest.param(_network(httpx.ConnectError), id="connect-refused"),
    pytest.param(_network(httpx.RemoteProtocolError), id="connection-dropped"),
]


@pytest.mark.parametrize("failure", TRANSIENT)
async def test_one_transient_failure_is_retried_and_the_answer_returned(
    redis_client: RedisClient, wm_fixtures: WmFixtures, failure: Answer
) -> None:
    def ok(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=wm_fixtures.json("search.json"))

    sleeps = _Sleeps()
    results = await _client(redis_client, [failure, ok], sleeps).search(FIXTURE_TITLE, 8)

    assert results[0]["title"] == FIXTURE_TITLE
    assert len(sleeps.seconds) == 1


@pytest.mark.parametrize(
    ("failure", "attempts", "code", "retry_after"),
    [
        pytest.param(_maxlag, 2, "upstream_rate_limited", 1, id="maxlag"),
        pytest.param(_too_many_requests, 2, "upstream_rate_limited", 3, id="429"),
        pytest.param(_bad_gateway, 3, "upstream_unavailable", 5, id="502"),
        pytest.param(_network(httpx.ConnectTimeout), 3, "upstream_unavailable", 5, id="timeout"),
        pytest.param(_network(httpx.ConnectError), 3, "upstream_unavailable", 5, id="refused"),
    ],
)
async def test_a_failure_that_persists_gives_up(
    redis_client: RedisClient, failure: Answer, attempts: int, code: str, retry_after: int
) -> None:
    """A rate limit is retried once, as Retry-After asks; a server or network
    failure up to three times, with a random 1-8 s wait between attempts."""
    requests = 0

    def counted(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return failure(request)

    sleeps = _Sleeps()
    with pytest.raises(ApiException) as caught:
        await _client(redis_client, [counted], sleeps).search(FIXTURE_TITLE, 8)

    assert requests == attempts
    assert (caught.value.status_code, caught.value.code) == (503, code)
    assert caught.value.retry_after == retry_after
    if code == "upstream_rate_limited":
        assert sleeps.seconds == [float(retry_after)]
    else:
        assert len(sleeps.seconds) == attempts - 1
        assert all(1.0 <= s <= 8.0 for s in sleeps.seconds)


@pytest.mark.parametrize(
    ("retry_after", "slept"),
    [("3", 3.0), ("120", 30.0), ("soon", 5.0), (None, 5.0)],
    ids=["honoured", "capped-at-30s", "unreadable-uses-5s", "missing-uses-5s"],
)
async def test_a_rate_limit_waits_as_retry_after_asks(
    redis_client: RedisClient, wm_fixtures: WmFixtures, retry_after: str | None, slept: float
) -> None:
    """Capped, so a hostile header cannot hold the shared lock past its expiry."""

    def limited(request: httpx.Request) -> httpx.Response:
        headers = {"retry-after": retry_after} if retry_after is not None else {}
        return httpx.Response(429, headers=headers)

    def ok(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=wm_fixtures.json("search.json"))

    sleeps = _Sleeps()
    await _client(redis_client, [limited, ok], sleeps).search(FIXTURE_TITLE, 8)

    assert sleeps.seconds == [slept]


async def test_a_network_failure_is_counted(redis_client: RedisClient) -> None:
    labels = {"op": "action", "status": "network_error"}
    before = metric_sample("wke_wikimedia_requests_total", labels)

    with pytest.raises(ApiException):
        await _client(redis_client, [_network(httpx.ConnectError)], _Sleeps()).search("X", 8)

    assert metric_sample("wke_wikimedia_requests_total", labels) == before + 3
