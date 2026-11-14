"""Checks on the passages, tables, lists and facts of a view."""

from __future__ import annotations

import re

from wke.core.citations import home_section_id
from wke.core.formats.notes import LIST_NOTE, TABLE_NOTE
from wke.core.models import Chunk, DossierView
from wke.core.parse.passage import Passage
from wke.core.text.navigation import points_elsewhere
from wke.core.validate.report import ValidationReport

_LIST_LINE = re.compile(r"^ *- \S")


def _list_ends_whole(text: str) -> bool:
    """Tell whether every line of a list chunk is an item line or the count note.

    Args:
        text: a list chunk's text.

    Returns:
        bool: True when no line is cut text.
    """
    lines = text.splitlines()
    return bool(lines) and all(_LIST_LINE.match(ln) or LIST_NOTE.match(ln) for ln in lines)


def _check_structured(chunk: Chunk, report: ValidationReport) -> None:
    """Check that a table, list or facts chunk ends at a row or item boundary.

    Args:
        chunk: a chunk that is not prose.
        report: receives the failures.
    """
    report.counts["structured_chunks"] += 1
    last = chunk.text.splitlines()[-1] if chunk.text else ""
    row_ends = last.startswith("|") and last.endswith("|")

    if chunk.kind == "table" and not (row_ends or TABLE_NOTE.match(last)):
        report.fail("cut_table_row", chunk.id)
    if chunk.kind == "list" and not _list_ends_whole(chunk.text):
        report.fail("cut_list_item", chunk.id)
    if chunk.kind == "facts" and any(": " not in ln for ln in chunk.text.splitlines()):
        report.fail("cut_fact_row", chunk.id)


def _check_prose(chunk: Chunk, report: ValidationReport) -> None:
    """Check that a passage ends at a sentence end and points nowhere.

    Every edge uses the parser's own rules (Passage.ends_sentence,
    Passage.ends_intro and Passage.starts_mid_sentence), so the validator and
    the parser cannot disagree.

    Args:
        chunk: a prose chunk.
        report: receives the failures.
    """
    report.counts["passages"] += 1
    text = chunk.text
    passage = Passage(text, formulas=tuple(chunk.formulas))
    lead_intro = not chunk.heading_path and passage.ends_intro()

    if (not passage.ends_sentence() and not lead_intro) or passage.starts_mid_sentence():
        report.fail("fragment_passages", f"{chunk.id}: {text[:60]!r}")
    if points_elsewhere(text):
        report.fail("navigation_passages", f"{chunk.id}: {text[:60]!r}")


def check_chunks(view: DossierView, report: ValidationReport) -> None:
    """Check every chunk of a view, the section that lists it and the citation it carries.

    Args:
        view: the view as served at one budget.
        report: receives the counts and failures.
    """
    section_of = {cid: s for s in view.sections for cid in s.chunk_ids}
    section_by_id = {s.id: s for s in view.sections}
    for chunk in view.chunks:
        owner = section_of.get(chunk.id)
        if owner is None:
            report.fail("orphan_chunk", f"{chunk.id} is in no section")
        else:
            owner = section_by_id.get(home_section_id(chunk.id, owner.id), owner)
        expected = owner.citation_id if owner is not None else None
        if expected and chunk.citation_id != expected:
            report.fail("wrong_chunk_citation", f"{chunk.id} cites {chunk.citation_id}")
        if chunk.kind == "prose":
            _check_prose(chunk, report)
        else:
            _check_structured(chunk, report)
