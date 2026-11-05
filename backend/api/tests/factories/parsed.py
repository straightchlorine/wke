"""Parsed articles built from small Parsoid-like HTML snippets."""

from __future__ import annotations

from wke.core.models import Chunk, ChunkKind
from wke.core.parse import ParsedArticle, parse_html

REV_ID = 7
CITATION_ID = "c1"
LEAD = "<p>The lead is a real sentence about the topic.</p>"


def parse_sections(*sections: str, anchor: str = "S1") -> ParsedArticle:
    """Parse sections given as inner HTML; the first one is the lead.

    Args:
        *sections: the inner HTML of each section in order.
        anchor: the heading id of the first section after the lead; the
            others are S2, S3 and so on. Every heading reads "Part <n>".

    Returns:
        ParsedArticle: the parse of the assembled revision.
    """
    parts: list[str] = []
    for index, inner in enumerate(sections):
        heading_id = anchor if index == 1 else f"S{index}"
        heading = "" if index == 0 else f"<h2 id='{heading_id}'>Part {index}</h2>"
        parts.append(f"<section data-mw-section-id='{index}'>{heading}{inner}</section>")
    return parse_html(f"<html><body>{''.join(parts)}</body></html>", REV_ID, CITATION_ID)


def texts(article: ParsedArticle, kind: ChunkKind | None = None) -> list[str]:
    """List the chunk texts of an article.

    Args:
        article: a parsed article.
        kind: only chunks of this kind; every chunk when None.

    Returns:
        list[str]: the texts in chunk order.
    """
    return [c.text for c in article.chunks if kind is None or c.kind == kind]


def link_spans(chunk: Chunk) -> list[tuple[str, str]]:
    """Read the link spans of a chunk back as the text they cover.

    Args:
        chunk: a prose chunk.

    Returns:
        list[tuple[str, str]]: (covered text, link title) per span, in order.
    """
    return [(chunk.text[s.start : s.end], s.title) for s in chunk.links]


def facts_lines(infobox_rows: str, classes: str = "infobox") -> list[str]:
    """Parse an infobox made of the given rows and return its facts lines.

    Args:
        infobox_rows: the `<tr>` elements of the infobox.
        classes: the class attribute of the table.

    Returns:
        list[str]: the "Label: value" lines; empty when no facts chunk came out.
    """
    table = f"<table class='{classes}'><tbody>{infobox_rows}</tbody></table>"
    found = texts(parse_sections(table + LEAD), "facts")
    return found[0].splitlines() if found else []


def table_text(table_html: str) -> list[str]:
    """Parse a section holding one table and return the lines of its table chunk.

    Args:
        table_html: one `<table>` element.

    Returns:
        list[str]: the chunk's lines; empty when no table chunk came out.
    """
    found = texts(parse_sections(LEAD, table_html), "table")
    return found[0].splitlines() if found else []
