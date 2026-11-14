"""Citations of a build: the revision pins, the related pages and the sections."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from pydantic import HttpUrl, TypeAdapter

from wke.core.citations import assign_section_citations
from wke.core.models import Citation, GraphNode, RevisionPin
from wke.core.parse import ParsedArticle

_HTTP_URL = TypeAdapter(HttpUrl)


def revision_pin(
    page_id: int, title: str, rev_id: int, origin: str, rev_timestamp: datetime
) -> RevisionPin:
    """Pin an article to one revision with its URL and permalink.

    Args:
        page_id: Wikipedia page id.
        title: article title.
        rev_id: revision id.
        origin: the wiki origin, such as https://en.wikipedia.org.
        rev_timestamp: when the revision was edited.

    Returns:
        RevisionPin: the pin, retrieved now.
    """
    return RevisionPin(
        page_id=page_id,
        title=title,
        rev_id=rev_id,
        rev_timestamp=rev_timestamp,
        url=_HTTP_URL.validate_python(f"{origin}/wiki/{quote(title.replace(' ', '_'))}"),
        permalink=_HTTP_URL.validate_python(f"{origin}/w/index.php?oldid={rev_id}"),
        retrieved_at=datetime.now(UTC),
    )


def build_related_citations(
    related_pages: list[dict[str, Any]], origin: str, start_index: int
) -> tuple[list[Citation], list[GraphNode], list[dict[str, Any]]]:
    """Turn related page records into citations, graph nodes and lead texts.

    Args:
        related_pages: the related page records; incomplete ones are skipped.
        origin: the wiki origin.
        start_index: number of the first citation id (c<N>); skipped pages
            leave no gap in the numbering.

    Returns:
        tuple: the citations, the graph nodes and the leads sent to wke-ml.
    """
    citations: list[Citation] = []
    nodes: list[GraphNode] = []
    leads: list[dict[str, Any]] = []
    for page in related_pages:
        page_id = page.get("pageid")
        rev_id = page.get("lastrevid")
        title = page.get("title", "")

        revisions: list[dict[str, Any]] = page.get("revisions") or []
        raw_timestamp: str | None = revisions[0].get("timestamp") if revisions else None
        if page_id is None or rev_id is None or not raw_timestamp:
            continue

        rev_timestamp = datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00"))
        pin = revision_pin(page_id, title, rev_id, origin, rev_timestamp)

        citations.append(Citation(id=f"c{start_index + len(citations)}", pin=pin, role="related"))
        nodes.append(GraphNode(id=page_id, title=title, role="related"))
        leads.append({"page_id": page_id, "text": page.get("extract", "")})
    return citations, nodes, leads


def cite_sections(
    parsed: ParsedArticle, seed_citation: Citation, related_citations: list[Citation]
) -> tuple[list[Citation], dict[str, str]]:
    """Give every parsed section a citation to its own heading in the pinned revision.

    Args:
        parsed: the parsed article; its chunks are retagged in place.
        seed_citation: the revision-level citation (c1), used for the lead.
        related_citations: related-article citations, which fix the next id.

    Returns:
        tuple: the new section citations and section id -> citation id.
    """
    used = [int(c.id[1:]) for c in (seed_citation, *related_citations)]
    return assign_section_citations(
        [(s.id, s.anchor) for s in parsed.sections],
        parsed.chunks,
        {s.id: s.chunk_ids for s in parsed.sections},
        seed_citation,
        first_index=max(used) + 1,
    )
