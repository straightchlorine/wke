"""Placement of section summaries."""

from __future__ import annotations

from wke.core.models import Section
from wke.core.pack.costs import summary_cost
from wke.core.pack.state import Packer


def section_summary_cost(packer: Packer, section: Section) -> int | None:
    """Cost of including a section's summary, or None when it cannot be included.

    Args:
        packer: the pass to place into.
        section: the section whose summary is considered.

    Returns:
        int | None: the cost; None when summaries are off, the section has
        no finished summary, or its summary is already included.
    """
    if (
        not packer.include_summaries
        or section.summary_state != "done"
        or section.summary is None
        or section.id in packer.state.summaries
    ):
        return None
    return summary_cost(section.summary.text)


def fits_summary(packer: Packer, section: Section, cost: int) -> bool:
    """Tell whether a summary of the given cost, with its headings, fits the room left."""
    heading = packer.heading_cost(section.id)
    return cost + heading <= packer.remaining


def add_summary(packer: Packer, section: Section, cost: int) -> None:
    """Include a section's summary and charge its cost."""
    packer.charge(section.id, cost)
    packer.state.summaries.add(section.id)


def place_summaries(packer: Packer, cap: float | None) -> None:
    """Add summaries of sections that have passages in the pack, most important first.

    Args:
        packer: the pass to place into.
        cap: most tokens all summaries together may take, or None for no cap.
    """
    spent = 0
    for sid in packer.state.summaries:
        held = packer.section_by_id[sid].summary
        assert held is not None
        spent += summary_cost(held.text)
    for section in packer.ranked:
        cost = section_summary_cost(packer, section)
        if cost is None or not packer.has_chunk(section) or not fits_summary(packer, section, cost):
            continue
        if cap is not None and spent + cost > cap:
            continue
        add_summary(packer, section, cost)
        spent += cost
