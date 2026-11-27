"""`python -m wke.refresh`: keep stored dossiers alive and rebuild the edited ones.

Builds its own Redis client from `wke.settings.settings` (the CronJob has no ASGI
lifespan) and runs `run_refresh` once. It reaches Redis only.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time

from redis.exceptions import RedisError

from wke.clients.redis import RedisClient, default_redis_factory
from wke.jobs.queue import JobQueue
from wke.logging_setup import configure_logging
from wke.refresh.run import run_refresh
from wke.settings import settings

logger = logging.getLogger(__name__)


async def _run() -> int:
    """Build the Redis client and queue from settings and run the refresh once.

    Returns:
        int: 0 on success, also when some rebuilds were deferred; 1 when Redis failed.
    """
    raw_redis = default_redis_factory(str(settings.redis_url))
    redis = RedisClient(raw_redis)
    job_queue = JobQueue(
        redis, settings.pipeline_version, settings.queue_cap, settings.background_queue_cap
    )

    started = time.monotonic()
    try:
        summary = await run_refresh(raw_redis, redis, job_queue, settings.pipeline_version)
    except RedisError as exc:
        logger.error("wke.refresh: redis failed: %s", exc.__class__.__name__)
        return 1
    finally:
        await redis.aclose()

    logger.info(
        "wke.refresh: stored=%d stale=%d admitted=%d refused=%d deferred=%d extended=%d "
        "left_alone=%d skipped=%d duration_s=%.1f",
        summary.stored,
        summary.stale,
        summary.admitted,
        summary.refused,
        summary.deferred,
        summary.extended,
        summary.left_alone,
        summary.skipped,
        time.monotonic() - started,
    )
    return 0


def main() -> int:
    """Run the nightly refresh once.

    Returns:
        int: Process exit code (0 on success, 1 when Redis failed).
    """
    configure_logging(settings.log_level, settings.log_format)
    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())
