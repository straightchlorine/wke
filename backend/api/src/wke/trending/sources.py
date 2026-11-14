"""Candidate rows for the trending snapshot: Wikifeeds mostread, Pageviews fallback."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from typing import Any, Literal

from wke.clients.wikimedia import WikifeedsNotFound, WikimediaClient
from wke.core.errors import ApiException
from wke.core.titles import normalize_title
from wke.trending.filters import select_candidates

logger = logging.getLogger(__name__)

MAX_TOPICS = 40
EXTRACTS_BATCH_SIZE = 20
WIKIFEEDS_RETRY_INTERVAL_SECONDS = 60
WIKIFEEDS_RETRY_BUDGET_SECONDS = 600

SleepFn = Callable[[float], Awaitable[None]]
TrendingSource = Literal["wikifeeds_mostread", "pageviews_top"]


def _from_mostread(body: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize a Wikifeeds mostread body into candidate rows.

    Args:
        body: the `mostread(date)` response.

    Returns:
        list[dict]: rows with raw_title, title, page_id, rev_id,
        description, views, extract. Rows missing page_id or revision
        are dropped.
    """
    rows: list[dict[str, Any]] = []
    for entry in body.get("articles", []):
        raw_title = entry.get("title") or entry.get("normalizedtitle")
        page_id = entry.get("pageid")
        revision = entry.get("revision")
        if not raw_title or page_id is None or revision is None:
            continue
        rows.append(
            {
                "raw_title": raw_title,
                "title": entry.get("normalizedtitle") or raw_title.replace("_", " "),
                "page_id": page_id,
                "rev_id": int(revision),
                "description": entry.get("description"),
                "views": entry.get("views", 0),
                "extract": entry.get("extract"),
            }
        )
    return rows


async def fetch_mostread_with_fallback(
    wikimedia: WikimediaClient, iso_date: str, sleep: SleepFn
) -> tuple[list[dict[str, Any]], TrendingSource]:
    """Stage 1: Wikifeeds mostread, retried on 404, falling back to Pageviews.

    The feed for day D holds the most-read list of day D-1, so the target
    date's list is requested from the feed of the next day and its
    `mostread.date` is checked against the target; a different date falls
    back like an outage does.

    Wikifeeds sometimes has not published that feed yet; a single
    404 is not "the feed is gone", so this retries every 60s for up to
    10 minutes before treating the feed as unavailable. A persistent
    Wikifeeds outage (upstream_unavailable after the Wikimedia client's
    own 5xx retries) is not retried again here -- it falls back
    immediately, since that already means the feed will not answer soon.

    Args:
        wikimedia: shared Wikimedia client.
        iso_date: ISO date `YYYY-MM-DD` (yesterday UTC).
        sleep: injectable sleep for the retry wait.

    Returns:
        tuple[list[dict], TrendingSource]: rows shaped like
        `_from_mostread`'s output, and which source they came from.
    """
    feed_date = (date.fromisoformat(iso_date) + timedelta(days=1)).isoformat()
    waited_seconds = 0
    while True:
        try:
            body = await wikimedia.mostread(feed_date, mode="worker")
            carried = str(body.get("date", ""))[:10]
            if carried != iso_date:
                logger.warning(
                    "Wikifeeds feed %s carries mostread date %r, expected %s, "
                    "falling back to pageviews_top",
                    feed_date,
                    body.get("date"),
                    iso_date,
                )
                break
            return _from_mostread(body), "wikifeeds_mostread"
        except WikifeedsNotFound:
            if waited_seconds >= WIKIFEEDS_RETRY_BUDGET_SECONDS:
                logger.warning(
                    "Wikifeeds still 404 for %s after %ss, falling back to pageviews_top",
                    iso_date,
                    waited_seconds,
                )
                break
            logger.warning(
                "Wikifeeds 404 for %s, retrying in %ss", iso_date, WIKIFEEDS_RETRY_INTERVAL_SECONDS
            )
            await sleep(WIKIFEEDS_RETRY_INTERVAL_SECONDS)
            waited_seconds += WIKIFEEDS_RETRY_INTERVAL_SECONDS
        except ApiException as exc:
            if exc.code != "upstream_unavailable":
                raise
            logger.warning(
                "Wikifeeds unavailable for %s (%s), falling back to pageviews_top",
                iso_date,
                exc.detail,
            )
            break

    articles = await _from_pageviews(wikimedia, iso_date)
    return articles, "pageviews_top"


async def _from_pageviews(wikimedia: WikimediaClient, iso_date: str) -> list[dict[str, Any]]:
    """Fallback path: Pageviews top titles enriched with batched extracts.

    Filters and caps the raw Pageviews rows first, then fetches
    extract/description/lastrevid for only the surviving titles, in
    batches of 20 (TextExtracts `exlimit`).

    Args:
        wikimedia: shared Wikimedia client.
        iso_date: ISO date `YYYY-MM-DD` (yesterday UTC).

    Returns:
        list[dict]: rows shaped like `_from_mostread`'s output. Titles
        the Action API reports missing are dropped.
    """
    body = await wikimedia.pageviews_top(iso_date, mode="worker")
    raw_rows = [
        {"raw_title": item["article"], "views": item.get("views", 0)}
        for item in body.get("articles", [])
        if item.get("article")
    ]
    filtered = select_candidates(raw_rows, limit=MAX_TOPICS)

    enriched: dict[str, dict[str, Any]] = {}
    titles = [row["raw_title"] for row in filtered]
    for start in range(0, len(titles), EXTRACTS_BATCH_SIZE):
        batch = titles[start : start + EXTRACTS_BATCH_SIZE]
        for page in await wikimedia.page_extracts(batch, mode="worker"):
            if page.get("missing") or "pageid" not in page or "lastrevid" not in page:
                continue
            enriched[normalize_title(page.get("title", ""))] = page

    rows: list[dict[str, Any]] = []
    for row in filtered:
        key = normalize_title(row["raw_title"].replace("_", " "))
        page = enriched.get(key)
        if page is None:
            continue
        rows.append(
            {
                "raw_title": row["raw_title"],
                "title": page["title"],
                "page_id": page["pageid"],
                "rev_id": int(page["lastrevid"]),
                "description": page.get("description"),
                "views": row["views"],
                "extract": page.get("extract"),
            }
        )
    return rows
