"""Trending pipeline (`python -m wke.trending`).

Yesterday UTC's Wikifeeds mostread (the feed of today's date, verified by
its own `date`; falling back to Pageviews top on a 404 or a mismatch) ->
candidate filters -> up to 40 `TrendingTopic` -> one `analyze` call for
the home-graph edges -> `TrendingSnapshot` stored at `trending:{date}` and
`trending:latest` -> a background build enqueued for every topic without a
ready dossier.

Idempotent: a run for a date whose `trending:{date}` key already exists
returns immediately, before any HTTP call.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from wke.clients.ml import MLClient, MLUnavailable
from wke.clients.redis import RedisClient
from wke.clients.wikimedia import WikimediaClient
from wke.core import keys
from wke.core.errors import ApiException
from wke.core.models import DossierState, GraphEdge, TrendingSnapshot, TrendingTopic
from wke.core.titles import normalize_title
from wke.jobs.queue import JobQueue
from wke.trending.filters import select_candidates
from wke.trending.sources import MAX_TOPICS, SleepFn, fetch_mostread_with_fallback

logger = logging.getLogger(__name__)

EXCERPT_MAX_CHARS = 280
ANALYZE_MAX_EDGES = 80

# The nightly job runs at 03:00 UTC (cron "0 3 * * *"). The schedule lives
# in the deployment, not in Settings: changing it means editing both the
# CronJob and this constant.
TRENDING_REFRESH_HOUR_UTC = 3


async def run_trending(
    wikimedia: WikimediaClient,
    ml: MLClient,
    redis: RedisClient,
    job_queue: JobQueue,
    pipeline_version: str,
    now: datetime | None = None,
    sleep: SleepFn = asyncio.sleep,
) -> TrendingSnapshot | None:
    """Build, store and enqueue prebuilds for yesterday's trending snapshot.

    Args:
        wikimedia: shared Wikimedia client (mostread/pageviews_top/page_extracts).
        ml: wke-ml client, for the home-graph analyze call.
        redis: shared Redis client.
        job_queue: background build admission queue.
        pipeline_version: PIPELINE_VERSION setting, for dossier/job keys.
        now: current UTC time; defaults to `datetime.now(UTC)`.
        sleep: injectable sleep, for the Wikifeeds-404 retry wait; tests
            pass a no-op or a counting stub to run instantly.

    Returns:
        TrendingSnapshot | None: the stored snapshot, or None if
        `trending:{date}` already existed (idempotent no-op, zero HTTP
        calls) or no candidate topics survived filtering.
    """
    moment = now or datetime.now(UTC)
    target_date = (moment - timedelta(days=1)).date()
    iso_date = target_date.isoformat()

    snapshot_key = keys.trending_snapshot(iso_date)
    if await redis.exists(snapshot_key):
        logger.info("trending:%s already exists, skipping", iso_date)
        return None

    articles, source = await fetch_mostread_with_fallback(wikimedia, iso_date, sleep)
    candidates = select_candidates(articles, limit=MAX_TOPICS)
    if not candidates:
        logger.warning("no trending candidates for %s after filtering", iso_date)
        return None

    topics = await _build_topics(redis, candidates, pipeline_version)
    snapshot = TrendingSnapshot(
        date=target_date,
        source=source,
        source_url=None,
        generated_at=moment,
        next_refresh=_next_refresh(moment),
        topics=topics,
        edges=await _compute_edges(ml, topics),
    )
    await _store_snapshot(redis, snapshot, snapshot_key)
    await _track_topics(redis, topics)
    await _enqueue_prebuilds(job_queue, topics)
    return snapshot


async def _build_topics(
    redis: RedisClient, candidates: list[dict[str, Any]], pipeline_version: str
) -> list[TrendingTopic]:
    """Turn the filtered candidate rows into ranked topics with dossier state.

    Args:
        redis: shared Redis client.
        candidates: filtered rows, most viewed first.
        pipeline_version: PIPELINE_VERSION setting, for the dossier keys.

    Returns:
        list[TrendingTopic]: one topic per candidate, ranked from 1.
    """
    topics: list[TrendingTopic] = []
    for rank, article in enumerate(candidates, start=1):
        state = await _dossier_state(redis, article["page_id"], article["rev_id"], pipeline_version)
        topics.append(
            TrendingTopic(
                rank=rank,
                page_id=article["page_id"],
                title=article["title"],
                description=article.get("description"),
                views=article["views"],
                rev_id=article["rev_id"],
                lead_excerpt=_excerpt(article.get("extract")),
                dossier_state=state,
                # DossierService.get_trending recomputes this live against
                # pageedits:{page_id}; the snapshot itself never has a
                # real "last 1 h" number to freeze.
                edits_last_hour=None,
            )
        )
    return topics


async def _store_snapshot(
    redis: RedisClient, snapshot: TrendingSnapshot, snapshot_key: str
) -> None:
    """Write the snapshot under its date key and as the latest one.

    Args:
        redis: shared Redis client.
        snapshot: the snapshot to store.
        snapshot_key: the dated `trending:{date}` key.
    """
    payload = snapshot.model_dump_json()
    await redis.set(snapshot_key, payload, ex=keys.TRENDING_SNAPSHOT_TTL_SECONDS)
    await redis.set(keys.TRENDING_LATEST, payload)


async def _track_topics(redis: RedisClient, topics: list[TrendingTopic]) -> None:
    """Track all topics so the watcher can resolve them by page_id and count them.

    Args:
        redis: shared Redis client.
        topics: the snapshot's topics.
    """
    for topic in topics:
        await redis.sadd(keys.TRACKED, str(topic.page_id))
        await redis.hset(keys.TRACKED_PAGE_IDS, normalize_title(topic.title), str(topic.page_id))


async def _enqueue_prebuilds(job_queue: JobQueue, topics: list[TrendingTopic]) -> None:
    """Queue a background build for every topic without a ready dossier.

    Args:
        job_queue: background build admission queue.
        topics: the snapshot's topics.
    """
    for topic in topics:
        if topic.dossier_state == "ready":
            continue
        try:
            await job_queue.admit(topic.page_id, topic.rev_id, topic.title, background=True)
        except ApiException as exc:
            logger.warning("background build not admitted for page_id=%s: %s", topic.page_id, exc)


def _next_refresh(moment: datetime) -> datetime:
    """Next scheduled trending run after `moment`, from the CronJob schedule.

    Args:
        moment: the run's start time (the `now` argument to run_trending).

    Returns:
        datetime: the next TRENDING_REFRESH_HOUR_UTC:00 UTC strictly after
        `moment` -- tomorrow's if `moment` is already at or past today's.
    """
    candidate = moment.replace(hour=TRENDING_REFRESH_HOUR_UTC, minute=0, second=0, microsecond=0)
    if candidate <= moment:
        candidate += timedelta(days=1)
    return candidate


def _excerpt(extract: str | None) -> str | None:
    """Truncate a lead extract to the TrendingTopic.lead_excerpt cap.

    Args:
        extract: verbatim extract text, or None.

    Returns:
        str | None: first 280 characters, or None.
    """
    if not extract:
        return None
    return extract[:EXCERPT_MAX_CHARS]


async def _dossier_state(
    redis: RedisClient, page_id: int, rev_id: int, pipeline_version: str
) -> DossierState:
    """Read a topic's dossier build state.

    Unlike `DossierService._dossier_state`, the trending job already
    knows the topic's pinned `rev_id` (from mostread/pageviews), so it
    checks `dossier:{page_id}:{rev_id}:{pv}` directly instead of
    resolving through `ptr:{page_id}` first -- the same key `JobQueue
    .admit` checks to short-circuit to "ready" -- and can additionally
    distinguish "building" (a job is in flight for that exact revision)
    from "none".

    Args:
        redis: shared Redis client.
        page_id: Wikipedia page id.
        rev_id: pinned revision id from the trending source.
        pipeline_version: PIPELINE_VERSION setting.

    Returns:
        DossierState: "ready", "partial", "building" or "none".
    """
    state: DossierState = "none"
    dossier_key = keys.dossier(page_id, rev_id, pipeline_version)
    raw = await redis.get(dossier_key)
    if raw is not None:
        try:
            data = json.loads(raw)
            build_state = data.get("build", {}).get("state")
            state = "ready" if build_state == "complete" else "partial"
        except (ValueError, AttributeError):
            state = "none"

    if state == "none":
        job_id = await redis.get(keys.jobkey(page_id, rev_id))
        if job_id is not None:
            state = "building"

    return state


async def _compute_edges(ml: MLClient, topics: list[TrendingTopic]) -> list[GraphEdge]:
    """Build the home-graph edges with one analyze call over all topic leads.

    Args:
        ml: wke-ml client.
        topics: ranked trending topics (already built with lead_excerpt).

    Returns:
        list[GraphEdge]: the edges wke-ml returns for the first topic against
        the others, or an empty list if fewer than 2 topics exist or wke-ml
        is unavailable.
    """
    if len(topics) < 2:
        return []
    seed, rest = topics[0], topics[1:]
    related_leads = [{"page_id": t.page_id, "text": t.lead_excerpt or ""} for t in rest]
    try:
        result = await ml.analyze(
            lead=seed.lead_excerpt or "",
            chunks=[],
            related_leads=related_leads,
            page_id=seed.page_id,
            max_edges=ANALYZE_MAX_EDGES,
        )
    except MLUnavailable as exc:
        logger.warning("wke-ml unavailable for trending edges: %s", exc.reason)
        return []
    return [GraphEdge(**edge) for edge in result.get("edges", [])]
