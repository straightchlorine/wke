"""Placement of the passage that closes a section's story."""

from __future__ import annotations

import math

from wke.core.models import Chunk, Section
from wke.core.pack.representative import ShownOpenings
from wke.core.pack.state import Packer

LATE_PASSAGE_SECTIONS = 5
# Most of the room left that a late passage may take, so the openers of the
# sections after it still fit.
LATE_SHARE = 0.25


def late_passage(packer: Packer, section: Section) -> Chunk | None:
    """Pick the most lead-similar passage in the last third of a section's prose.

    Events and cases end with their outcome, so the passage that resolves a
    section tends to sit near its end. The first paragraph is never chosen.

    Args:
        packer: the pass to place into.
        section: the section to pick from.

    Returns:
        Chunk | None: the passage, or None when the section has none left.
    """
    prose = packer.prose_of(section)
    tail = prose[max(1, len(prose) - math.ceil(len(prose) / 3)) :]
    return max(
        (c for c in tail if c.id not in packer.included), key=lambda c: c.relevance, default=None
    )


def place_late_passage(packer: Packer, section: Section, shown: ShownOpenings) -> None:
    """Include a section's late passage when the section already has prose in the pack.

    Args:
        packer: the pass to place into.
        section: the section whose outcome is wanted.
        shown: the openings in the pack, updated with the passage placed.
    """
    if not any(c.id in packer.included for c in packer.prose_of(section)):
        return
    passage = late_passage(packer, section)
    if (
        passage is not None
        and passage.est_tokens <= LATE_SHARE * packer.remaining
        and packer.fits_chunk(passage)
    ):
        packer.add_chunk(passage)
        shown.record(passage)
