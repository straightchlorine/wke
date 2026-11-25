"""A Worker over the fakes, for tests that never run a real build."""

from __future__ import annotations

from typing import Any

import httpx

from tests.support.constants import PIPELINE_VERSION
from tests.support.ml_clients import analyze_down_client
from tests.support.wikimedia import make_wikimedia_client
from wke.clients.redis import RedisClient
from wke.jobs.queue import JobQueue
from wke.jobs.rater import Rater
from wke.jobs.worker import Worker


def make_worker(
    redis_client: RedisClient, queue: JobQueue, rating: Rater | None = None, **overrides: Any
) -> Worker:
    """Build a Worker whose Wikimedia and wke-ml clients answer 404 and 500.

    Args:
        redis_client: the Redis client.
        queue: the job queue to consume.
        rating: the rating loop the worker runs beside its own, if any.
        **overrides: public_host, public_scheme or an analyze_* keyword.

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
        rating=rating,
        **overrides,
    )
