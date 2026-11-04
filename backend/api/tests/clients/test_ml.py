"""wke.clients.ml.MLClient: every failure mode degrades to MLUnavailable.

A raised MLUnavailable is what lets the pipeline fall back to structural
mode instead of getting stuck; anything that escapes as a different
exception type breaks that fallback.
"""

from __future__ import annotations

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
