"""`python -m wke.watcher`: EventStreams recentchange consumer.

Runs the recentchange watcher forever: one long-lived SSE connection,
reconnect with full-jitter backoff, a heartbeat file for the liveness
probe, and /metrics on WATCHER_METRICS_PORT (default 8000) for the
wke_watcher_* series. Intended to run as the sole replica of a
Deployment with `strategy: Recreate`.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
from prometheus_client import start_http_server

from wke.clients.redis import RedisClient, default_redis_factory
from wke.clients.user_agent import build_user_agent
from wke.logging_setup import configure_logging
from wke.settings import settings
from wke.watcher.stream import Watcher

HEARTBEAT_PATH = Path("/tmp/heartbeat")


async def run_watcher() -> None:
    """Build every dependency and run the watcher until cancelled."""
    configure_logging(settings.log_level, settings.log_format)
    start_http_server(settings.watcher_metrics_port)
    raw_redis = default_redis_factory(str(settings.redis_url))
    redis = RedisClient(raw_redis)
    async with httpx.AsyncClient() as http_client:
        watcher = Watcher(
            http_client,
            redis,
            str(settings.wikimedia_eventstreams_url),
            build_user_agent(),
            HEARTBEAT_PATH,
        )
        await watcher.run_forever()


def main() -> int | None:
    """Run the watcher event loop.

    Returns:
        int | None: None on a clean (cancelled) shutdown.
    """
    asyncio.run(run_watcher())
    return None


if __name__ == "__main__":
    raise SystemExit(main())
