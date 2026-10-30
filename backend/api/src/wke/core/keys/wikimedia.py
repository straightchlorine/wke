"""Redis keys of the Wikimedia caches, lock, pacing and budget."""

from __future__ import annotations

from wke.core.keys.hashing import sha1_hex


def wm_search(query: str, limit: int) -> str:
    """Build the search cache key.

    Args:
        query: raw search string.
        limit: requested result count.

    Returns:
        str: `wm:search:{sha1(q|limit)}`.
    """
    return f"wm:search:{sha1_hex(f'{query}|{limit}')}"


def wm_resolve(title_key: str) -> str:
    """Build the resolve cache key.

    Args:
        title_key: normalized title (NFC, underscores as spaces).

    Returns:
        str: `wm:resolve:{title_key}`.
    """
    return f"wm:resolve:{title_key}"


def wm_html(rev_id: int) -> str:
    """Build the Parsoid HTML cache key.

    Args:
        rev_id: revision id.

    Returns:
        str: `wm:html:{rev_id}`.
    """
    return f"wm:html:{rev_id}"


def wm_revts(rev_id: int) -> str:
    """Build the revision-timestamp cache key.

    Args:
        rev_id: revision id.

    Returns:
        str: `wm:revts:{rev_id}`.
    """
    return f"wm:revts:{rev_id}"


def wm_related(page_id: int) -> str:
    """Build the related-leads cache key.

    Args:
        page_id: seed page id.

    Returns:
        str: `wm:related:{page_id}`.
    """
    return f"wm:related:{page_id}"


def wm_budget(epoch_minute: int) -> str:
    """Build the shared Wikimedia call-budget counter key.

    Args:
        epoch_minute: `int(time.time() // 60)`.

    Returns:
        str: `wm:budget:{epoch_minute}`.
    """
    return f"wm:budget:{epoch_minute}"


WM_LOCK = "wm:lock"
WM_PACE = "wm:pace"
