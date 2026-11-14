"""Every 4xx and 5xx response is an application/problem+json ApiError body.

A FastAPI validation failure (422), an HTTP error raised by a route, a
domain ApiException, an unmatched path (API or MCP) and a rate limit must all
come back as `application/problem+json` with the full ApiError envelope and a
request_id, never FastAPI's or Starlette's default error bodies.
"""

from __future__ import annotations

import httpx
import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI, HTTPException, Request

from tests.support.apps import app_client, make_app
from tests.support.extra_routes import add_test_route
from wke.core.errors import ApiException
from wke.core.models import TopicCandidate
from wke.settings import Settings


@pytest.fixture
def error_app(fake_redis: FakeRedis, settings: Settings) -> FastAPI:
    app = make_app(fake_redis, settings)

    async def needs_limit(request: Request, limit: int) -> dict[str, int]:
        return {"limit": limit}

    async def http_error(request: Request, status: int) -> None:
        raise HTTPException(status, "short and stout")

    async def ambiguous(request: Request) -> None:
        raise ApiException(
            409,
            "disambiguation",
            detail="Mercury is a disambiguation page.",
            retry_after=7,
            candidates=[TopicCandidate(page_id=1, title="Mercury (planet)", dossier_state="none")],
        )

    add_test_route(app, "/test/validated", needs_limit)
    add_test_route(app, "/test/http-error", http_error)
    add_test_route(app, "/test/ambiguous", ambiguous)
    return app


def _assert_error_body(response: httpx.Response, status_code: int, code: str) -> dict[str, object]:
    assert response.status_code == status_code
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["type"].endswith(f"/{code}")
    assert body["title"]
    assert body["status"] == status_code
    assert body["code"] == code
    assert body["request_id"]
    return body


async def test_bad_query_param_is_an_api_error(error_app: FastAPI) -> None:
    async with app_client(error_app) as client:
        response = await client.get("/test/validated", params={"limit": "not-a-number"})

    body = _assert_error_body(response, 422, "validation_error")
    assert "limit" in str(body["detail"])


async def test_unknown_route_is_an_api_error(error_app: FastAPI) -> None:
    async with app_client(error_app) as client:
        response = await client.get("/this/route/does/not/exist")

    _assert_error_body(response, 404, "not_found")


@pytest.mark.parametrize(
    ("status", "code", "title"),
    [
        (404, "not_found", "Not Found"),
        (422, "internal", "Unprocessable Entity"),
        (418, "internal", "Error"),
    ],
)
async def test_http_exception_keeps_its_status_and_detail(
    error_app: FastAPI, status: int, code: str, title: str
) -> None:
    async with app_client(error_app) as client:
        response = await client.get("/test/http-error", params={"status": status})

    body = _assert_error_body(response, status, code)
    assert body["detail"] == "short and stout"
    assert body["title"] == title


async def test_api_exception_carries_retry_after_and_candidates(error_app: FastAPI) -> None:
    async with app_client(error_app) as client:
        response = await client.get("/test/ambiguous")

    body = _assert_error_body(response, 409, "disambiguation")
    assert response.headers["retry-after"] == "7"
    assert body["retry_after"] == 7
    assert body["detail"] == "Mercury is a disambiguation page."
    assert body["candidates"] == [
        {"page_id": 1, "title": "Mercury (planet)", "dossier_state": "none"}
    ]
