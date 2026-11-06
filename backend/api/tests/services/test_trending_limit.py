"""DossierService.get_trending keeps only the edges whose both ends are in the kept topics."""

from __future__ import annotations

import json

from tests.support.constants import PIPELINE_VERSION
from tests.support.snapshots import make_snapshot
from wke.clients.redis import RedisClient
from wke.clients.wikimedia import WikimediaClient
from wke.core import keys
from wke.jobs.queue import JobQueue
from wke.services.dossiers import DossierService


async def test_limit_drops_edges_with_an_end_outside_the_topics(
    redis_client: RedisClient, wikimedia_client: WikimediaClient
) -> None:
    page_ids = (101, 102, 103)
    topics = [
        {**make_snapshot(page_id=page_id)["topics"][0], "rank": rank}
        for rank, page_id in enumerate(page_ids, start=1)
    ]
    edges = [
        {"source": 101, "target": 102, "weight": 0.9},
        {"source": 102, "target": 103, "weight": 0.8},
        {"source": 101, "target": 103, "weight": 0.7},
    ]
    snapshot = make_snapshot(topics=topics, edges=edges)
    await redis_client.set(keys.TRENDING_LATEST, json.dumps(snapshot))
    queue = JobQueue(redis_client, PIPELINE_VERSION, queue_cap=20)
    service = DossierService(redis_client, wikimedia_client, queue, PIPELINE_VERSION)

    trimmed = await service.get_trending(2)

    assert [topic.page_id for topic in trimmed.topics] == [101, 102]
    assert [(e.source, e.target, e.weight) for e in trimmed.edges] == [(101, 102, 0.9)]
