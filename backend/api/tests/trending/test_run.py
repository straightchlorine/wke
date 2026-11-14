"""Tests for wke.trending.run.run_trending."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from tests.support.constants import PIPELINE_VERSION
from tests.support.ml_clients import make_ml_client
from tests.support.trending import (
    FeedAnswer,
    analyze_edge_handler,
    feed_answer,
    feed_article,
    logged,
    trending_handler,
)
from tests.support.wikimedia import SyncHandler, WmFixtures, make_wikimedia_client
from wke.clients.redis import RedisClient
from wke.core import keys
from wke.core.models import GraphEdge, TrendingSnapshot
from wke.core.titles import normalize_title
from wke.jobs.queue import JobQueue
from wke.trending.run import ANALYZE_MAX_EDGES, run_trending

# mostread.json was recorded from the feed of 2026-09-27, which carries the
# most-read list of 2026-09-26.
NOW = datetime(2026, 9, 27, 3, 0, tzinfo=UTC)
TARGET_DATE = "2026-09-26"


@pytest.fixture
def job_queue(redis_client: RedisClient) -> JobQueue:
    """A JobQueue over the fakeredis-backed RedisClient."""
    return JobQueue(redis_client, PIPELINE_VERSION, 20)


async def _run(
    redis_client: RedisClient,
    job_queue: JobQueue,
    wm_fixtures: WmFixtures,
    *,
    feed: FeedAnswer | None = None,
    ml_handler: SyncHandler | None = None,
    log: list[str] | None = None,
    now: datetime = NOW,
) -> TrendingSnapshot | None:
    """Run the pipeline over the recorded feed unless `feed` replaces it."""
    handler = trending_handler(wm_fixtures, feed)
    ml = make_ml_client(ml_handler or analyze_edge_handler())
    if log is not None:
        handler = logged(handler, log)
    wikimedia = make_wikimedia_client(redis_client, handler)
    return await run_trending(wikimedia, ml, redis_client, job_queue, PIPELINE_VERSION, now=now)


async def test_snapshot_shape_from_wikifeeds_mostread(
    redis_client: RedisClient, job_queue: JobQueue, wm_fixtures: WmFixtures
) -> None:
    snapshot = await _run(redis_client, job_queue, wm_fixtures)

    assert snapshot is not None
    validated = TrendingSnapshot.model_validate_json(snapshot.model_dump_json())
    assert validated.source == "wikifeeds_mostread"
    assert str(validated.date) == TARGET_DATE
    assert validated.generated_at == NOW
    assert [topic.rank for topic in validated.topics] == list(range(1, len(validated.topics) + 1))
    recorded = {a["pageid"]: a for a in wm_fixtures.json("mostread.json")["articles"]}
    for topic in validated.topics:
        article = recorded[topic.page_id]
        assert topic.rev_id == int(article["revision"])
        assert topic.views == article["views"]
        assert topic.lead_excerpt == article["extract"][:280]
        assert topic.edits_last_hour is None

    stored = await redis_client.get(keys.trending_snapshot(TARGET_DATE))
    assert stored == snapshot.model_dump_json()
    assert await redis_client.get(keys.TRENDING_LATEST) == stored
    assert (
        0
        < await redis_client.ttl(keys.trending_snapshot(TARGET_DATE))
        <= (keys.TRENDING_SNAPSHOT_TTL_SECONDS)
    )
    assert await redis_client.ttl(keys.TRENDING_LATEST) == -1


async def test_idempotent_second_run_makes_zero_http_calls(
    redis_client: RedisClient, job_queue: JobQueue, wm_fixtures: WmFixtures
) -> None:
    log: list[str] = []

    first = await _run(redis_client, job_queue, wm_fixtures, log=log)
    assert first is not None
    calls_after_first = len(log)
    assert calls_after_first > 0

    assert await _run(redis_client, job_queue, wm_fixtures, log=log) is None
    assert len(log) == calls_after_first


async def test_pageviews_fallback_snapshot_records_its_source(
    redis_client: RedisClient, job_queue: JobQueue, wm_fixtures: WmFixtures
) -> None:
    feed = feed_answer(wm_fixtures, date="2026-09-25Z")

    snapshot = await _run(redis_client, job_queue, wm_fixtures, feed=feed)

    assert snapshot is not None
    assert snapshot.source == "pageviews_top"
    assert str(snapshot.date) == TARGET_DATE
    assert await redis_client.exists(keys.trending_snapshot(TARGET_DATE))


async def test_no_candidates_stores_nothing(
    redis_client: RedisClient, job_queue: JobQueue, wm_fixtures: WmFixtures
) -> None:
    articles = [feed_article(wm_fixtures, 0, title="Main_Page", normalizedtitle="Main Page")]

    snapshot = await _run(
        redis_client, job_queue, wm_fixtures, feed=feed_answer(wm_fixtures, articles=articles)
    )

    assert snapshot is None
    assert not await redis_client.exists(keys.trending_snapshot(TARGET_DATE))
    assert not await redis_client.exists(keys.TRENDING_LATEST)


async def test_snapshot_edges_come_from_one_analyze_call_over_the_leads(
    redis_client: RedisClient, job_queue: JobQueue, wm_fixtures: WmFixtures
) -> None:
    payloads: list[dict[str, Any]] = []

    snapshot = await _run(
        redis_client, job_queue, wm_fixtures, ml_handler=analyze_edge_handler(payloads)
    )

    assert snapshot is not None
    seed, second = snapshot.topics[0], snapshot.topics[1]
    assert snapshot.edges == [GraphEdge(source=seed.page_id, target=second.page_id, weight=0.5)]
    assert len(payloads) == 1
    assert payloads[0]["page_id"] == seed.page_id
    assert payloads[0]["lead"] == seed.lead_excerpt
    assert payloads[0]["chunks"] == []
    assert payloads[0]["max_edges"] == ANALYZE_MAX_EDGES
    assert payloads[0]["related_leads"] == [
        {"page_id": topic.page_id, "text": topic.lead_excerpt} for topic in snapshot.topics[1:]
    ]


async def test_topic_without_an_extract_has_no_excerpt_and_an_empty_lead_for_analyze(
    redis_client: RedisClient, job_queue: JobQueue, wm_fixtures: WmFixtures
) -> None:
    articles = [feed_article(wm_fixtures, 0, extract=None), feed_article(wm_fixtures, 1)]
    payloads: list[dict[str, Any]] = []

    snapshot = await _run(
        redis_client,
        job_queue,
        wm_fixtures,
        feed=feed_answer(wm_fixtures, articles=articles),
        ml_handler=analyze_edge_handler(payloads),
    )

    assert snapshot is not None
    assert snapshot.topics[0].lead_excerpt is None
    assert payloads[0]["lead"] == ""


async def test_snapshot_is_stored_without_edges_when_wke_ml_is_down(
    redis_client: RedisClient, job_queue: JobQueue, wm_fixtures: WmFixtures
) -> None:
    snapshot = await _run(
        redis_client,
        job_queue,
        wm_fixtures,
        ml_handler=lambda _request: httpx.Response(503),
    )

    assert snapshot is not None
    assert snapshot.edges == []
    assert snapshot.topics
    assert await redis_client.exists(keys.TRENDING_LATEST)


async def test_single_topic_skips_the_analyze_call(
    redis_client: RedisClient, job_queue: JobQueue, wm_fixtures: WmFixtures
) -> None:
    def no_ml(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("wke-ml must not be called for one topic")

    articles = [feed_article(wm_fixtures, 0)]

    snapshot = await _run(
        redis_client,
        job_queue,
        wm_fixtures,
        feed=feed_answer(wm_fixtures, articles=articles),
        ml_handler=no_ml,
    )

    assert snapshot is not None
    assert len(snapshot.topics) == 1
    assert snapshot.edges == []


async def test_every_topic_is_tracked_even_when_admission_is_rejected(
    redis_client: RedisClient, wm_fixtures: WmFixtures
) -> None:
    """A queue_full rejection must not leave a trending topic untracked."""
    full_queue = JobQueue(redis_client, PIPELINE_VERSION, queue_cap=0, background_queue_cap=0)
    # A decomposed accent: the watcher looks titles up by their normalized form.
    articles = [
        feed_article(wm_fixtures, 0, normalizedtitle="Cafe\u0301 society"),
        feed_article(wm_fixtures, 1),
    ]

    snapshot = await _run(
        redis_client, full_queue, wm_fixtures, feed=feed_answer(wm_fixtures, articles=articles)
    )

    assert snapshot is not None
    assert snapshot.topics
    assert await redis_client.llen(keys.QUEUE_BACKGROUND) == 0
    for topic in snapshot.topics:
        assert await redis_client.sismember(keys.TRACKED, str(topic.page_id)) is True
        cached = await redis_client.hget(keys.TRACKED_PAGE_IDS, normalize_title(topic.title))
        assert cached == str(topic.page_id)


async def test_background_enqueue_skips_ready_dossier(
    redis_client: RedisClient, wm_fixtures: WmFixtures
) -> None:
    ready = feed_article(wm_fixtures, 0)
    ready_rev_id = int(ready["revision"])
    dossier_key = keys.dossier(ready["pageid"], ready_rev_id, PIPELINE_VERSION)
    await redis_client.set(dossier_key, json.dumps({"build": {"state": "complete"}}))
    job_queue = JobQueue(redis_client, PIPELINE_VERSION, queue_cap=50)

    snapshot = await _run(redis_client, job_queue, wm_fixtures)

    assert snapshot is not None
    assert snapshot.topics[0].dossier_state == "ready"
    not_ready = [t for t in snapshot.topics if t.dossier_state != "ready"]
    assert len(not_ready) == len(snapshot.topics) - 1
    assert await redis_client.get(keys.jobkey(ready["pageid"], ready_rev_id)) is None
    assert await redis_client.llen(keys.QUEUE_BACKGROUND) == len(not_ready)


@pytest.mark.parametrize(
    ("stored_dossier", "job_in_flight", "expected_state"),
    [
        (json.dumps({"build": {"state": "complete"}}), False, "ready"),
        (json.dumps({"build": {"state": "running"}}), False, "partial"),
        (json.dumps({}), False, "partial"),
        ("not json", False, "none"),
        ("null", False, "none"),
        (None, True, "building"),
        ("not json", True, "building"),
        (None, False, "none"),
    ],
)
async def test_dossier_state_of_the_pinned_revision(
    redis_client: RedisClient,
    job_queue: JobQueue,
    wm_fixtures: WmFixtures,
    stored_dossier: str | None,
    job_in_flight: bool,
    expected_state: str,
) -> None:
    first = feed_article(wm_fixtures, 0)
    page_id, rev_id = first["pageid"], int(first["revision"])
    if stored_dossier is not None:
        await redis_client.set(keys.dossier(page_id, rev_id, PIPELINE_VERSION), stored_dossier)
    if job_in_flight:
        await redis_client.set(keys.jobkey(page_id, rev_id), "0123456789abcdef")

    snapshot = await _run(redis_client, job_queue, wm_fixtures)

    assert snapshot is not None
    assert snapshot.topics[0].dossier_state == expected_state


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (datetime(2026, 9, 27, 1, 0, tzinfo=UTC), datetime(2026, 9, 27, 3, 0, tzinfo=UTC)),
        (datetime(2026, 9, 27, 3, 0, tzinfo=UTC), datetime(2026, 9, 28, 3, 0, tzinfo=UTC)),
        (datetime(2026, 9, 27, 3, 0, 5, tzinfo=UTC), datetime(2026, 9, 28, 3, 0, tzinfo=UTC)),
    ],
    ids=["before-todays-run", "at-todays-run", "after-todays-run"],
)
async def test_next_refresh_is_the_next_03_00_utc_strictly_after_the_run(
    redis_client: RedisClient,
    job_queue: JobQueue,
    wm_fixtures: WmFixtures,
    moment: datetime,
    expected: datetime,
) -> None:
    snapshot = await _run(redis_client, job_queue, wm_fixtures, now=moment)

    assert snapshot is not None
    assert snapshot.next_refresh == expected
