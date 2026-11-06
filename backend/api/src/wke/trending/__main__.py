"""`python -m wke.trending`: Wikifeeds mostread snapshot + prebuild drain.

Builds its own Redis/Wikimedia/wke-ml clients from `wke.settings.settings`
(the CronJob has no ASGI lifespan to share `create_app`'s) and runs
`run_trending` once.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time

import httpx

from wke.clients.ml import MLClient
from wke.clients.redis import RedisClient, default_redis_factory
from wke.clients.user_agent import build_user_agent
from wke.clients.wikimedia import WikimediaClient
from wke.clients.wikimedia_transport import WIKIMEDIA_TIMEOUT_SECONDS
from wke.jobs.queue import JobQueue
from wke.logging_setup import configure_logging
from wke.settings import settings
from wke.trending.run import run_trending

logger = logging.getLogger(__name__)

ML_TIMEOUT_SECONDS = 15.0


async def _run() -> int:
    """Build clients from settings and run the trending pipeline once.

    Returns:
        int: 0 on success (including the idempotent no-op case).
    """
    raw_redis = default_redis_factory(str(settings.redis_url))
    redis = RedisClient(raw_redis)
    wm_http = httpx.AsyncClient(
        headers={"User-Agent": build_user_agent()}, timeout=WIKIMEDIA_TIMEOUT_SECONDS
    )
    wikimedia = WikimediaClient(
        wm_http,
        redis,
        str(settings.wikipedia_api_url),
        str(settings.wikipedia_rest_url),
        settings.wm_budget_per_minute,
    )
    ml_http = httpx.AsyncClient(base_url=str(settings.ml_url), timeout=ML_TIMEOUT_SECONDS)
    ml = MLClient(ml_http)
    job_queue = JobQueue(
        redis, settings.pipeline_version, settings.queue_cap, settings.background_queue_cap
    )

    started = time.monotonic()
    try:
        snapshot = await run_trending(wikimedia, ml, redis, job_queue, settings.pipeline_version)
    finally:
        await wm_http.aclose()
        await ml_http.aclose()
        await redis.aclose()

    if snapshot is not None:
        to_build = sum(1 for topic in snapshot.topics if topic.dossier_state != "ready")
        logger.info(
            "wke.trending: date=%s source=%s topics=%d to_build=%d duration_s=%.1f",
            snapshot.date,
            snapshot.source,
            len(snapshot.topics),
            to_build,
            time.monotonic() - started,
        )
    return 0


def main() -> int:
    """Run the nightly trending snapshot pipeline once.

    Returns:
        int: Process exit code (0 on success).
    """
    configure_logging(settings.log_level, settings.log_format)
    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())
