"""Render a packed DossierView to Markdown."""

from __future__ import annotations

from wke.core.citations import section_citation_id, seed_pin
from wke.core.models import Chunk, DossierView, Section
from wke.core.pack.layout import SectionLayout, section_layout
from wke.core.pack.owners import chunk_kind
from wke.core.render.budget import FLAT_NOTICE, budget_line, holds_whole_article, opening_note
from wke.core.render.defaults import DEFAULT_INCLUDE_SUMMARIES
from wke.core.render.escape import escape_inline_markup, neutralise
from wke.core.render.header import PROVENANCE_NOTICE
from wke.core.render.labels import SUMMARY_LABEL, heading_prefix
from wke.core.render.leftout import left_out_header
from wke.core.render.notes import summary_notice, tables_left_out_line
from wke.core.render.parts import ALL_PARTS, Part
from wke.core.render.quote import quote
from wke.core.text.wikilinks import wiki_origin

SOURCES_HEADING = "## Sources"
NO_SOURCES_LINE = "- (none included at this budget)"

# start of the licence footer - always the last line of the document
LICENSE_PREFIX = "Quoted passages are CC BY-SA 4.0"


class SourceList:
    """Citation tags in order of first use, with the Sources line of each.

    Args:
        view: the packed view.
        markers: whether tag() returns the "[cN]" marker; without it the
            sources are still collected but the text carries no marker.
    """

    def __init__(self, view: DossierView, markers: bool = True):
        self._markers = markers
        self._citation_by_id = {citation.id: citation for citation in view.citations}
        self._seen: set[str] = set()
        self.lines: list[str] = []

    def tag(self, citation_id: str) -> str:
        """Return the "[cN]" tag of a citation and list it under Sources on first use.

        Args:
            citation_id: id of a citation of the view.

        Returns:
            str: "[cN]", or "[?]" when the view has no such citation; "" when
            the list was built without markers.
        """
        citation = self._citation_by_id.get(citation_id)
        if citation is None:
            return "[?]" if self._markers else ""
        if citation.id not in self._seen:
            self._seen.add(citation.id)
            target = citation.url or citation.pin.permalink
            self.lines.append(f"[{citation.id}] {target}")
        return f"[{citation.id}]" if self._markers else ""


def header_lines(view: DossierView, layout: SectionLayout, links: bool = False) -> list[str]:
    """Return the lines above the first section.

    Args:
        view: the packed view.
        layout: which sections the Markdown emits.
        links: whether the Markdown carries inline links.

    Returns:
        list[str]: title, pinning line, budget line, the flat-budget notice
        when the pack holds the whole article (otherwise the opening-passages
        note), the optional "Left out:" line
        and the provenance notice, each followed by a blank line.
    """
    pin = seed_pin(view)
    lines = [
        f"# {view.topic.title}",
        "",
        f"Pinned at revision {pin.rev_id} ({pin.rev_timestamp.isoformat()}): {pin.permalink}",
        "",
        budget_line(view, links),
        "",
    ]
    if holds_whole_article(view):
        lines.extend([FLAT_NOTICE, ""])
    elif note := opening_note(view):
        lines.extend([note, ""])
    header = left_out_header(layout)
    if header:
        lines.extend([header, ""])
    lines.extend([PROVENANCE_NOTICE, ""])
    return lines


def summary_lines(
    section: Section, chunk_by_id: dict[str, Chunk], seed_id: str, sources: SourceList
) -> list[str]:
    """Return the lines of a section's labelled machine summary.

    Args:
        section: a section that has a summary.
        chunk_by_id: the chunks the view carries.
        seed_id: citation id used when the section names none.
        sources: the citation tags of the document.

    Returns:
        list[str]: the label, the escaped text with its tag and the model line.
    """
    summary = section.summary
    assert summary is not None
    tag = sources.tag(section_citation_id(section, chunk_by_id, seed_id))
    return [
        f"**{SUMMARY_LABEL}**",
        "",
        neutralise(escape_inline_markup(summary.text)),
        *([tag] if tag else []),
        "",
        f"Model: {summary.model} ({summary.model_revision}); "
        f"generated {summary.generated_at.isoformat()}",
        "",
    ]


def section_lines(
    view: DossierView,
    section: Section,
    chunk_by_id: dict[str, Chunk],
    seed_id: str,
    sources: SourceList,
    include_summaries: bool,
    links: bool = False,
) -> list[str]:
    """Return the lines of one section: heading, passages, summary and notes.

    Args:
        view: the packed view.
        section: the section to render.
        chunk_by_id: the chunks the view carries.
        seed_id: citation id used when a summary's section names none.
        sources: the citation tags of the document.
        include_summaries: whether the render asks for summaries.
        links: whether to write the passages' wiki links inline.

    Returns:
        list[str]: the lines, each block followed by a blank line.
    """
    section_chunk_ids = [cid for cid in section.chunk_ids if cid in chunk_by_id]
    omitted = [cid for cid in section.chunk_ids if cid not in chunk_by_id]
    structured_out = [cid for cid in omitted if chunk_kind(cid) != "prose"]
    notice = summary_notice(section, include_summaries)
    origin = wiki_origin(seed_pin(view).url) if links else ""

    lines = [f"{heading_prefix(section)} {escape_inline_markup(section.label)}", ""]
    if not section_chunk_ids and section.summary is None:
        return lines

    for chunk_id in section_chunk_ids:
        chunk = chunk_by_id[chunk_id]
        lines.extend(quote(chunk, chunk.text, origin))
        if tag := sources.tag(chunk.citation_id):
            lines.append(tag)
        lines.append("")

    if section.summary is not None:
        lines.extend(summary_lines(section, chunk_by_id, seed_id, sources))
    elif notice is not None:
        lines.extend([f"_{notice}_", ""])
    if structured_out:
        lines.extend([tables_left_out_line(structured_out), ""])
    return lines


