"""The whole paragraph that stands for a section, and the openings already shown."""

from __future__ import annotations

from dataclasses import dataclass

from wke.core.models import Chunk
from wke.core.pack.state import Packer
from wke.core.text.openings import (
    content_tokens,
    has_named_subject,
    opening_key,
    overlap_with,
)

OPENER_SHARE = 0.4
CANDIDATE_PARAGRAPHS = 3

# most of a paragraph's content tokens that may already stand in the lead.
LEAD_OVERLAP_LIMIT = 0.7


@dataclass
class ShownOpenings:
    """What the lead says and how the paragraphs placed so far begin.

    Attributes:
        lead_tokens: content tokens of the lead passages in the pack.
        openings: opening keys of every prose passage in the pack.
    """

    lead_tokens: set[str]
    openings: set[tuple[str, ...]]

    @classmethod
    def of(cls, packer: Packer) -> ShownOpenings:
        """Read the lead and the openings from what the pack holds.

        Args:
            packer: the pass to place into.

        Returns:
            ShownOpenings: the state after the lead and the earlier budget steps.
        """
        lead_tokens: set[str] = set()
        openings: set[tuple[str, ...]] = set()
        for chunk_id in packer.state.included:
            chunk = packer.chunk_by_id[chunk_id]
            if chunk.kind != "prose":
                continue
            text = packer.state.texts.get(chunk_id, chunk.text)
            if not chunk.heading_path:
                lead_tokens.update(content_tokens(text))
            if key := opening_key(text):
                openings.add(key)
        return cls(lead_tokens, openings)

    def accepts(self, chunk: Chunk) -> bool:
        """Tell whether a paragraph adds an opening the pack does not hold yet.

        Args:
            chunk: a candidate paragraph.

        Returns:
            bool: False when most of its words are in the lead or its first
            content tokens equal those of a paragraph already shown.
        """
        if overlap_with(chunk.text, self.lead_tokens) > LEAD_OVERLAP_LIMIT:
            return False
        return opening_key(chunk.text) not in self.openings

    def record(self, chunk: Chunk) -> None:
        """Note the opening of a paragraph that was placed.

        Args:
            chunk: the placed paragraph.
        """
        if key := opening_key(chunk.text):
            self.openings.add(key)


def fits_share(packer: Packer, chunk: Chunk) -> bool:
    """Tell whether a whole paragraph fits its share of the room left."""
    return chunk.est_tokens <= OPENER_SHARE * packer.remaining and packer.fits_chunk(chunk)


def pick_representative(packer: Packer, prose: list[Chunk], shown: ShownOpenings) -> Chunk | None:
    """Pick the whole paragraph that stands for a section.

    The first paragraph when it fits its share, else the shortest of the
    first three that fits and has a named subject. When that paragraph
    repeats the lead or an opening already shown, the next acceptable one of
    the three takes its place; the first pick stays when none is acceptable.

    Args:
        packer: the pass to place into.
        prose: the section's prose paragraphs in document order.
        shown: the openings already in the pack.

    Returns:
        Chunk | None: the paragraph, or None when none of them fits.
    """
    candidates = prose[:CANDIDATE_PARAGRAPHS]
    if fits_share(packer, candidates[0]):
        first = candidates[0]
    else:
        fitting = [c for c in candidates[1:] if fits_share(packer, c) and has_named_subject(c.text)]
        first = min(fitting, key=lambda c: (c.est_tokens, c.order), default=None)
    if first is None or shown.accepts(first):
        return first
    later = (
        c
        for c in candidates
        if c.order > first.order and fits_share(packer, c) and has_named_subject(c.text)
    )
    return next((c for c in later if shown.accepts(c)), first)
