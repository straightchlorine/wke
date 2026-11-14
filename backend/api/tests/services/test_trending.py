"""The trending view: truncation, edges between kept topics, live state and edit counts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from tests.factories.dossier import make_fixture_dossier
from tests.support.services import make_service, renamed, seed_dossier
from tests.support.snapshots import make_snapshot
from wke.clients.redis import RedisClient
from wke.core import keys


def _topic(rank: int, page_id: int) -> dict[str, Any]:
    topic = make_snapshot(page_id=page_id)["topics"][0]
    return {**topic, "rank": rank, "title": f"Topic {page_id}", "edits_last_hour": 99}


async def _store_snapshot(redis_client: RedisClient, page_ids: list[int]) -> None:
    snapshot = make_snapshot(
        topics=[_topic(rank, page_id) for rank, page_id in enumerate(page_ids, start=1)],
        edges=[
            {"source": 1, "target": 2, "weight": 0.5},
            {"source": 2, "target": 3, "weight": 0.5},
            {"source": 1, "target": 3, "weight": 0.5},
        ],
    )
    await redis_client.set(keys.TRENDING_LATEST, json.dumps(snapshot))


async def test_limit_keeps_the_top_topics_and_only_edges_between_them(
    redis_client: RedisClient,
) -> None:
    await _store_snapshot(redis_client, [1, 2, 3])

    snapshot = await make_service(redis_client).get_trending(2)

    assert [topic.page_id for topic in snapshot.topics] == [1, 2]
    assert [(edge.source, edge.target) for edge in snapshot.edges] == [(1, 2)]


@pytest.mark.parametrize("limit", [0, -1])
async def test_a_limit_below_one_keeps_no_topics(redis_client: RedisClient, limit: int) -> None:
    await _store_snapshot(redis_client, [1, 2, 3])

    snapshot = await make_service(redis_client).get_trending(limit)

    assert snapshot.topics == []
    assert snapshot.edges == []


async def test_state_and_edit_count_are_read_live_not_taken_from_the_snapshot(
    redis_client: RedisClient,
) -> None:
    ready = renamed(make_fixture_dossier(), 1, "Topic 1")
    await seed_dossier(redis_client, ready)
    await _store_snapshot(redis_client, [1, 2])
    now = datetime.now(UTC).timestamp()
    await redis_client.zadd(keys.pageedits(1), {"10": now - 600, "11": now - 5400})

    snapshot = await make_service(redis_client).get_trending(10)

    assert [(t.dossier_state, t.edits_last_hour) for t in snapshot.topics] == [
        ("ready", 1),
        ("none", 0),
    ]
