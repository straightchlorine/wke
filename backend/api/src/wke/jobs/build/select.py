"""Choice of the sections that get a model summary."""

from __future__ import annotations

from wke.core import pack
from wke.core.models import Chunk, Section
from wke.jobs.build.constants import SUMMARY_SECTIONS_MIN, SUMMARY_TOKENS_PER_SECTION


def select_summary_sections(
    sections: list[Section], chunks: list[Chunk], summary_sections: int
) -> list[str]:
    """Choose which sections get a model summary.

    Prose sections other than the lead are ranked by the packer's own
    importance score and the top k are summarised, with k = round(article
    prose tokens / 2000) clamped to 3 at the least and `summary_sections`
    (8 by default) at the most.

    Args:
        sections: all sections in document order.
        chunks: the dossier's chunks, with relevance set.
        summary_sections: the SUMMARY_SECTIONS setting, the highest k.

    Returns:
        list[str]: ids of the sections to summarise, most important first.
    """
    prose_ids = {c.id for c in chunks if c.kind == "prose"}
    prose_tokens = sum(c.est_tokens for c in chunks if c.kind == "prose")
    k = min(
        max(round(prose_tokens / SUMMARY_TOKENS_PER_SECTION), SUMMARY_SECTIONS_MIN),
        summary_sections,
    )
    ranked = [
        s
        for s in pack.ranked_sections(sections, chunks)
        if s.summary_state != "no_prose" and any(cid in prose_ids for cid in s.chunk_ids)
    ]
    return [s.id for s in ranked[:k]]
