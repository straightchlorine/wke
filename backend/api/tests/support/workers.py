"""A Worker over the fakes, for tests that never run a real build."""

from __future__ import annotations

import httpx

from tests.support.constants import PIPELINE_VERSION
from tests.support.ml_clients import analyze_down_client
from tests.support.wikimedia import make_wikimedia_client
from wke.clients.redis import RedisClient
from wke.jobs.queue import JobQueue
from wke.jobs.worker import Worker


def make_worker(redis_client: RedisClient, queue: JobQueue, **overrides: str) -> Worker:
    """Build a Worker whose Wikimedia and wke-ml clients answer 404 and 500.

    Args:
        redis_client: the Redis client.
        queue: the job queue to consume.
        **overrides: public_host or public_scheme.

    Returns:
        Worker: with the test pipeline version and one summary section.
    """
    return Worker(
        redis_client,
        queue,
        wikimedia=make_wikimedia_client(redis_client, lambda _request: httpx.Response(404)),
        ml=analyze_down_client(),
        pipeline_version=PIPELINE_VERSION,
        summary_sections=1,
        num_beams=1,
        wikipedia_api_url="http://wikipedia.test/w/api.php",
        **overrides,
    )
