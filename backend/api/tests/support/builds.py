"""Running a build job and its summary items against the fakes, as the worker would."""

from __future__ import annotations

from tests.support.constants import PIPELINE_VERSION
from wke.clients.ml import MLClient
from wke.clients.redis import RedisClient
from wke.clients.wikimedia import WikimediaClient
from wke.core import keys
from wke.core.models import Dossier, Job
from wke.jobs.build.run import run_build
from wke.jobs.build.summarize import run_summary_item
from wke.jobs.queue import JobQueue

WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"


def make_queue(redis_client: RedisClient) -> JobQueue:
    """Build the job queue the pipeline tests share.

    Args:
        redis_client: the Redis client the queue stores into.

    Returns:
        JobQueue: with the test pipeline version and a small cap.
    """
    return JobQueue(redis_client, PIPELINE_VERSION, queue_cap=20)


async def build_only(
    redis_client: RedisClient,
    wikimedia_client: WikimediaClient,
    ml: MLClient,
    job: Job,
    *,
    summary_sections: int = 1,
    public_host: str = "",
    public_scheme: str = "https",
    background: bool = False,
) -> JobQueue:
    """Store the job and run its build, leaving the summary items queued.

    Args:
        redis_client: the Redis client.
        wikimedia_client: the Wikimedia client over the recorded article.
        ml: the wke-ml client.
        job: the admitted job.
        summary_sections: the SUMMARY_SECTIONS setting.
        public_host: the PUBLIC_HOST setting.
        public_scheme: the PUBLIC_SCHEME setting.
        background: True when the job came off the background queue.

    Returns:
        JobQueue: the queue the job was stored in.
    """
    queue = make_queue(redis_client)
    await queue.set_job(job)
    await run_build(
        job,
        redis=redis_client,
        wikimedia=wikimedia_client,
        ml=ml,
        job_queue=queue,
        pipeline_version=PIPELINE_VERSION,
        summary_sections=summary_sections,
        wikipedia_api_url=WIKIPEDIA_API_URL,
        background=background,
        public_host=public_host,
        public_scheme=public_scheme,
    )
    return queue


async def queued_summary_items(redis_client: RedisClient) -> list[str]:
    """List the interactive summary items waiting for a worker.

    Args:
        redis_client: the Redis client.

    Returns:
        list[str]: the "job_id:section_id" queue values, oldest first.
    """
    return await redis_client.lrange(keys.QUEUE_SUM_INTERACTIVE, 0, -1)


async def run_summary(
    redis_client: RedisClient, queue: JobQueue, ml: MLClient, item: str, *, num_beams: int = 1
) -> None:
    """Run one queued summary item as the worker would.

    Args:
        redis_client: the Redis client.
        queue: the job queue the build stored its job in.
        ml: the wke-ml client.
        item: a "job_id:section_id" queue value.
        num_beams: the NUM_BEAMS setting.
    """
    job_id, section_id = item.split(":", 1)
    await run_summary_item(
        job_id,
        section_id,
        redis=redis_client,
        job_queue=queue,
        ml=ml,
        pipeline_version=PIPELINE_VERSION,
        num_beams=num_beams,
    )


async def run_queued_summaries(redis_client: RedisClient, queue: JobQueue, ml: MLClient) -> None:
    """Run every queued interactive summary item in order.

    Args:
        redis_client: the Redis client.
        queue: the job queue the build stored its job in.
        ml: the wke-ml client.
    """
    for item in await queued_summary_items(redis_client):
        await run_summary(redis_client, queue, ml, item)


async def stored_dossier(redis_client: RedisClient, job: Job) -> Dossier:
    """Read back the dossier a build stored for the job.

    Args:
        redis_client: the Redis client.
        job: the job whose page and revision name the dossier.

    Returns:
        Dossier: the stored dossier, validated.
    """
    assert job.rev_id is not None
    raw = await redis_client.get(keys.dossier(job.page_id, job.rev_id, PIPELINE_VERSION))
    assert raw is not None
    return Dossier.model_validate_json(raw)
