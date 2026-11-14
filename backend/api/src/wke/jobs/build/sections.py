"""Section assembly: labels, states and importance for a parsed article."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from wke.core import pack
from wke.core.models import Chunk, ChunkKind, Section, SummaryState
from wke.core.parse import ParsedArticle, ParsedSection
from wke.jobs.build.select import select_summary_sections

LabelSource = Literal["heading", "article_title", "structural"]


def label_sections(
    sections: list[ParsedSection],
    article_title: str,
    heading_label_source: LabelSource = "heading",
) -> list[tuple[ParsedSection, str, LabelSource]]:
    """Assign a display label and label_source to each parsed section.

    The lead section (heading == "") is labelled with the article title.
    ParsedSection.heading_path holds ancestors only (not the section's own
    heading), so a top-level section's path is empty and a duplicate
    heading's nearest ancestor - heading_path[0], the second-level (H2)
    heading it sits under - is appended so the two sections remain
    distinguishable. If that still collides (no ancestor to append, e.g.
    two duplicate top-level headings, or two duplicates under the same
    ancestor), an ordinal ("(2)", "(3)", ...) is appended instead.

    Args:
        sections: parsed sections in document order.
        article_title: the resolved article title (unknown to the parser).
        heading_label_source: label_source for a section labelled from
            its own heading ("heading" for the ML path, "structural" for
            persist_structural's ML-down fallback).

    Returns:
        list[tuple]: (section, label, label_source) in the input order.
    """
    heading_counts: dict[str, int] = {}
    for section in sections:
        if section.heading:
            heading_counts[section.heading] = heading_counts.get(section.heading, 0) + 1

    labelled: list[tuple[ParsedSection, str, LabelSource]] = []
    label_occurrences: dict[str, int] = {}
    for section in sections:
        if not section.heading:
            labelled.append((section, article_title, "article_title"))
            continue
        label = section.heading
        if heading_counts[section.heading] > 1 and section.heading_path:
            label = f"{section.heading} ({section.heading_path[0]})"
        occurrence = label_occurrences.get(label, 0) + 1
        label_occurrences[label] = occurrence
        if occurrence > 1:
            label = f"{label} ({occurrence})"
        labelled.append((section, label, heading_label_source))
    return labelled


def own_heading_path(section: ParsedSection) -> list[str]:
    """Return the section's heading path including its own heading.

    Args:
        section: a parsed section, whose heading_path holds ancestors only.

    Returns:
        list[str]: the ancestors plus the section's own heading, the same
        shape every chunk of the section carries; empty for the lead.
    """
    return [*section.heading_path, section.heading] if section.heading else []


def section_state(section_chunk_ids: list[str], kinds: Mapping[str, ChunkKind]) -> SummaryState:
    """Initial summary_state of a section from what its chunks are.

    Args:
        section_chunk_ids: ids of the section's chunks.
        kinds: chunk id to chunk kind.

    Returns:
        SummaryState: "pending" for a section with prose, "skipped" for one
        holding only non-prose chunks, "no_prose" for one with no chunks.
    """
    if any(kinds.get(cid) == "prose" for cid in section_chunk_ids):
        return "pending"
    return "skipped" if section_chunk_ids else "no_prose"


def non_prose_relevance(chunks: list[Chunk], parsed: ParsedArticle) -> None:
    """Set relevance on key-facts, table and list chunks, which the model never scored.

    Key facts rank with the lead; a table or list takes the mean relevance of its
    section's prose, or 0.5 when the section has none.

    Args:
        chunks: all chunks, prose relevance already set; changed in place.
        parsed: the parsed article, for the section of each chunk.
    """
    chunk_by_id = {c.id: c for c in chunks}
    for section in parsed.sections:
        prose = [chunk_by_id[cid] for cid in section.chunk_ids if chunk_by_id[cid].kind == "prose"]
        weight = sum(max(c.est_tokens, 1) for c in prose)
        mean = sum(max(c.est_tokens, 1) * c.relevance for c in prose) / weight if weight else 0.5
        for cid in section.chunk_ids:
            chunk = chunk_by_id[cid]
            if chunk.kind == "facts":
                chunk.relevance = 1.0
            elif chunk.kind in ("table", "list"):
                chunk.relevance = mean


def set_importance(sections: list[Section], chunks: list[Chunk]) -> None:
    """Store the packer's importance score on each section.

    Args:
        sections: all sections in document order; changed in place.
        chunks: the dossier's chunks, with relevance set.
    """
    scores = pack.section_importance(sections, chunks)
    for section in sections:
        section.importance = min(max(scores[section.id], 0.0), 1.0)


def assemble_sections(
    parsed: ParsedArticle,
    chunks: list[Chunk],
    title: str,
    citation_of: dict[str, str],
    summary_sections: int,
) -> tuple[list[Section], list[str]]:
    """Build the dossier sections of an analyzed article and pick the summarized ones.

    Sets non-prose relevance and section importance on `chunks` in place.
    Needs no network, so build jobs and offline tools share it.

    Args:
        parsed: the parsed article.
        chunks: the article's chunks with relevance and cluster ids applied.
        title: the resolved article title, used to label the lead.
        citation_of: section id to its section citation id.
        summary_sections: the SUMMARY_SECTIONS setting.

    Returns:
        The sections in document order and the ids chosen for a summary.
    """
    non_prose_relevance(chunks, parsed)
    kinds: dict[str, ChunkKind] = {c.id: c.kind for c in chunks}
    sections = [
        Section(
            id=section.id,
            label=label,
            label_source=label_source,
            chunk_ids=section.chunk_ids,
            heading_path=own_heading_path(section),
            citation_id=citation_of.get(section.id),
            dropped_non_prose=section.dropped_non_prose,
            dropped_lists=section.dropped_lists,
            dropped_tables=section.dropped_tables,
            summary=None,
            summary_state=section_state(section.chunk_ids, kinds),
        )
        for section, label, label_source in label_sections(parsed.sections, title)
    ]
    set_importance(sections, chunks)
    return sections, select_summary_sections(sections, chunks, summary_sections)
