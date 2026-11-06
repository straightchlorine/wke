"""`python -m wke.worker`: standalone job worker process."""

from __future__ import annotations

import asyncio
import logging
import signal

import httpx

from wke.clients.ml import MLClient
from wke.clients.redis import RedisClient, default_redis_factory
from wke.clients.user_agent import build_user_agent
from wke.clients.wikimedia import WikimediaClient
from wke.clients.wikimedia_transport import WIKIMEDIA_TIMEOUT_SECONDS
from wke.jobs.queue import JobQueue
from wke.jobs.worker import Worker
from wke.logging_setup import configure_logging
from wke.settings import settings

logger = logging.getLogger(__name__)

ML_TIMEOUT_SECONDS = 15.0


async def _run() -> None:
    """Build every dependency and run the worker until SIGTERM."""
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

    worker = Worker(
        redis,
        job_queue,
        wikimedia,
        ml,
        settings.pipeline_version,
        settings.summary_sections,
        settings.num_beams,
        str(settings.wikipedia_api_url),
        public_host=settings.public_host,
        public_scheme=settings.public_scheme,
    )

    try:
        await _run_until_sigterm(worker)
    finally:
        await wm_http.aclose()
        await ml_http.aclose()
        await redis.aclose()


async def _run_until_sigterm(worker: Worker) -> None:
    """Run the worker loop until SIGTERM, requeuing any in-flight item on cancel.

    Args:
        worker: the Worker to run.
    """
    run_task = asyncio.create_task(worker.run_forever())
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGTERM, run_task.cancel)
    try:
        await run_task
    except asyncio.CancelledError:
        logger.info("wke.worker: SIGTERM received, in-flight item requeued")


def main() -> None:
    """Run the standalone worker process until SIGTERM."""
    configure_logging(settings.log_level, settings.log_format)
    asyncio.run(_run())


if __name__ == "__main__":
    main()
