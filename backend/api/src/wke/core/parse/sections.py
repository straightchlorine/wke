"""Walk the sections of a revision and parse each one into chunks."""

from __future__ import annotations

from selectolax.lexbor import LexborNode

from wke.core.parse.chunks import emit_chunks
from wke.core.parse.models import ParsedSection
from wke.core.parse.paragraphs import collect_own_paragraphs
from wke.core.parse.state import ParseState
from wke.core.parse.structured import emit_structured
from wke.core.text.clean import clean_text
from wke.core.text.tokens import est_tokens

BOILERPLATE_ANCHORS = frozenset(
    (
        "See_also",
        "References",
        "Notes",
        "Further_reading",
        "External_links",
        "Bibliography",
        "Sources",
        "Citations",
    )
)

# Sections whose lists are citations of the article's own sources: their
# prose is kept, their lists are neither emitted nor counted.
REFERENCE_LIST_ANCHORS = frozenset(
    ("Works_cited", "Sources", "Cited_works", "Selected_bibliography")
)

HEADING_SELECTOR = "h1, h2, h3, h4, h5, h6"


def walk_sections(container: LexborNode, heading_path: list[str], state: ParseState) -> None:
    """Process each direct-child `<section data-mw-section-id>` of container.

    Args:
        container: the body or a section whose child sections are walked.
        heading_path: the headings of the sections above, outermost first.
        state: parse accumulator, extended with the sections and chunks.
    """
    for child in container.iter():
        if child.tag != "section":
            continue

        section_id = child.attributes.get("data-mw-section-id")
        if section_id is None:
            continue

        anchor, heading = section_heading(child)
        if anchor in BOILERPLATE_ANCHORS:
            continue

        own_heading_path = heading_path + ([heading] if heading else [])
        parsed_section = ParsedSection(
            id=section_id,
            anchor=anchor,
            heading=heading,
            heading_path=list(heading_path),
            order=state.section_order,
            chunk_ids=[],
        )
        state.section_order += 1
        state.sections.append(parsed_section)

        runs, own = collect_own_paragraphs(child, is_lead=not heading)
        if anchor in REFERENCE_LIST_ANCHORS:
            own.lists = []

        emit_chunks(runs, section_id, own_heading_path, state, parsed_section)
        prose_tokens = sum(est_tokens(p.text) for run in runs for p in run)
        emit_structured(
            own, heading, prose_tokens, section_id, own_heading_path, state, parsed_section
        )

        walk_sections(child, own_heading_path, state)


def section_heading(section: LexborNode) -> tuple[str, str]:
    """Return (anchor, heading text) for a section's own heading, if any.

    Document order puts a section's own heading before any nested
    section's heading, so the first heading match in the subtree belongs
    to this section.

    Args:
        section: a `<section>` element.

    Returns:
        tuple[str, str]: the heading's id and its cleaned text; ("", "") for
        the lead, which has no heading.
    """
    heading_node = section.css_first(HEADING_SELECTOR)
    if heading_node is None:
        return "", ""

    anchor = heading_node.attributes.get("id") or ""
    heading = clean_text(heading_node.text(separator="", strip=False))
    return anchor, heading
