"""Read-time freshness classification and settle-window background rebuilds."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from wke.clients.redis import RedisClient
from wke.core import keys
from wke.core.models import Freshness
from wke.jobs.queue import JobQueue

logger = logging.getLogger(__name__)

STALE_REBUILD_AGE_SECONDS = 30 * 60
QUIET_WINDOW_SECONDS = 5 * 60


def _unknown(pinned_rev_id: int) -> Freshness:
    """Build the freshness of a dossier the watcher has no data for.

    Args:
        pinned_rev_id: the dossier's pinned revision id.

    Returns:
        Freshness: state "unknown", source "none", no latest revision, no
        edit count and no checked_at.
    """
    return Freshness(
        state="unknown",
        pinned_rev_id=pinned_rev_id,
        latest_rev_id=None,
        edits_since=None,
        source="none",
    )


async def count_edits_since(redis: RedisClient, page_id: int, since: datetime) -> int:
    """Count the watcher-recorded edits of a page made after a moment.

    Args:
        redis: Redis client.
        page_id: Wikipedia page id.
        since: the exclusive lower bound, normally a dossier's build.built_at.

    Returns:
        int: the members of `pageedits:{page_id}` scored after `since`.
    """
    return await redis.zcount(keys.pageedits(page_id), f"({since.timestamp()}", "+inf")


async def compute_freshness(
    redis: RedisClient, page_id: int, pinned_rev_id: int, built_at: datetime
) -> Freshness:
    """Classify a dossier's freshness against the watcher's latest pointer.

    Args:
        redis: Redis client.
        page_id: Wikipedia page id.
        pinned_rev_id: the dossier's pinned revision id.
        built_at: the dossier's build.built_at, the edits_since cutoff.

    Returns:
        Freshness: state fresh/stale (watcher source) or unknown (no
        watcher pointer yet, poll fallback not built), with edits_since
        counted from `pageedits:{page_id}` after built_at when the state
        is known. checked_at is when the watcher recorded the latest
        revision, read from `pageedits:{page_id}`; it is None (source
        "none") when the watcher has no data for the page, and is never
        the time of this call.
    """
    latest_raw = await redis.get(keys.latest_rev(page_id))
    if latest_raw is None:
        return _unknown(pinned_rev_id)
    try:
        latest_rev_id = int(latest_raw)
    except ValueError:
        logger.warning("malformed latest_rev:%s value; treating as unknown", page_id)
        return _unknown(pinned_rev_id)

    observed_at = await redis.zscore(keys.pageedits(page_id), str(latest_rev_id))
    checked_at = datetime.fromtimestamp(observed_at, UTC) if observed_at is not None else None
    edits_since = await count_edits_since(redis, page_id, built_at)
    state = "fresh" if latest_rev_id <= pinned_rev_id else "stale"
    return Freshness(
        state=state,
        pinned_rev_id=pinned_rev_id,
        latest_rev_id=latest_rev_id,
        edits_since=edits_since,
        checked_at=checked_at,
        source="watcher",
    )


async def maybe_enqueue_rebuild(
    redis: RedisClient,
    job_queue: JobQueue,
    page_id: int,
    title: str,
    built_at: datetime,
) -> bool:
    """Enqueue a background rebuild if the settle-window rule allows it.

    Rebuilds onto q:background only when the current build is older than
    30 min AND the page has been quiet for at least 5 min (no edit more
    recent than now - 300s), debounced by `SET rebuild:{page_id} NX EX
    1800` so an edit war costs at most 2 rebuilds per page per hour.

    Args:
        redis: Redis client.
        job_queue: JobQueue to admit the rebuild job on.
        page_id: Wikipedia page id.
        title: article title, stored on the rebuild Job for display.
        built_at: the current dossier's build.built_at.

    Returns:
        bool: True if a rebuild was admitted, False if the settle-window
        rule did not match or the debounce key was already set.
    """
    now = datetime.now(UTC)
    if (now - built_at).total_seconds() <= STALE_REBUILD_AGE_SECONDS:
        return False

    latest_raw = await redis.get(keys.latest_rev(page_id))
    if latest_raw is None:
        return False
    try:
        latest_rev_id = int(latest_raw)
    except ValueError:
        logger.warning("malformed latest_rev:%s value; skipping rebuild", page_id)
        return False

    last_edit_ts = await redis.zscore(keys.pageedits(page_id), str(latest_rev_id))
    if last_edit_ts is None:
        return False
    if (now.timestamp() - last_edit_ts) < QUIET_WINDOW_SECONDS:
        return False

    acquired = await redis.set(
        keys.rebuild_debounce(page_id), "1", ex=keys.REBUILD_DEBOUNCE_TTL_SECONDS, nx=True
    )
    if not acquired:
        return False

    await job_queue.admit(page_id, latest_rev_id, title, background=True)
    return True
