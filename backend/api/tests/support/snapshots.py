"""Trending snapshot factory."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from tests.support.constants import FIXTURE_PAGE_ID, FIXTURE_REV_ID, FIXTURE_TITLE


def make_snapshot(
    *,
    page_id: int = FIXTURE_PAGE_ID,
    views: int = 12345,
    rev_id: int = FIXTURE_REV_ID,
    **overrides: Any,
) -> dict[str, Any]:
    """Build a JSON-ready trending snapshot with the recorded article as its one topic.

    Args:
        page_id: page id of the single topic.
        views: view count of the single topic.
        rev_id: revision id of the single topic.
        **overrides: top-level snapshot fields to replace (for example `topics=[]`).

    Returns:
        dict: the snapshot, ready for `json.dumps`.
    """
    snapshot: dict[str, Any] = {
        "schema_version": "1",
        "date": "2026-09-27",
        "source": "wikifeeds_mostread",
        "source_url": None,
        "generated_at": datetime.now(UTC).isoformat(),
        "next_refresh": None,
        "topics": [
            {
                "rank": 1,
                "page_id": page_id,
                "title": FIXTURE_TITLE,
                "description": None,
                "views": views,
                "rev_id": rev_id,
                "lead_excerpt": None,
                "dossier_state": "none",
                "edits_last_hour": None,
            }
        ],
        "edges": [],
    }
    snapshot.update(overrides)
    return snapshot
