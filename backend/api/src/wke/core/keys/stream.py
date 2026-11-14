"""Redis keys of the trending snapshot and the live edit stream."""

from __future__ import annotations

from datetime import UTC, datetime


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

# Counter kinds of the recentchange stream: the whole wiki, and tracked pages.
ENWIKI_RC_KIND = "enwiki"
TRACKED_RC_KIND = "tracked"
# How many edits the ring keeps; older ones fall off the end.
EDITS_RING_MAX_LENGTH = 500


def minute_bucket(epoch_seconds: float) -> str:
    """Build the UTC minute bucket a recentchange counter key is dated by.

    Args:
        epoch_seconds: unix timestamp.

    Returns:
        str: `YYYYMMDDHHMM`, the UTC minute of that timestamp.
    """
    return datetime.fromtimestamp(epoch_seconds, tz=UTC).strftime("%Y%m%d%H%M")


def rc_counter(kind: str, minute: str) -> str:
    """Build a per-minute recentchange counter key.

    Args:
        kind: counter kind, e.g. `enwiki` or `tracked`.
        minute: `YYYYMMDDHHMM` UTC minute bucket.

    Returns:
        str: `rc:{kind}:{minute}`.
    """
    return f"rc:{kind}:{minute}"


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
# The watcher's resume cursor: the id of the last stream event it processed.
WATCHER_LAST_ID = "watcher:last_id"
