"""slowapi rate limit: the 429 body, and a key function that ignores client-supplied headers.

`get_remote_address` reads `request.client.host` (set by the ASGI server,
never by header content) so a spoofed `X-Forwarded-For` cannot let a
client dodge its own bucket or attribute its traffic to someone else's.
"""

from __future__ import annotations

import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from tests.support.apps import app_client, make_app
from tests.support.extra_routes import add_test_route
from wke.api.ratelimit import build_limiter
from wke.settings import Settings


@pytest.fixture
def rate_limited_app(fake_redis: FakeRedis, settings: Settings) -> FastAPI:
    app = make_app(fake_redis, settings)
    # The shared limiter as production builds it, on in-memory storage.
    limiter = build_limiter("memory://")
    app.state.limiter = limiter

    # slowapi ships no type annotations for `limit`.
    @limiter.limit("2/minute")  # pyright: ignore[reportUntypedFunctionDecorator, reportUnknownMemberType]
    async def limited(request: Request) -> dict[str, bool]:
        return {"ok": True}

    add_test_route(app, "/test/limited", limited)
    return app


async def test_third_request_is_rate_limited(rate_limited_app: FastAPI) -> None:
    async with app_client(rate_limited_app) as client:
        first = await client.get("/test/limited")
        second = await client.get("/test/limited")
        third = await client.get("/test/limited")

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert third.headers["content-type"] == "application/problem+json"
    assert third.headers["retry-after"] == "60"
    body = third.json()
    assert body["code"] == "rate_limited"
    assert body["retry_after"] == 60
    assert body["request_id"]


async def test_spoofed_x_forwarded_for_does_not_grant_a_separate_bucket(
    rate_limited_app: FastAPI,
) -> None:
    async with app_client(rate_limited_app) as client:
        await client.get("/test/limited", headers={"X-Forwarded-For": "1.2.3.4"})
        await client.get("/test/limited", headers={"X-Forwarded-For": "5.6.7.8"})
        third = await client.get("/test/limited", headers={"X-Forwarded-For": "9.9.9.9"})

    # Every request shares one transport connection, so get_remote_address
    # sees the same request.client.host whatever the header claims: the
    # bucket is exhausted by the third request.
    assert third.status_code == 429


async def test_each_client_address_has_its_own_bucket(rate_limited_app: FastAPI) -> None:
    async def statuses(address: str) -> list[int]:
        transport = ASGITransport(app=rate_limited_app, client=(address, 5000))
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            return [(await client.get("/test/limited")).status_code for _ in range(3)]

    async with rate_limited_app.router.lifespan_context(rate_limited_app):
        first = await statuses("203.0.113.1")
        second = await statuses("203.0.113.2")

    assert first == second == [200, 200, 429]
