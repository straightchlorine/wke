"""Health probes and gauge sampling behind /metrics, /api/v1/status and the lifespan."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from fastapi import FastAPI

from wke.api.constants import ML_PROBE_INTERVAL_SECONDS, ML_PROBE_MIN_INTERVAL_SECONDS
from wke.clients.ml import MLClient
from wke.clients.redis import RedisClient
from wke.core import keys
from wke.core.models import TrendingSnapshot
from wke.metrics import JOBS_QUEUED, TRENDING_LAST_SUCCESS_TIMESTAMP


def ml_probe_is_stale(checked_at: datetime | None, now: datetime) -> bool:
    """Decide whether an on-demand /api/v1/status call must re-probe wke-ml.

    Args:
        checked_at: when wke-ml was last probed, or None if never probed.
        now: the current time.

    Returns:
        bool: True if there is no prior probe, or the prior probe is at
        least ML_PROBE_MIN_INTERVAL_SECONDS old.
    """
    if checked_at is None:
        return True
    return (now - checked_at).total_seconds() >= ML_PROBE_MIN_INTERVAL_SECONDS


async def probe_ml_ready(app: FastAPI) -> None:
    """Probe wke-ml's /readyz once and record the result on app.state.

    Args:
        app: the FastAPI application; reads app.state.ml (MLClient) and
            writes app.state.ml_ready / app.state.ml_ready_checked_at.
    """
    ml: MLClient = app.state.ml
    app.state.ml_ready = await ml.readyz()
    app.state.ml_ready_checked_at = datetime.now(UTC)


async def read_trending_snapshot(redis_client: RedisClient) -> TrendingSnapshot | None:
    """Read the latest trending snapshot, for /api/v1/status.

    Args:
        redis_client: fail-open Redis wrapper.

    Returns:
        TrendingSnapshot | None: None if no snapshot has been built yet,
        it fails to parse, or Redis is unreachable.
    """
    raw = await redis_client.get(keys.TRENDING_LATEST)
    if raw is None:
        return None
    try:
        return TrendingSnapshot.model_validate_json(raw)
    except ValueError:
        return None


async def wikimedia_budget_remaining(
    redis_client: RedisClient, budget_per_minute: int, redis_ok: bool
) -> int | None:
    """Compute the shared Wikimedia call budget left in the current minute.

    Args:
        redis_client: fail-open Redis wrapper.
        budget_per_minute: the shared per-minute call cap
            (settings.wm_budget_per_minute).
        redis_ok: whether this request's Redis PING succeeded. A missing
            counter key legitimately means no calls yet this minute, so
            it cannot double as an outage signal; that is what redis_ok
            is for.

    Returns:
        int | None: budget_per_minute minus the current minute's call
        count, floored at 0; None if Redis is unreachable.
    """
    if not redis_ok:
        return None
    epoch_minute = int(datetime.now(UTC).timestamp() // 60)
    raw = await redis_client.get(keys.wm_budget(epoch_minute))
    used = int(raw) if raw is not None else 0
    return max(0, budget_per_minute - used)


async def sample_redis_gauges(app: FastAPI) -> None:
    """Refresh the Redis-derived gauges just before a /metrics scrape.

    Sampled at scrape time rather than pushed from the worker/cron, so
    `wke_jobs_queued` still reflects reality if the worker is down and
    `wke_trending_last_success_timestamp` needs no extra write path
    beyond the snapshot wke-trending already stores at `trending:latest`.
    Fails open through RedisClient: a Redis blip leaves the queue gauges at 0
    and the trending gauge unchanged instead of breaking /metrics scraping.

    Args:
        app: the FastAPI application; reads app.state.redis.
    """
    redis_client: RedisClient = app.state.redis
    for queue_name in (*keys.QUEUE_PRIORITY_ORDER, keys.QUEUE_PROCESSING):
        JOBS_QUEUED.labels(queue=queue_name).set(await redis_client.llen(queue_name))

    snapshot = await read_trending_snapshot(redis_client)
    if snapshot is not None:
        TRENDING_LAST_SUCCESS_TIMESTAMP.set(snapshot.generated_at.timestamp())


async def ml_probe_loop(app: FastAPI) -> None:
    """Re-probe wke-ml's readiness every ML_PROBE_INTERVAL_SECONDS forever.

    Sleeps before first probe: GET /api/v1/status already on-demand probes
    (throttled to ML_PROBE_MIN_INTERVAL_SECONDS), so this loop only keeps
    the result fresh between requests.

    Args:
        app: the FastAPI application to probe and update.
    """
    while True:
        await asyncio.sleep(ML_PROBE_INTERVAL_SECONDS)
        await probe_ml_ready(app)
