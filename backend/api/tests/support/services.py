"""A DossierService over fakeredis and a mock Wikimedia transport."""

from __future__ import annotations

import json

import httpx

from tests.support.constants import PIPELINE_VERSION, REQUIRED_ENV
from tests.support.wikimedia import Handler, make_wikimedia_client
from wke.clients.redis import RedisClient
from wke.core import keys
from wke.core.citations import seed_pin
from wke.core.models import Dossier
from wke.jobs.queue import JobQueue
from wke.services.dossiers import DossierService


def _not_found(request: httpx.Request) -> httpx.Response:
    return httpx.Response(404)


def make_service(
    redis_client: RedisClient,
    handler: Handler = _not_found,
    *,
    pipeline_version: str = PIPELINE_VERSION,
    public_host: str = REQUIRED_ENV["PUBLIC_HOST"],
) -> DossierService:
    """Build a DossierService whose Wikimedia calls are answered by `handler`.

    Args:
        redis_client: the RedisClient the service and its job queue share.
        handler: the MockTransport handler for Wikimedia; every call gets a
            404 when omitted.
        pipeline_version: the pipeline version the service reads and builds.
        public_host: the host its absolute links are rooted at (https).

    Returns:
        DossierService: wired to a JobQueue with a cap of 20.
    """
    wikimedia = make_wikimedia_client(redis_client, handler)
    job_queue = JobQueue(redis_client, pipeline_version, queue_cap=20)
    return DossierService(redis_client, wikimedia, job_queue, pipeline_version, public_host)


async def seed_dossier(
    redis_client: RedisClient, dossier: Dossier, pipeline_version: str = PIPELINE_VERSION
) -> None:
    """Write a dossier, its `ptr` and its `built` entry as the pipeline would.

    Args:
        redis_client: the RedisClient to write to.
        dossier: the dossier to store, at its seed pin's revision.
        pipeline_version: the pipeline version in the dossier key and pointer.
    """
    page_id = dossier.topic.page_id
    rev_id = seed_pin(dossier).rev_id
    pointer = {
        "rev_id": rev_id,
        "pipeline_version": pipeline_version,
        "built_at": dossier.build.built_at.isoformat(),
    }
    await redis_client.set(keys.ptr(page_id), json.dumps(pointer))
    await redis_client.set(
        keys.dossier(page_id, rev_id, pipeline_version), dossier.model_dump_json()
    )
    await redis_client.zadd(keys.BUILT, {str(page_id): dossier.build.built_at.timestamp()})


def renamed(dossier: Dossier, page_id: int, title: str) -> Dossier:
    """Copy a dossier under another page id and title, for catalogs of several pages.

    Args:
        dossier: the dossier to copy.
        page_id: the page id of the copy.
        title: the topic title of the copy.

    Returns:
        Dossier: the copy; its citations and revision are unchanged.
    """
    topic = dossier.topic.model_copy(update={"page_id": page_id, "title": title})
    return dossier.model_copy(update={"topic": topic})
