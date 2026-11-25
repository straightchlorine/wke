"""The stored rating document and the repack of a dossier under it."""

from __future__ import annotations

import math
from dataclasses import dataclass
from types import SimpleNamespace
from typing import TYPE_CHECKING

from pydantic import BaseModel, ValidationError

from wke.core import keys
from wke.core.models import Dossier
from wke.jobs.build.constants import RATING_MODEL, RATING_PROMPT_SHA256
from wke.jobs.build.sections import non_prose_relevance, set_importance
from wke.jobs.build.select import select_summary_sections

if TYPE_CHECKING:
    from wke.settings import Settings

# Summary states that are reset to "skipped" when the repack drops the section's summary.
_SUMMARISED = ("done", "withheld", "unavailable")


@dataclass(frozen=True)
class RatingConfig:
    """The rating settings shared by the build, the rater and dossier reads."""

    enabled: bool = False
    deadline_seconds: int = 1800
    call_timeout_seconds: int = 120
    summary_sections: int = 8
    min_coverage: float = 0.9
    max_attempts: int = 3
    retry_backoff_seconds: int = 60

    @classmethod
    def from_settings(cls, cfg: Settings) -> RatingConfig:
        """Build the config from the settings.

        Args:
            cfg: the settings.

        Returns:
            RatingConfig: enabled only when SELECTION_RATING is true.
        """
        return cls(
            enabled=cfg.selection_rating,
            deadline_seconds=cfg.rating_deadline_seconds,
            call_timeout_seconds=cfg.rating_call_timeout_seconds,
            summary_sections=cfg.summary_sections,
            min_coverage=cfg.rating_min_coverage,
            max_attempts=cfg.rating_max_attempts,
            retry_backoff_seconds=cfg.rating_retry_backoff_seconds,
        )


class RatingDocument(BaseModel):
    """The rater's stored scores for a revision; done is True once every passage is scored."""

    prompt_sha256: str
    model: str
    done: bool
    scores: dict[str, float | None]


def rating_key(page_id: int, rev_id: int, pipeline_version: str) -> str:
    """Build the Redis key of a revision's rating document, for the current prompt and model.

    Args:
        page_id: Wikipedia page id.
        rev_id: pinned revision id.
        pipeline_version: PIPELINE_VERSION setting.

    Returns:
        str: the Redis key.
    """
    return keys.rating(page_id, rev_id, pipeline_version, RATING_PROMPT_SHA256[:12], RATING_MODEL)


def rating_lock_key(page_id: int, rev_id: int, pipeline_version: str) -> str:
    """Build the key of the lock that allows one queued or running rating job per revision.

    Args:
        page_id: Wikipedia page id.
        rev_id: pinned revision id.
        pipeline_version: PIPELINE_VERSION setting.

    Returns:
        str: the Redis key.
    """
    return keys.rating_lock(
        page_id, rev_id, pipeline_version, RATING_PROMPT_SHA256[:12], RATING_MODEL
    )


def parse_document(raw: str | None) -> RatingDocument | None:
    """Parse a stored rating document made under the current prompt and model.

    Args:
        raw: the stored value, or None.

    Returns:
        RatingDocument | None: None if absent, unreadable or from another prompt or model.
    """
    if raw is None:
        return None
    try:
        document = RatingDocument.model_validate_json(raw)
    except ValidationError:
        return None
    if document.prompt_sha256 != RATING_PROMPT_SHA256 or document.model != RATING_MODEL:
        return None
    return document


def ranks_of(values: dict[str, float]) -> dict[str, float]:
    """Rank the values from 0 upward; tied values get the mean of the ranks they span.

    Args:
        values: a value per id.

    Returns:
        dict[str, float]: the 0-based rank per id.
    """
    ids = sorted(values, key=lambda i: values[i])
    out: dict[str, float] = {}
    start = 0
    while start < len(ids):
        end = start
        while end + 1 < len(ids) and values[ids[end + 1]] == values[ids[start]]:
            end += 1
        out.update({i: (start + end) / 2 for i in ids[start : end + 1]})
        start = end + 1
    return out


def rank_map(values: dict[str, float], stored: dict[str, float]) -> dict[str, float]:
    """Replace the values by stored relevances, keeping the values' order.

    The value ranked r-th smallest becomes the r-th smallest stored relevance, interpolated
    when ranks are tied. Rating scores thus reorder passages without changing the relevance
    scale the packer was built for.

    Args:
        values: the new value per passage id.
        stored: the stored relevance of the same passage ids.

    Returns:
        dict[str, float]: the new relevance per passage id.
    """
    ordered = sorted(stored.values())
    ranks = ranks_of(values)

    def at(rank: float) -> float:
        low = math.floor(rank)
        high = min(low + 1, len(ordered) - 1)
        return ordered[low] + (rank - low) * (ordered[high] - ordered[low])

    return {i: at(ranks[i]) for i in values}


def apply_rating(
    dossier: Dossier,
    scores: dict[str, float | None],
    summary_sections: int,
    min_coverage: float = 0.0,
) -> Dossier | None:
    """Return a copy of the dossier with its prose passages re-ranked by the rating scores.

    A passage without a score takes the mean of the others. A section that is no longer
    among those chosen for summaries loses its summary (state "skipped").

    Args:
        dossier: the stored dossier; not changed.
        scores: a score 0 to 3, or None, per prose chunk id.
        summary_sections: the SUMMARY_SECTIONS setting.
        min_coverage: share of prose passages that must have a real score.

    Returns:
        Dossier | None: the copy; None if the ids differ from the prose chunk ids or coverage is
        below min_coverage.
    """
    repacked = dossier.model_copy(deep=True)
    prose = [c for c in repacked.chunks if c.kind == "prose"]
    if set(scores) != {c.id for c in prose}:
        return None
    known = [s for s in scores.values() if s is not None]
    if len(known) < min_coverage * len(prose) - 1e-9:
        return None
    fill = sum(known) / len(known) if known else 0.0
    values = {i: (fill if s is None else s) / 3 for i, s in scores.items()}
    relevance = rank_map(values, {c.id: c.relevance for c in prose})
    for chunk in prose:
        chunk.relevance = relevance[chunk.id]
    non_prose_relevance(
        repacked.chunks,
        SimpleNamespace(sections=repacked.sections),  # pyright: ignore[reportArgumentType]
    )
    set_importance(repacked.sections, repacked.chunks)
    chosen = select_summary_sections(repacked.sections, repacked.chunks, summary_sections)
    for section in repacked.sections:
        if section.id not in chosen and section.summary_state in _SUMMARISED:
            section.summary, section.summary_state, section.withheld_reason = None, "skipped", None
    return repacked
