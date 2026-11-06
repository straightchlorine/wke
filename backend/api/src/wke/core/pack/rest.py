"""Placement of the passages left over, by relevance and section importance."""

from __future__ import annotations

from wke.core.models import Chunk
from wke.core.pack.importance import REST_IMPORTANCE_WEIGHT, section_importance
from wke.core.pack.state import Packer
from wke.core.pack.structured import add_structured


def locked_sections(packer: Packer) -> set[str]:
    """Return the sections represented by a summary alone.

    Args:
        packer: the pass to place into.

    Returns:
        set[str]: ids of sections whose summary is included and none of
        whose chunks is; their passages stay out so the summary stands in.
    """
    return {
        sid for sid in packer.state.summaries if not packer.has_chunk(packer.section_by_id[sid])
    }


def place_rest(packer: Packer) -> None:
    """Include the remaining chunks, highest priority first, while they fit.

    Args:
        packer: the pass to place into.
    """
    locked = locked_sections(packer)
    pending = [
        c
        for c in packer.dossier.chunks
        if c.id not in packer.included and packer.owner.get(c.id, "") not in locked
    ]
    score = section_importance(packer.dossier.sections, packer.dossier.chunks)

    def priority(chunk: Chunk) -> float:
        # The passage's own relevance to the lead + the standing of the section it belongs to,
        # so the leftovers follow their sections instead of being picked one by one across the
        # articles. Equal scores keep document order through the second sort key.
        return chunk.relevance + REST_IMPORTANCE_WEIGHT * score.get(
            packer.owner.get(chunk.id, ""), 0.0
        )

    for chunk in sorted(pending, key=lambda c: (-priority(c), c.order)):
        if chunk.kind in ("table", "list"):
            add_structured(packer, chunk)
        elif packer.fits_chunk(chunk):
            packer.add_chunk(chunk)
