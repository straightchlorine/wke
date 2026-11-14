"""Application lifespan: owns the Redis, Wikimedia and wke-ml clients, MCP and the worker."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette

from wke.api.constants import ML_HTTP_TIMEOUT_SECONDS, WORKER_SHUTDOWN_TIMEOUT_SECONDS
from wke.api.mcp_server import build_mcp_server
from wke.api.probes import ml_probe_loop
from wke.clients.ml import MLClient
from wke.clients.redis import RedisClient, RedisFactory
from wke.clients.user_agent import build_user_agent
from wke.clients.wikimedia import WikimediaClient
from wke.clients.wikimedia_transport import WIKIMEDIA_TIMEOUT_SECONDS
from wke.jobs.queue import JobQueue
from wke.jobs.worker import Worker
from wke.logging_setup import configure_logging
from wke.services.dossiers import DossierService
from wke.settings import Settings


def _build_service(
    cfg: Settings, redis: RedisClient, wm_http: httpx.AsyncClient
) -> tuple[WikimediaClient, JobQueue, DossierService]:
    """Wire the Wikimedia client, the job queue and the dossier service.

    Args:
        cfg: the settings.
        redis: the Redis client.
        wm_http: the HTTP client for Wikimedia.

    Returns:
        tuple: the Wikimedia client, the job queue and the dossier service.
    """
    wikimedia = WikimediaClient(
        wm_http,
        redis,
        str(cfg.wikipedia_api_url),
        str(cfg.wikipedia_rest_url),
        cfg.wm_budget_per_minute,
    )
    job_queue = JobQueue(redis, cfg.pipeline_version, cfg.queue_cap, cfg.background_queue_cap)
    service = DossierService(
        redis, wikimedia, job_queue, cfg.pipeline_version, cfg.public_host, cfg.public_scheme
    )
    return wikimedia, job_queue, service


def _build_mcp(cfg: Settings, service: DossierService) -> tuple[MCPServer, Starlette]:
    """Build the MCP server and its stateless streamable-HTTP ASGI app.

    Args:
        cfg: the settings.
        service: the dossier service the tools call.

    Returns:
        tuple: the MCP server and the ASGI app to mount.
    """
    mcp_server = build_mcp_server(service)
    # MCPServer's constructor calls the mcp SDK's own configure_logging,
    # which replaces the root handler with its own; reassert ours.
    configure_logging(cfg.log_level, cfg.log_format)
    transport_security = TransportSecuritySettings(allowed_hosts=[cfg.public_host, "localhost:*"])
    mcp_asgi_app = mcp_server.streamable_http_app(
        stateless_http=True,
        json_response=True,
        transport_security=transport_security,
    )
    return mcp_server, mcp_asgi_app


def _build_worker(
    cfg: Settings,
    redis: RedisClient,
    job_queue: JobQueue,
    wikimedia: WikimediaClient,
    ml: MLClient,
) -> Worker:
    """Build the in-process build worker.

    Args:
        cfg: the settings.
        redis: the Redis client.
        job_queue: the job queue to consume.
        wikimedia: the Wikimedia client.
        ml: the wke-ml client.

    Returns:
        Worker: ready for run_forever.
    """
    return Worker(
        redis,
        job_queue,
        wikimedia,
        ml,
        cfg.pipeline_version,
        cfg.summary_sections,
        cfg.num_beams,
        str(cfg.wikipedia_api_url),
        public_host=cfg.public_host,
        public_scheme=cfg.public_scheme,
    )


async def _stop_tasks(*tasks: asyncio.Task[None] | None) -> None:
    """Cancel background tasks, then wait for each to wind down.

    Args:
        *tasks: the tasks to stop; None entries are skipped.
    """
    running = [task for task in tasks if task is not None]
    for task in running:
        task.cancel()
    for task in running:
        with contextlib.suppress(asyncio.CancelledError, TimeoutError):
            await asyncio.wait_for(task, timeout=WORKER_SHUTDOWN_TIMEOUT_SECONDS)


def build_lifespan(
    cfg: Settings,
    redis_factory: RedisFactory,
    wikimedia_http_client: httpx.AsyncClient | None,
    ml_http_client: httpx.AsyncClient | None,
    start_worker: bool,
) -> Callable[[FastAPI], contextlib.AbstractAsyncContextManager[None]]:
    """Build the lifespan context manager of the application.

    Args:
        cfg: the settings.
        redis_factory: builds the async Redis client from REDIS_URL.
        wikimedia_http_client: pre-built client for WikimediaClient, or None.
        ml_http_client: pre-built client for MLClient, or None.
        start_worker: False to skip the in-process Worker.

    Returns:
        Callable[[FastAPI], contextlib.AbstractAsyncContextManager[None]]: the
        lifespan callable to pass to FastAPI.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        redis = RedisClient(redis_factory(str(cfg.redis_url)))
        wm_http = wikimedia_http_client or httpx.AsyncClient(
            headers={"User-Agent": build_user_agent()},
            timeout=WIKIMEDIA_TIMEOUT_SECONDS,
        )
        ml_http = ml_http_client or httpx.AsyncClient(
            base_url=str(cfg.ml_url), timeout=ML_HTTP_TIMEOUT_SECONDS
        )
        ml = MLClient(ml_http)
        wikimedia, job_queue, service = _build_service(cfg, redis, wm_http)

        app.state.redis = redis
        app.state.ml = ml
        app.state.job_queue = job_queue
        app.state.service = service
        app.state.ml_ready = False
        app.state.ml_ready_checked_at = None

        mcp_server, app.state.mcp_asgi_app = _build_mcp(cfg, service)
        worker = _build_worker(cfg, redis, job_queue, wikimedia, ml)

        async with mcp_server.session_manager.run():
            app.state.ready = True
            worker_task = asyncio.create_task(worker.run_forever()) if start_worker else None
            ml_probe_task = asyncio.create_task(ml_probe_loop(app))
            try:
                yield
            finally:
                app.state.ready = False
                await _stop_tasks(worker_task, ml_probe_task)
                await ml_http.aclose()
                await wm_http.aclose()
                await redis.aclose()

    return lifespan
