"""Trending candidate filters: rejects non-articles, aggregations, and denylisted titles."""

from __future__ import annotations

from typing import Any

NAMESPACE_PREFIXES = (
    "Special:",
    "Wikipedia:",
    "File:",
    "Portal:",
    "Help:",
    "Template:",
    "Category:",
    "Talk:",
    "User:",
    "Draft:",
    "Module:",
)

# Bare year pages are linked from nearly every article and routinely
# appear in Wikifeeds/Pageviews top lists without being a real topic.
DENYLIST = frozenset({"2024", "2025", "2026", "2027"})


def is_trending_candidate(raw_title: str) -> bool:
    """Decide whether a raw title survives the trending filters.

    Args:
        raw_title: title as returned by Wikifeeds/Pageviews, underscore
            or space separated.

    Returns:
        bool: False for Main_Page, "-", any namespaced title, List_of_*,
        Deaths_in_*, or a denylisted title; True otherwise.
    """
    title = raw_title.replace("_", " ").strip()
    if not title or title == "-":
        return False
    if title == "Main Page":
        return False
    if title.startswith(NAMESPACE_PREFIXES):
        return False
    if title.startswith("List of "):
        return False
    if title.startswith("Deaths in "):
        return False
    if title in DENYLIST:
        return False
    return True


def select_candidates(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Filter and cap a rank-ordered list of trending source rows.

    Args:
        items: rank-ordered rows, each carrying a `raw_title`.
        limit: max rows to keep.

    Returns:
        list[dict]: the filtered rows, in their original order, capped
        at `limit`. Duplicate titles (by normalized form) are kept once.
    """
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        raw_title = item["raw_title"]
        if not is_trending_candidate(raw_title):
            continue
        normalized = raw_title.replace("_", " ").strip()
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(item)
        if len(result) >= limit:
            break
    return result
