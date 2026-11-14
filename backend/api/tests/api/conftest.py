"""Route-test fixtures: a dossier built into fake_redis, and a counting Wikimedia mock."""

from __future__ import annotations

import httpx
import pytest

from tests.support.constants import FIXTURE_PAGE_ID, PIPELINE_VERSION, REQUIRED_ENV
from tests.support.jobs import make_job
from tests.support.wikimedia import WmFixtures, make_wikimedia_client, wikimedia_handler
from wke.clients.ml import MLClient
from wke.clients.redis import RedisClient
from wke.clients.wikimedia import WikimediaClient
from wke.core import keys
from wke.jobs.build.run import run_build
from wke.jobs.build.summarize import run_summary_item
from wke.jobs.queue import JobQueue


async def _build(
    job_id: str, redis_client: RedisClient, wikimedia_client: WikimediaClient, ml_client: MLClient
) -> JobQueue:
    """Admit and build the recorded article's dossier to its partial state, one summary queued.

    Args:
        job_id: id of the job to admit and build.
        redis_client: the RedisClient the dossier is written to.
        wikimedia_client: the recorded-fixture Wikimedia client.
        ml_client: the canned wke-ml client.

    Returns:
        JobQueue: the queue the job was admitted to.
    """
    job = make_job(id=job_id)
    job_queue = JobQueue(redis_client, PIPELINE_VERSION, queue_cap=20)
    await job_queue.set_job(job)
    await run_build(
        job,
        redis=redis_client,
        wikimedia=wikimedia_client,
        ml=ml_client,
        job_queue=job_queue,
        pipeline_version=PIPELINE_VERSION,
        summary_sections=1,
        wikipedia_api_url=REQUIRED_ENV["WIKIPEDIA_API_URL"],
        background=False,
    )
    return job_queue


@pytest.fixture
async def built_page(
    redis_client: RedisClient, wikimedia_client: WikimediaClient, ml_client_ok: MLClient
) -> int:
    """Build and fully summarize the recorded article's dossier into fake_redis.

    Returns:
        int: the built page id (FIXTURE_PAGE_ID).
    """
    job_queue = await _build("aaaaaaaaaaaaaaaa", redis_client, wikimedia_client, ml_client_ok)
    queued = await redis_client.lrange(keys.QUEUE_SUM_INTERACTIVE, 0, -1)
    for item in queued:
        job_id, section_id = item.split(":", 1)
        await run_summary_item(
            job_id,
            section_id,
            redis=redis_client,
            job_queue=job_queue,
            ml=ml_client_ok,
            pipeline_version=PIPELINE_VERSION,
            num_beams=1,
        )
        # Consume the item so it is not left behind for a test that
        # starts its own worker to pick up and process a second time.
        await redis_client.lrem(keys.QUEUE_SUM_INTERACTIVE, 1, item)
    return FIXTURE_PAGE_ID


@pytest.fixture
async def partial_built_page(
    redis_client: RedisClient, wikimedia_client: WikimediaClient, ml_client_ok: MLClient
) -> int:
    """Build the recorded article's dossier but leave every summary item unqueued.

    Stops after `run_build`, so `build.state == "partial"`: the
    structural stages ran but no summary has been produced yet.

    Returns:
        int: the built page id (FIXTURE_PAGE_ID).
    """
    await _build("cccccccccccccccc", redis_client, wikimedia_client, ml_client_ok)
    return FIXTURE_PAGE_ID


@pytest.fixture
def counting_wikimedia_client(
    redis_client: RedisClient, wm_fixtures: WmFixtures
) -> tuple[WikimediaClient, list[str]]:
    """A WikimediaClient on the shared mock handler, plus the request URLs it served.

    Returns:
        tuple[WikimediaClient, list[str]]: the client and the list its handler
        appends one entry to per request, in order.
    """
    calls: list[str] = []
    inner = wikimedia_handler(wm_fixtures)

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return inner(request)

    return make_wikimedia_client(redis_client, handle), calls