def sources_lines(sources: SourceList) -> list[str]:
    """Return the Sources block.

    Args:
        sources: the citation tags of the document.

    Returns:
        list[str]: the "## Sources" heading and one bullet per source, followed
        by a blank line.
    """
    lines = [SOURCES_HEADING, ""]
    if sources.lines:
        lines.extend(f"- {source}" for source in sources.lines)
    else:
        lines.append(NO_SOURCES_LINE)
    lines.append("")
    return lines


def license_lines(license_notice: str) -> list[str]:
    """Return the licence footer, the last line of every render.

    Args:
        license_notice: the licence text that ends the document.

    Returns:
        list[str]: the licence line.
    """
    return [license_notice]


def _seed_id(view: DossierView) -> str:
    """Return the citation id used when a summary's section names none."""
    return next((c.id for c in view.citations if c.role == "seed" and not c.anchor), "c1")


def _layout(view: DossierView) -> SectionLayout:
    """Return which sections of the view the Markdown emits."""
    summarised = [section.id for section in view.sections if section.summary is not None]
    return section_layout(view.sections, {chunk.id for chunk in view.chunks}, summarised)


def content_lines(
    view: DossierView,
    layout: SectionLayout,
    sources: SourceList,
    include_summaries: bool,
    links: bool = False,
) -> list[str]:
    """Return the lines of the dossier part: every kept section with its passages.

    Args:
        view: the packed view.
        layout: which sections the Markdown emits.
        sources: the citation tags of the document; filled while rendering.
        include_summaries: whether the render asks for summaries.
        links: whether to write the passages' wiki links inline.

    Returns:
        list[str]: the section lines in document order, each block followed
        by a blank line.
    """
    chunk_by_id = {chunk.id: chunk for chunk in view.chunks}
    seed_id = _seed_id(view)
    lines: list[str] = []
    for section in view.sections:
        if section.id in layout.kept_ids:
            lines.extend(
                section_lines(
                    view, section, chunk_by_id, seed_id, sources, include_summaries, links
                )
            )
    return lines


def content_text(
    view: DossierView, include_summaries: bool = DEFAULT_INCLUDE_SUMMARIES, links: bool = False
) -> tuple[str, SourceList]:
    """Render the dossier part, with its [cN] tags, and collect its sources.

    Args:
        view: A DossierView produced by build_view.
        include_summaries: Whether the view was packed with summaries.
        links: Whether to write the passages' wiki links inline.

    Returns:
        tuple[str, SourceList]: the section Markdown, which is the text the
        token budget counts, and the citations it used in order of first use.
    """
    sources = SourceList(view)
    lines = content_lines(view, _layout(view), sources, include_summaries, links)
    return "\n".join(lines).rstrip("\n") + "\n", sources


def render_markdown(
    view: DossierView,
    include_summaries: bool = DEFAULT_INCLUDE_SUMMARIES,
    links: bool = False,
    parts: frozenset[Part] = ALL_PARTS,
) -> str:
    """Render a packed DossierView to Markdown.

    Args:
        view: A DossierView produced by build_view.
        include_summaries: Whether the view was packed with summaries; a
            notice for a missing summary is written only when it was.
        links: Whether to write the passages' wiki links as inline Markdown
            links. Off by default: the text is the verbatim passage and the
            token budget counts nothing else; with links the Markdown can
            exceed the budget and the budget line says so.
        parts: Which parts to write. The dossier part (the sections) is always
            written; "metadata" adds the head above it, "sources" adds the
            [cN] markers and the Sources list below it. The CC BY-SA footer
            is always the last line.

    Returns:
        str: The Markdown document. With "metadata": title, pinning line, a
        budget line naming what was left out, one "Left out:" line naming the
        sections without content and those where nothing fit the budget. Always:
        one heading per remaining section (nested by depth; a section without
        anything included keeps its heading only as the parent of one that
        has), each quoted passage, key-facts list or table (followed by the
        citation tag of its section with "sources"), machine summaries under a
        visible label, a note of the tables and lists the budget left out, and
        the licence footer. With "sources": a Sources list of exact section
        URLs before the footer.
    """
    layout = _layout(view)
    sources = SourceList(view, markers="sources" in parts)
    lines = header_lines(view, layout, links) if "metadata" in parts else []
    lines.extend(content_lines(view, layout, sources, include_summaries, links))
    if "sources" in parts:
        lines.extend(sources_lines(sources))
    lines.extend(license_lines(view.license_notice))
    return "\n".join(lines).rstrip("\n") + "\n"
