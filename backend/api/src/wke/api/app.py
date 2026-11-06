"""FastAPI application factory: wires the lifespan, middleware, routers and MCP mount."""

from __future__ import annotations

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.middleware import SlowAPIMiddleware

from wke.api.constants import API_TITLE, PACKAGE_VERSION
from wke.api.error_handlers import register_error_handlers
from wke.api.lifespan import build_lifespan
from wke.api.mcp_mount import MCPDelegate
from wke.api.middleware import install_request_middleware
from wke.api.openapi_docs import custom_openapi
from wke.api.ratelimit import build_limiter
from wke.api.routes import dossiers, health, jobs, live, llmstxt, search, sitemap, status, trending
from wke.clients.redis import RedisFactory, default_redis_factory
from wke.settings import Settings
from wke.settings import settings as default_settings


def create_app(
    app_settings: Settings | None = None,
    redis_factory: RedisFactory = default_redis_factory,
    wikimedia_http_client: httpx.AsyncClient | None = None,
    ml_http_client: httpx.AsyncClient | None = None,
    limiter: Limiter | None = None,
    start_worker: bool = True,
) -> FastAPI:
    """Build the FastAPI application.

    Args:
        app_settings: Settings instance; defaults to the module-level
            eagerly-constructed settings singleton.
        redis_factory: builds the async Redis client from REDIS_URL;
            tests replace this to return a fakeredis client.
        wikimedia_http_client: pre-built httpx.AsyncClient for
            WikimediaClient; tests inject one backed by MockTransport.
        ml_http_client: pre-built httpx.AsyncClient for MLClient; tests
            inject one backed by MockTransport.
        limiter: pre-built slowapi Limiter; tests inject one with
            `storage_uri="memory://"` so rate-limit tests never need a
            real Redis. Defaults to a Redis-backed Limiter from REDIS_URL.
        start_worker: False to skip running the in-process Worker, so
            tests that build their own dossier fixtures do not race it.

    Returns:
        FastAPI: the configured application, MCP mounted at "/".
    """
    cfg = app_settings or default_settings
    lifespan = build_lifespan(
        cfg, redis_factory, wikimedia_http_client, ml_http_client, start_worker
    )
    app = FastAPI(title=API_TITLE, version=PACKAGE_VERSION, lifespan=lifespan)

    limiter = limiter or build_limiter(str(cfg.redis_url))
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)
    register_error_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["content-type", "if-none-match", "x-request-id"],
    )
    install_request_middleware(app)

    app.include_router(health.build_router())
    app.include_router(status.build_router(cfg))
    app.include_router(llmstxt.build_router())
    app.include_router(sitemap.build_router())
    app.include_router(search.build_router(limiter))
    app.include_router(dossiers.build_router(limiter))
    app.include_router(jobs.build_router(limiter))
    app.include_router(trending.build_router(limiter))
    app.include_router(live.build_router(limiter))

    app.openapi = lambda: custom_openapi(app)
    # Mount last: "/" is a catch-all, so all routes must be registered first.
    app.mount("/", MCPDelegate(app))
    return app
