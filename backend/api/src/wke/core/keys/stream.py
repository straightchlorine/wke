"""Redis keys of the trending snapshot and the live edit stream."""

from __future__ import annotations


def trending_snapshot(iso_date: str) -> str:
    """Build the dated trending snapshot key.

    Args:
        iso_date: snapshot date, `YYYY-MM-DD`.

    Returns:
        str: `trending:{date}`.
    """
    return f"trending:{iso_date}"


TRENDING_LATEST = "trending:latest"
EDITS_RING = "edits"
EDITS_SEQ = "edits:seq"


def rc_counter(kind: str, minute_bucket: str) -> str:
    """Build a per-minute recentchange counter key.

    Args:
        kind: counter kind, e.g. `enwiki` or `tracked`.
        minute_bucket: `YYYYMMDDHHMM` UTC minute bucket.

    Returns:
        str: `rc:{kind}:{minute}`.
    """
    return f"rc:{kind}:{minute_bucket}"


def latest_rev(page_id: int) -> str:
    """Build the watcher's latest-revision pointer key.

    Args:
        page_id: Wikipedia page id.

    Returns:
        str: `latest_rev:{page_id}`.
    """
    return f"latest_rev:{page_id}"


def pageedits(page_id: int) -> str:
    """Build the per-page edit-timestamp ZSET key.

    Args:
        page_id: Wikipedia page id.

    Returns:
        str: `pageedits:{page_id}`.
    """
    return f"pageedits:{page_id}"


# Written by the watcher's heartbeat loop;
# read by GET /api/v1/status as `watcher_connected`.
WATCHER_HEARTBEAT = "watcher:heartbeat"
