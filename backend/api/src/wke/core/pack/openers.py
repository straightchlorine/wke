"""Placement of each section's representative paragraph."""

from __future__ import annotations

from wke.core.models import Section
from wke.core.pack.late import LATE_PASSAGE_SECTIONS, place_late_passage
from wke.core.pack.representative import ShownOpenings, pick_representative
from wke.core.pack.state import Packer
from wke.core.pack.summaries import add_summary, fits_summary, section_summary_cost


def place_section_opener(packer: Packer, section: Section, shown: ShownOpenings) -> None:
    """Include the paragraph that stands for a section, or its summary.

    A section without a paragraph that fits is represented by its summary
    when that fits, else it is left out of the pack.

    Args:
        packer: the pass to place into.
        section: the section to place.
        shown: the openings in the pack, updated with the paragraph placed.
    """
    prose = packer.prose_of(section)
    if not prose or any(c.id in packer.included for c in prose):
        return

    paragraph = pick_representative(packer, prose, shown)
    if paragraph is not None:
        packer.add_chunk(paragraph)
        shown.record(paragraph)
        return

    cost = section_summary_cost(packer, section)
    if cost is not None and fits_summary(packer, section, cost):
        add_summary(packer, section, cost)


def place_openers(packer: Packer) -> None:
    """Include one whole paragraph per section by importance.

    The lead and the top sections also get their late passage, the lead's
    before any section opens and a section's right after its first
    paragraph, before the next section gets one.

    Args:
        packer: the pass to place into.
    """
    shown = ShownOpenings.of(packer)
    for lead in (s for s in packer.dossier.sections if not s.heading_path):
        place_late_passage(packer, lead, shown)

    for rank, section in enumerate(packer.ranked):
        place_section_opener(packer, section, shown)
        if rank < LATE_PASSAGE_SECTIONS:
            place_late_passage(packer, section, shown)
