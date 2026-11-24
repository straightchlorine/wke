"""wke.clients.ml.MLClient: every failure mode degrades to MLUnavailable.

A raised MLUnavailable is what lets the pipeline fall back to structural
mode instead of getting stuck; anything that escapes as a different
exception type breaks that fallback.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from wke.clients.ml import MLClient, MLUnavailable
from wke.logging_setup import request_id_var


def _client(handler) -> MLClient:
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport, base_url="http://wke-ml.test")
    return MLClient(http)


async def test_timeout_raises_ml_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow")

    with pytest.raises(MLUnavailable) as exc_info:
        await _client(handler).summarize("some text")
    assert exc_info.value.reason == "timeout"


async def test_connect_error_raises_ml_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(MLUnavailable) as exc_info:
        await _client(handler).summarize("some text")
    assert exc_info.value.reason == "connect_error"


async def test_remote_protocol_error_raises_ml_unavailable() -> None:
    """wke-ml dropped mid-request (a restart), not a timeout or connect error."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.RemoteProtocolError("peer closed connection")

    with pytest.raises(MLUnavailable) as exc_info:
        await _client(handler).summarize("some text")
    assert exc_info.value.reason == "RemoteProtocolError"


async def test_5xx_raises_ml_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="unavailable")

    with pytest.raises(MLUnavailable) as exc_info:
        await _client(handler).summarize("some text")
    assert exc_info.value.reason == "http_503"


async def test_4xx_raises_ml_unavailable_not_http_status_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"detail": "bad request"})

    with pytest.raises(MLUnavailable) as exc_info:
        await _client(handler).summarize("some text")
    assert exc_info.value.reason == "http_400"


@pytest.mark.parametrize(
    "body", [b"not json", b'["not", "an", "object"]'], ids=["not-json", "json-list"]
)
async def test_a_body_that_is_not_a_json_object_raises_ml_unavailable(body: bytes) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    with pytest.raises(MLUnavailable) as exc_info:
        await _client(handler).summarize("some text")
    assert exc_info.value.reason == "bad_response"


async def test_success_returns_json_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"model": "distilbart-cnn-6-6"})

    result = await _client(handler).summarize("some text")
    assert result == {"model": "distilbart-cnn-6-6"}


async def test_readyz_true_on_200() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/readyz"
        return httpx.Response(200, json={"status": "ready"})

    assert await _client(handler).readyz() is True


async def test_readyz_false_on_non_200() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"status": "starting"})

    assert await _client(handler).readyz() is False


async def test_readyz_false_on_connect_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    assert await _client(handler).readyz() is False


async def test_readyz_false_on_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow")

    assert await _client(handler).readyz() is False


async def test_ml_client_forwards_bound_request_id() -> None:
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("x-request-id"))
        return httpx.Response(200, json={"summary": "x"})

    client = MLClient(
        httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://ml.test")
    )
    token = request_id_var.set("req-12345678")
    try:
        await client.summarize("text")
    finally:
        request_id_var.reset(token)
    await client.summarize("text")
    assert seen == ["req-12345678", None]


async def test_analyze_sends_the_seed_page_id_only_when_given() -> None:
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"edges": []})

    client = _client(handler)
    await client.analyze("Lead.", [{"id": "c1", "text": "Text."}], page_id=7)
    await client.analyze("Lead.", [{"id": "c1", "text": "Text."}])

    assert bodies[0]["page_id"] == 7
    assert "page_id" not in bodies[1]
    assert bodies[1]["related_leads"] == []


async def test_rate_posts_the_article_and_passages_with_the_deadline_and_returns_the_body() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"scores": {"c1": 2.5}})

    result = await _client(handler).rate(
        "Ada", "A lead.", [{"id": "c1", "text": "A passage."}], deadline_ms=120_000
    )

    [request] = seen
    assert request.url.path == "/v1/rate"
    assert request.headers["X-Deadline-Ms"] == "120000"
    assert json.loads(request.content) == {
        "title": "Ada",
        "lead": "A lead.",
        "passages": [{"id": "c1", "text": "A passage."}],
    }
    assert result == {"scores": {"c1": 2.5}}


@pytest.mark.parametrize("status", [422, 503])
async def test_rate_error_statuses_raise_ml_unavailable(status: int) -> None:
    with pytest.raises(MLUnavailable) as exc_info:
        await _client(lambda _request: httpx.Response(status)).rate(
            "Ada", "A lead.", [{"id": "c1", "text": "A passage."}], deadline_ms=1000
        )

    assert exc_info.value.reason == f"http_{status}"


async def test_a_sibling_has_a_call_slot_of_its_own_over_the_same_http_client() -> None:
    gate = asyncio.Event()
    started: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        started.append(request.url.path)
        if request.url.path == "/v1/rate":
            await gate.wait()
        return httpx.Response(200, json={})

    first = _client(handler)
    second = first.sibling()
    slow = asyncio.create_task(first.rate("T", "L", [{"id": "c", "text": "x"}], 60_000))
    try:
        await asyncio.sleep(0.05)

        await asyncio.wait_for(second.summarize("some text"), timeout=2)

        assert started == ["/v1/rate", "/v1/summarize"]
        assert second is not first
    finally:
        gate.set()
        await slow
