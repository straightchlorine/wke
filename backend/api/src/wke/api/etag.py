"""ETag computation and conditional-GET evaluation for dossier routes."""

from __future__ import annotations

import hashlib
from typing import Literal

from wke.core.render.defaults import DEFAULT_INCLUDE_SUMMARIES

LATEST_CACHE_CONTROL = "public, max-age=60"
LIST_CACHE_CONTROL = "public, max-age=10"
IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable"

BuildState = Literal["partial", "complete"]


def compute_etag(
    rev_id: int,
    pipeline_version: str,
    budget: int,
    fmt: Literal["json", "markdown"],
    build_state: BuildState = "complete",
    summaries_done: int = 0,
    summaries: bool = DEFAULT_INCLUDE_SUMMARIES,
    links: bool = False,
    parts_code: str = "pd",
) -> str:
    """Build the ETag for a packed dossier response.

    Includes build state and summaries_done so in-place updates from
    partial to complete dossier change the ETag; includes summaries flag
    so ?summaries=false and ?summaries=true never collide, and the links
    flag so a Markdown body with inline links never shares a tag with one
    without, and the parts code so a different selection of parts never
    shares a tag.

    Args:
        rev_id: Pinned revision id.
        pipeline_version: Build pipeline version string.
        budget: Requested token budget (2000, 8000, or 32000).
        fmt: Response format, "json" or "markdown".
        build_state: Dossier build state, "partial" or "complete".
        summaries_done: Count of completed summaries; changes ETag mid-poll.
        summaries: Request's summaries query flag.
        links: Request's links query flag (Markdown with inline links).
        parts_code: the code of the selected parts, such as "pd" or "pdms".

    Returns:
        str: the quoted ETag,
        "{rev_id}-{pv}-{budget}-{fmt}-{state}-{done}-{s0|s1}-{l0|l1}-{parts_code}".
    """
    summaries_flag = "s1" if summaries else "s0"
    links_flag = "l1" if links else "l0"
    return (
        f'"{rev_id}-{pipeline_version}-{budget}-{fmt}-'
        f'{build_state}-{summaries_done}-{summaries_flag}-{links_flag}-{parts_code}"'
    )


def is_not_modified(etag: str, if_none_match: str | None) -> bool:
    """Evaluate an If-None-Match header against a computed ETag.

    Args:
        etag: The freshly computed ETag for this response.
        if_none_match: The raw If-None-Match request header value, if any.

    Returns:
        bool: True if the response should be a 304 Not Modified.
    """
    if not if_none_match:
        return False
    candidates = {value.strip() for value in if_none_match.split(",")}
    return "*" in candidates or etag in candidates


def cache_control_for(route: Literal["latest", "revision"]) -> str:
    """Pick the Cache-Control value for a dossier route.

    Args:
        route: "latest" for GET /dossiers/{page_id}, "revision" for the
            immutable GET /dossiers/{page_id}/rev/{rev_id} route.

    Returns:
        str: the Cache-Control header value for that route.
    """
    return LATEST_CACHE_CONTROL if route == "latest" else IMMUTABLE_CACHE_CONTROL


def body_etag(body: str, encoding: str) -> str:
    """Build a strong ETag from the hash of a response body.

    Args:
        body: the response text.
        encoding: the codec the body is served in.

    Returns:
        str: the quoted entity tag.
    """
    return '"' + hashlib.sha256(body.encode(encoding)).hexdigest()[:32] + '"'
