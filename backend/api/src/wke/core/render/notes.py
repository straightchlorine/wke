"""The notes that say why a summary is missing or what a section left out."""

from __future__ import annotations

from collections.abc import Iterable

from wke.core.models import Section
from wke.core.pack.owners import chunk_kind


def withheld_reason(section: Section) -> str:
    """The stored reason a summary was withheld, verbatim.

    Args:
        section: A section in the "withheld" state.

    Returns:
        str: The stored withheld_reason without a trailing full stop, or a plain
        statement that none was stored.
    """
    reason = (section.withheld_reason or "").strip().rstrip(".")
    return reason or "no reason was stored"


def summary_notice(section: Section, include_summaries: bool) -> str | None:
    """One notice line for a section whose attempted summary is missing.

    Args:
        section: The section to describe.
        include_summaries: whether the render asks for summaries at all.

    Returns:
        str | None: A notice sentence for the "pending", "unavailable" and "withheld"
        states, or None when summaries are off, the section carries a
        rendered summary, none was attempted ("skipped") or the token
        budget alone left it out.
    """
    if not include_summaries or section.summary is not None:
        return None
    notices = {
        "pending": "Summary pending: the model has not produced one yet.",
        "unavailable": "Summary unavailable: the model could not be reached.",
        "withheld": f"Summary withheld: {withheld_reason(section)}.",
    }
    return notices.get(section.summary_state)


def structured_counts(chunk_ids: Iterable[str]) -> str:
    """Name how many tables and lists a set of chunk ids holds.

    Args:
        chunk_ids: chunk ids of any kind; prose ids are not counted.

    Returns:
        str: "2 tables and 1 list", tables first; "" when there are neither.
    """
    kinds = [chunk_kind(cid) for cid in chunk_ids]
    parts = [plural(kinds.count(kind), kind) for kind in ("table", "list") if kind in kinds]
    return " and ".join(parts)


def tables_left_out_line(chunk_ids: list[str]) -> str:
    """Build the note for tables and lists of a section left out.

    Args:
        chunk_ids: ids of the omitted table and list chunks.

    Returns:
        str: the italic note line.
    """
    count = len(chunk_ids)
    verb = "is" if count == 1 else "are"
    return f"_{structured_counts(chunk_ids)} of this section {verb} left out at this budget._"


def plural(count: int, noun: str) -> str:
    """Pick the singular or plural form of a noun for a count.

    Args:
        count: the count.
        noun: the singular noun.

    Returns:
        str: the count with the noun, pluralised unless the count is 1.
    """
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"
