"""GET /api/v1/status: dependency health and queue depth."""

# Handlers are registered by the router decorator, never called by name.
# pyright: reportUnusedFunction=false

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request

from wke.api.constants import PACKAGE_VERSION
from wke.api.probes import (
    ml_probe_is_stale,
    probe_ml_ready,
    read_trending_snapshot,
    wikimedia_budget_remaining,
)
from wke.clients.redis import RedisClient
from wke.core import keys
from wke.core.models import Status
from wke.jobs.queue import JobQueue
from wke.settings import Settings


def build_router(cfg: Settings) -> APIRouter:
    """Build the /api/v1/status router.

    Args:
        cfg: the settings (pipeline version, Wikimedia budget).

    Returns:
        APIRouter: with the status route registered.
    """
    router = APIRouter()

    @router.get("/api/v1/status", tags=["status"])
    async def get_status(request: Request) -> Status:
        redis_client: RedisClient = request.app.state.redis
        job_queue: JobQueue = request.app.state.job_queue
        redis_ok = await redis_client.ping()
        depth = await job_queue.queue_depth()

        checked_at: datetime | None = getattr(request.app.state, "ml_ready_checked_at", None)
        if ml_probe_is_stale(checked_at, datetime.now(UTC)):
            await probe_ml_ready(request.app)

        watcher_connected = await redis_client.exists(keys.WATCHER_HEARTBEAT)
        snapshot = await read_trending_snapshot(redis_client)
        trending_age_seconds = (
            max(0, int((datetime.now(UTC) - snapshot.generated_at).total_seconds()))
            if snapshot is not None
            else None
        )
        budget_remaining = await wikimedia_budget_remaining(
            redis_client, cfg.wm_budget_per_minute, redis_ok
        )

        return Status(
            version=PACKAGE_VERSION,
            pipeline_version=cfg.pipeline_version,
            redis=redis_ok,
            ml_ready=bool(getattr(request.app.state, "ml_ready", False)),
            watcher_connected=watcher_connected,
            trending_date=snapshot.date if snapshot is not None else None,
            trending_age_seconds=trending_age_seconds,
            queue_depth=depth,
            wikimedia_budget_remaining=budget_remaining,
        )

    return router
