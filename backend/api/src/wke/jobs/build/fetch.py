"""Cached reads of a revision's timestamp, Parsoid HTML and related pages."""

from __future__ import annotations

import base64
import json
import zlib
from datetime import datetime
from typing import Any

from wke.clients.redis import RedisClient
from wke.clients.wikimedia import WikimediaClient
from wke.core import keys
from wke.metrics import CACHE_REQUESTS_TOTAL


async def fetch_revision_timestamp(
    redis: RedisClient, wikimedia: WikimediaClient, rev_id: int
) -> datetime:
    """Fetch a revision's real edit timestamp, cached forever by rev_id.

    Args:
        redis: Redis client.
        wikimedia: Wikimedia client.
        rev_id: revision id, immutable once made.

    Returns:
        datetime: the revision's edit time, UTC.
    """
    cache_key = keys.wm_revts(rev_id)
    cached = await redis.get(cache_key)
    if cached is not None:
        return datetime.fromisoformat(cached)
    raw = await wikimedia.revision_timestamp(rev_id, mode="worker")
    timestamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    await redis.set(cache_key, timestamp.isoformat(), ex=keys.WM_HTML_TTL_SECONDS)
    return timestamp


async def cached_html(redis: RedisClient, rev_id: int) -> str | None:
    """Read a revision's Parsoid HTML from the cache without fetching.

    Args:
        redis: Redis client.
        rev_id: revision id, immutable once made.

    Returns:
        str | None: the HTML, or None when it is not cached.
    """
    cached = await redis.get(keys.wm_html(rev_id))
    if cached is None:
        return None
    return zlib.decompress(base64.b64decode(cached)).decode("utf-8")


async def fetch_html(redis: RedisClient, wikimedia: WikimediaClient, rev_id: int) -> str:
    """Read a revision's Parsoid HTML from the cache or Wikimedia and cache it.

    Args:
        redis: Redis client.
        wikimedia: Wikimedia client.
        rev_id: revision id.

    Returns:
        str: the HTML.
    """
    cache_key = keys.wm_html(rev_id)
    html = await cached_html(redis, rev_id)
    if html is not None:
        CACHE_REQUESTS_TOTAL.labels(kind="html", result="hit").inc()
        return html
    CACHE_REQUESTS_TOTAL.labels(kind="html", result="miss").inc()
    html = await wikimedia.revision_html(rev_id, mode="worker")
    packed = base64.b64encode(zlib.compress(html.encode("utf-8"))).decode("ascii")
    await redis.set(cache_key, packed, ex=keys.WM_HTML_TTL_SECONDS)
    return html


async def fetch_related(
    redis: RedisClient, wikimedia: WikimediaClient, page_id: int, title: str
) -> list[dict[str, Any]]:
    """Read the related pages of an article from the cache or Wikimedia and cache them.

    Args:
        redis: Redis client.
        wikimedia: Wikimedia client.
        page_id: Wikipedia page id of the article.
        title: article title, the morelike query.

    Returns:
        list[dict]: the related page records.
    """
    cache_key = keys.wm_related(page_id)
    cached = await redis.get(cache_key)
    if cached is not None:
        CACHE_REQUESTS_TOTAL.labels(kind="related", result="hit").inc()
        return json.loads(cached)
    CACHE_REQUESTS_TOTAL.labels(kind="related", result="miss").inc()
    related = await wikimedia.morelike(title, mode="worker")
    await redis.set(cache_key, json.dumps(related), ex=keys.WM_RELATED_TTL_SECONDS)
    return related
