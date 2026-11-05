"""Entry point: Parsoid revision HTML to sections and chunks."""

from __future__ import annotations

from selectolax.lexbor import LexborHTMLParser

from wke.core.parse.furniture import drop_furniture
from wke.core.parse.models import ParsedArticle
from wke.core.parse.sections import walk_sections
from wke.core.parse.state import ParseState


def parse_html(html: str, rev_id: int, citation_id: str) -> ParsedArticle:
    """Parse Parsoid revision HTML into sections and chunks.

    Args:
        html: Parsoid HTML for one revision, as returned by
            `GET /w/rest.php/v1/revision/{rev_id}/html`.
        rev_id: revision id the HTML was fetched for; used to build chunk
            ids.
        citation_id: citation id (e.g. "c1") every chunk from this
            revision is tagged with.

    Returns:
        ParsedArticle: kept sections in document order, their chunks, and
        whether the MAX_CHUNKS cap truncated the article.
    """
    tree = LexborHTMLParser(html)
    tables = drop_furniture(tree)
    state = ParseState(rev_id, citation_id)

    state.tables = tables
    body = tree.body

    if body is not None:
        walk_sections(body, [], state)
    return ParsedArticle(sections=state.sections, chunks=state.chunks, truncated=state.truncated)
