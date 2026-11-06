"""Section importance: how much each section matters to the article."""

from __future__ import annotations

import re
from collections.abc import Callable

from wke.core.models import Chunk, Section

# A table or list weighs this much at most when sections are ranked by size.
STRUCTURED_IMPORTANCE_TOKENS = 300

# What a section's importance is made of, in order:
# - the mean relevance of its passages to the lead,
# - its size against the largest section,
# - its position in the article.
# The three sum to 1.
# TODO: calibrate - chosen not measured
IMPORTANCE_WEIGHTS = (0.5, 0.3, 0.2)

# Leftovers are scored by as:
#   own relevance + this weight * their section's importance
# Both terms are 0..1.
# At 1.0 a section weighs as much as a perfect relevance:
#   relevance 0.30 in a 0.90 section = 1.20
#   relevance 0.95 in a 0.10 section = 1.05
# The first wins. A strong section keeps its body, instead of the pack taking
# one lead-like sentence from every weak section.
# --
# TODO: calibrate - chosen not measured; verify whether useful at all
REST_IMPORTANCE_WEIGHT = 1.0

# Added to a section whose heading names how a story ended.
OUTCOME_BONUS = 0.25
OUTCOME_HEADING = re.compile(
    r"arrest|trial|death|legacy|aftermath|result|reception|outcome", re.IGNORECASE
)


def _is_lead_section(section: Section) -> bool:
    """Tell the lead from every other section.

    Args:
        section: any section of a dossier.

    Returns:
        bool: True for the section without a heading path.
    """
    return not section.heading_path


def _importance_weight(chunk: Chunk) -> int:
    """Weight a chunk by its size, counting a long table or list only up to a cap."""
    size = max(chunk.est_tokens, 1)
    return size if chunk.kind == "prose" else min(size, STRUCTURED_IMPORTANCE_TOKENS)


def linear_position(index: int, count: int) -> float:
    """Score a section's place in the article, earlier is higher.

    Args:
        index: zero-based position of the section.
        count: number of sections.

    Returns:
        float: 1 for the first section down to 0 for the last.
    """
    return 1.0 - index / max(count - 1, 1)


def u_position(index: int, count: int) -> float:
    """Score a section's place in the article, both ends high.

    Articles close on outcomes (arrest, death, legacy, reception), so the
    last sections count as much as the first.

    Args:
        index: zero-based position of the section.
        count: number of sections.

    Returns:
        float: 1 at the first section, falling to 0.5 in the middle and
        rising to 1 at the last.
    """
    far = index / max(count - 1, 1)
    return max(1.0 - far, far)


def section_importance(
    sections: list[Section],
    chunks: list[Chunk],
    mix: tuple[float, float, float] | None = None,
    position: Callable[[int, int], float] | None = None,
    bonus: float | None = None,
) -> dict[str, float]:
    """Score how much each section matters to the article.

    The score is 0.5 * similarity to the lead (token-weighted mean of the
    section's chunk relevance, the cosine of each chunk to the lead) + 0.3 *
    size (section tokens over the largest section) + 0.2 * position (1 at the
    first and last section, 0.5 in the middle), plus 0.25 when the heading
    names an outcome (arrest, trial, death, legacy, aftermath, result,
    reception, outcome), capped at 1.

    Args:
        sections: all sections in document order.
        chunks: the dossier's chunks.
        mix: (similarity, size, position) weights; IMPORTANCE_WEIGHTS
            when None.
        position: function (index, section count) -> prior in [0, 1];
            u_position when None.
        bonus: added for an outcome heading; OUTCOME_BONUS when None.

    Returns:
        dict[str, float]: section id -> importance in [0, 1]; sections
        without chunks score 0.
    """
    chunk_by_id = {chunk.id: chunk for chunk in chunks}
    tokens: dict[str, int] = {}
    weighted: dict[str, float] = {}
    for section in sections:
        members = [chunk_by_id[cid] for cid in section.chunk_ids if cid in chunk_by_id]
        weights = [_importance_weight(c) for c in members]
        tokens[section.id] = sum(weights)
        weighted[section.id] = sum(w * c.relevance for w, c in zip(weights, members, strict=True))

    largest = max(tokens.values(), default=0)
    w_sim, w_size, w_pos = mix or IMPORTANCE_WEIGHTS
    position_of = position or u_position
    outcome_bonus = OUTCOME_BONUS if bonus is None else bonus

    scores: dict[str, float] = {}
    for index, section in enumerate(sections):
        if not tokens[section.id]:
            scores[section.id] = 0.0
            continue

        similarity = weighted[section.id] / tokens[section.id]
        size = tokens[section.id] / largest
        score = w_sim * similarity + w_size * size + w_pos * position_of(index, len(sections))
        if OUTCOME_HEADING.search(section.label):
            score += outcome_bonus
        scores[section.id] = min(score, 1.0)

    return scores


def ranked_sections(sections: list[Section], chunks: list[Chunk]) -> list[Section]:
    """Order the non-lead sections that hold chunks by importance.

    Args:
        sections: all sections in document order.
        chunks: the dossier's chunks.

    Returns:
        list[Section]: most important first, ties in document order.
    """
    scores = section_importance(sections, chunks)
    candidates = [s for s in sections if not _is_lead_section(s) and s.chunk_ids]
    return sorted(candidates, key=lambda s: -scores[s.id])
