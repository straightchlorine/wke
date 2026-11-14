"""Request ids, security headers, 500 fallback, probes, CORS, MCP delegate, noindex, labels."""

from __future__ import annotations

import logging

import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from starlette.routing import Route
from starlette.types import Scope

from tests.support.apps import app_client, make_app
from tests.support.extra_routes import add_test_route
from wke.api.middleware import route_label
from wke.settings import Settings


async def test_api_responses_are_noindex(app: FastAPI) -> None:
    async with app_client(app) as client:
        ok = await client.get("/api/v1/status")
        missing = await client.get("/api/v1/does-not-exist")

    assert ok.status_code == 200
    assert ok.headers["x-robots-tag"] == "noindex"
    assert missing.status_code == 404
    assert missing.headers["x-robots-tag"] == "noindex"


async def test_crawlable_files_are_not_noindex(app: FastAPI) -> None:
    async with app_client(app) as client:
        llms = await client.get("/llms.txt")
        sitemap = await client.get("/sitemap.xml")

    assert llms.status_code == 200
    assert sitemap.status_code == 200
    assert "x-robots-tag" not in llms.headers
    assert "x-robots-tag" not in sitemap.headers


async def test_valid_request_id_is_echoed(app: FastAPI) -> None:
    async with app_client(app) as client:
        response = await client.get("/healthz", headers={"X-Request-ID": "req-12345678"})

    assert response.headers["x-request-id"] == "req-12345678"


@pytest.mark.parametrize("incoming", ["short", "has spaces in it!", "x" * 65])
async def test_invalid_request_id_is_replaced(app: FastAPI, incoming: str) -> None:
    async with app_client(app) as client:
        response = await client.get("/healthz", headers={"X-Request-ID": incoming})

    issued = response.headers["x-request-id"]
    assert issued != incoming
    assert len(issued) == 36


async def test_security_headers_are_set_on_every_response(app: FastAPI) -> None:
    async with app_client(app) as client:
        response = await client.get("/healthz")

    assert response.headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["permissions-policy"] == "()"


async def test_unhandled_exception_becomes_an_api_error_500_with_request_id(app: FastAPI) -> None:
    async def boom(request: Request) -> dict[str, str]:
        raise RuntimeError("boom")

    add_test_route(app, "/test/boom", boom)

    async with app_client(app) as client:
        response = await client.get("/test/boom", headers={"X-Request-ID": "req-12345678"})

    assert response.status_code == 500
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == "internal"
    assert body["request_id"] == "req-12345678"
    assert "boom" not in response.text


async def test_healthz_is_ok_and_readyz_follows_the_lifespan(app: FastAPI) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        before_health = await client.get("/healthz")
        before_ready = await client.get("/readyz")
    async with app_client(app) as client:
        after_ready = await client.get("/readyz")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        after_shutdown = await client.get("/readyz")

    assert before_health.status_code == 200
    assert before_health.json() == {"status": "ok"}
    assert before_ready.status_code == 503
    assert before_ready.json() == {"status": "starting"}
    assert after_ready.status_code == 200
    assert after_ready.json() == {"status": "ready"}
    assert after_shutdown.status_code == 503


@pytest.mark.parametrize(
    ("origin", "allowed"),
    [("https://allowed.example", True), ("https://other.example", False)],
)
async def test_cors_allows_only_configured_origins(
    fake_redis: FakeRedis, settings: Settings, origin: str, allowed: bool
) -> None:
    cors_settings = settings.model_copy(update={"cors_origins": ["https://allowed.example"]})
    app = make_app(fake_redis, cors_settings)

    async with app_client(app) as client:
        response = await client.options(
            "/api/v1/status",
            headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
        )

    if allowed:
        assert response.headers["access-control-allow-origin"] == origin
        assert "access-control-allow-credentials" not in response.headers
    else:
        assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize(
    ("method", "request_headers", "status"),
    [
        ("POST", "content-type, if-none-match, x-request-id", 200),
        ("DELETE", "content-type", 400),
        ("GET", "authorization", 400),
    ],
)
async def test_cors_preflight_allows_only_the_api_methods_and_headers(
    fake_redis: FakeRedis, settings: Settings, method: str, request_headers: str, status: int
) -> None:
    cors_settings = settings.model_copy(update={"cors_origins": ["https://allowed.example"]})
    app = make_app(fake_redis, cors_settings)

    async with app_client(app) as client:
        response = await client.options(
            "/api/v1/status",
            headers={
                "Origin": "https://allowed.example",
                "Access-Control-Request-Method": method,
                "Access-Control-Request-Headers": request_headers,
            },
        )

    assert response.status_code == status


async def test_unknown_path_through_the_mcp_delegate_is_an_api_error_404(app: FastAPI) -> None:
    async with app_client(app) as client:
        response = await client.get("/not/a/route")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "not_found"


async def test_mcp_before_the_lifespan_is_503(app: FastAPI) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/mcp", json={})

    assert response.status_code == 503


@pytest.mark.parametrize("path", ["/mcpx", "/mcp-old/tools"])
async def test_path_that_only_starts_like_mcp_is_an_api_error_404(app: FastAPI, path: str) -> None:
    async with app_client(app) as client:
        response = await client.post(path, json={})

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "not_found"


def _request_for(path: str, route: Route | None = None) -> Request:
    scope: Scope = {"type": "http", "path": path, "headers": [], "query_string": b""}
    if route is not None:
        scope["route"] = route
    return Request(scope)


@pytest.mark.parametrize(
    ("path", "route", "label"),
    [
        pytest.param(
            "/api/v1/jobs/abc",
            Route("/api/v1/jobs/{job_id}", print),
            "/api/v1/jobs/{job_id}",
            id="template",
        ),
        pytest.param("/mcp", None, "/mcp", id="mcp"),
        pytest.param("/mcp/", None, "/mcp", id="mcp-slash"),
        pytest.param("/mcpx", None, "unmatched", id="mcp-lookalike"),
        pytest.param("/wp-login", None, "unmatched", id="unknown"),
    ],
)
def test_route_label_is_never_the_raw_path(path: str, route: Route | None, label: str) -> None:
    assert route_label(_request_for(path, route)) == label


@pytest.mark.parametrize(
    ("path", "level"),
    [
        ("/api/v1/status", logging.INFO),
        ("/api/v1/does-not-exist", logging.INFO),
        ("/healthz", logging.DEBUG),
        ("/test/boom", logging.WARNING),
    ],
)
async def test_access_log_level_follows_the_route_and_status(
    app: FastAPI, path: str, level: int
) -> None:
    async def boom(request: Request) -> dict[str, str]:
        raise RuntimeError("boom")

    add_test_route(app, "/test/boom", boom)
    records: list[logging.LogRecord] = []

    class Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    # The lifespan resets the root handlers (the MCP SDK installs its own),
    # so caplog's handler would be gone: attach to the module logger itself.
    logger = logging.getLogger("wke.api.middleware")
    handler = Collect(logging.DEBUG)
    logger.addHandler(handler)
    previous_level = logger.level
    logger.setLevel(logging.DEBUG)
    try:
        async with app_client(app) as client:
            await client.get(path)
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)

    access = [r for r in records if r.getMessage().startswith("GET ")]
    assert [r.levelno for r in access] == [level]
    assert "does-not-exist" not in access[0].getMessage()
