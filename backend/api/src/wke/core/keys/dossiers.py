"""Redis keys of stored dossiers and their summaries."""

from __future__ import annotations

from wke.core.keys.hashing import sha256_hex


def sum_key(input_text: str, model: str, model_revision: str, params: str) -> str:
    """Build the content-addressed summary cache key.

    Args:
        input_text: exact text sent to the summarizer.
        model: HF model name.
        model_revision: HF model revision (commit sha).
        params: stable string encoding of num_beams/min_length/max_length.

    Returns:
        str: `sum:{sha256(input|model@rev|params)}`.
    """
    payload = f"{input_text}|{model}@{model_revision}|{params}"
    return f"sum:{sha256_hex(payload)}"


def dossier(page_id: int, rev_id: int, pipeline_version: str) -> str:
    """Build the stored dossier key.

    Args:
        page_id: Wikipedia page id.
        rev_id: pinned revision id.
        pipeline_version: PIPELINE_VERSION setting.

    Returns:
        str: `dossier:{page_id}:{rev_id}:{pv}`.
    """
    return f"dossier:{page_id}:{rev_id}:{pipeline_version}"


def ptr(page_id: int) -> str:
    """Build the latest-build pointer key.

    Args:
        page_id: Wikipedia page id.

    Returns:
        str: `ptr:{page_id}`.
    """
    return f"ptr:{page_id}"


def rebuild_debounce(page_id: int) -> str:
    """Build the background-rebuild debounce key.

    Args:
        page_id: Wikipedia page id.

    Returns:
        str: `rebuild:{page_id}`.
    """
    return f"rebuild:{page_id}"


TRACKED = "tracked"
TRACKED_PAGE_IDS = "tracked_page_ids"
BUILT = "built"
