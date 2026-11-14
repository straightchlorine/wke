"""Application builders for route tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


def never_called_http_client() -> httpx.AsyncClient:
    """An AsyncClient whose transport fails the test if any request is sent."""

    def handle(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no outbound HTTP call should happen in this test")

    return httpx.AsyncClient(transport=httpx.MockTransport(handle))


def make_app(
    fake_redis,
    settings,
    *,
    wikimedia_http: httpx.AsyncClient | None = None,
    ml_http: httpx.AsyncClient | None = None,
    start_worker: bool = False,
) -> FastAPI:
    """Build a create_app() on fake_redis with a fresh in-memory limiter.

    Args:
        fake_redis: the fakeredis client every Redis factory call returns.
        settings: the Settings instance handed to the app.
        wikimedia_http: Wikimedia transport; fails the test if used when omitted.
        ml_http: wke-ml transport; fails the test if used when omitted.
        start_worker: whether the lifespan starts the job worker.

    Returns:
        FastAPI: the app, its limiter reachable as `app.state.limiter`.
    """
    from slowapi import Limiter
    from slowapi.util import get_remote_address

    from wke.api.app import create_app

    return create_app(
        app_settings=settings,
        redis_factory=lambda url: fake_redis,
        wikimedia_http_client=wikimedia_http or never_called_http_client(),
        ml_http_client=ml_http or never_called_http_client(),
        limiter=Limiter(key_func=get_remote_address, storage_uri="memory://"),
        start_worker=start_worker,
    )


@asynccontextmanager
async def app_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Run an app's lifespan and an AsyncClient against it, in one asyncio task.

    Args:
        app: the FastAPI app to serve over an in-process ASGI transport.

    Yields:
        AsyncClient: connected to `app` via ASGITransport, lifespan started.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        async with app.router.lifespan_context(app):
            yield ac
