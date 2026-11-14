"""MLClient over a mock transport, answering with a test's handler."""

from __future__ import annotations

from collections.abc import Callable

import httpx

from tests.support.ml_payloads import analyze_response_json
from wke.clients.ml import MLClient

MLHandler = Callable[[httpx.Request], httpx.Response]


def make_ml_client(handler: MLHandler) -> MLClient:
    """Build an MLClient whose wke-ml requests are answered by `handler`.

    Args:
        handler: the MockTransport handler that answers every request.

    Returns:
        MLClient: pointed at a test host.
    """
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://wke-ml.test")
    return MLClient(http)


def analyze_down_client() -> MLClient:
    """Build an MLClient whose every call fails with a 500.

    Returns:
        MLClient: analyze raises MLUnavailable.
    """
    return make_ml_client(lambda _request: httpx.Response(500))


def summarize_down_client() -> MLClient:
    """Build an MLClient that analyzes normally and fails every summarize call.

    Returns:
        MLClient: summarize raises MLUnavailable.
    """

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/analyze":
            return httpx.Response(200, json=analyze_response_json())
        return httpx.Response(500)

    return make_ml_client(handle)
