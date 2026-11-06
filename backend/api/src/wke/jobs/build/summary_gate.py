"""Source check of a model summary and the section state that follows from it."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from wke.core.models import MachineSummary, Section
from wke.core.summaries.check import check_summary

logger = logging.getLogger(__name__)


def withhold(section: Section, reason: str) -> None:
    """Withhold a section's summary and record why.

    Args:
        section: the section; changed in place.
        reason: the source-check failure to show.
    """
    logger.info("summary withheld for section %s: %s", section.id, reason)
    section.summary = None
    section.summary_state = "withheld"
    section.withheld_reason = reason


def mark_unavailable(section: Section) -> None:
    """Record that the model produced no usable summary for the section.

    Args:
        section: the section; changed in place.
    """
    section.summary = None
    section.summary_state = "unavailable"


def attach_summary(
    section: Section,
    summary: MachineSummary,
    input_ids: list[str],
    input_text: str,
    heading: str,
    foreign_titles: Sequence[str],
    truncated: bool,
) -> None:
    """Run the source check on a model summary and attach it to its section or withhold it.

    Args:
        section: the section the summary summarises; changed in place.
        summary: the model's output, never edited.
        input_ids: ids of the chunks the model read, which replace the ids
            the summary carries.
        input_text: the joined text the model read.
        heading: the section heading, whose years the summary may use.
        foreign_titles: titles of other articles the summary may not name.
        truncated: whether wke-ml reported the output as cut off.
    """
    reason = check_summary(
        summary.text,
        input_text,
        heading=heading,
        truncated=truncated,
        foreign_titles=foreign_titles,
    )
    if reason is not None:
        withhold(section, reason)
        return
    section.summary = summary.model_copy(
        update={"input_chunk_ids": input_ids, "citation_id": section.citation_id}
    )
    section.summary_state = "done"
    section.withheld_reason = None
