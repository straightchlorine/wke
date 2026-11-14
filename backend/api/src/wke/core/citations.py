"""Section-level citations: one per heading of the pinned revision.

The anchor of a citation is the id attribute of the heading element in the
Parsoid HTML of that revision, never a slug built from the label, so
`<permalink>#<anchor>` opens the exact place a passage was taken from.
"""

from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import quote

from pydantic import HttpUrl, TypeAdapter

from wke.core.models import Chunk, Citation, Dossier, RevisionPin, Section

# Characters Wikipedia leaves readable in a fragment; everything else is
# percent-encoded so the URL is the same regardless of the client.
FRAGMENT_SAFE = "_-.:,()'!~*$&+;=@/?"

_HTTP_URL = TypeAdapter(HttpUrl)


def citation_url(pin: RevisionPin, anchor: str | None) -> str:
    """Build the permalink of a revision, with the section fragment if any.

    Args:
        pin: the revision pin the citation points into.
        anchor: heading id from the revision's Parsoid HTML, or None for
            the whole revision.

    Returns:
        str: `<permalink>` or `<permalink>#<anchor>`.
    """
    base = str(pin.permalink)
    return f"{base}#{quote(anchor, safe=FRAGMENT_SAFE)}" if anchor else base


def home_section_id(chunk_id: str, listed_in: str) -> str:
    """Name the section whose heading a chunk is cited to.

    The key-facts chunk is listed in the lead but cites the section that
    holds the infobox, which its id names ("{rev}:{section}:facts").

    Args:
        chunk_id: the chunk id.
        listed_in: id of the section whose chunk list holds the chunk.

    Returns:
        str: the section id the chunk cites.
    """
    parts = chunk_id.split(":")
    return parts[1] if len(parts) == 3 and parts[2] == "facts" else listed_in


def assign_section_citations(
    sections: Iterable[tuple[str, str]],
    chunks: list[Chunk],
    chunk_ids_by_section: dict[str, list[str]],
    seed_citation: Citation,
    first_index: int,
) -> tuple[list[Citation], dict[str, str]]:
    """Give every section of the seed article a citation to its own heading.

    The lead has no heading and cites the revision itself (the seed
    citation). Every other section gets one citation carrying its heading's
    real id; two sections never share an id in Parsoid HTML, but a repeated
    anchor would reuse the first citation.

    Args:
        sections: (section id, heading anchor) pairs in document order.
        chunks: the article's chunks; each section's chunks are retagged
            in place with their section's citation id.
        chunk_ids_by_section: section id -> ids of the chunks it owns.
        seed_citation: the revision-level citation (c1).
        first_index: number of the first new citation, after the related
            ones.

    Returns:
        tuple[list[Citation], dict[str, str]]: the new citations in order, and
        section id -> citation id.
    """
    pin = seed_citation.pin
    by_anchor: dict[str, str] = {}
    created: list[Citation] = []
    citation_of: dict[str, str] = {}
    next_index = first_index
    for section_id, anchor in sections:
        if not anchor:
            citation_of[section_id] = seed_citation.id
            continue
        if anchor not in by_anchor:
            citation = Citation(
                id=f"c{next_index}",
                pin=pin,
                role="seed",
                anchor=anchor,
                url=_HTTP_URL.validate_python(citation_url(pin, anchor)),
            )
            next_index += 1
            created.append(citation)
            by_anchor[anchor] = citation.id
        citation_of[section_id] = by_anchor[anchor]
    chunk_by_id = {chunk.id: chunk for chunk in chunks}
    for section_id, ids in chunk_ids_by_section.items():
        for chunk_id in ids:
            home = home_section_id(chunk_id, section_id)
            chunk_by_id[chunk_id].citation_id = citation_of.get(home, seed_citation.id)
    return created, citation_of


def seed_pin(dossier: Dossier) -> RevisionPin:
    """Find the seed article's revision pin.

    Args:
        dossier: the dossier to inspect.

    Returns:
        RevisionPin: the pin of the citation with role "seed", or the first
        citation's pin if none is marked seed.

    Raises:
        ValueError: if the dossier has no citations at all.
    """
    for citation in dossier.citations:
        if citation.role == "seed":
            return citation.pin
    if dossier.citations:
        return dossier.citations[0].pin
    raise ValueError("dossier has no citations to pin against")


def section_citation_id(
    section: Section, chunk_by_id: dict[str, Chunk], default: str = "c1"
) -> str:
    """Pick the citation a section's items carry.

    Args:
        section: the section.
        chunk_by_id: chunks by id.
        default: id to use when the section and its chunks name none.

    Returns:
        str: the section's own citation id, else its first chunk's, else
        the default.
    """
    if section.citation_id:
        return section.citation_id
    for chunk_id in section.chunk_ids:
        if chunk_id in chunk_by_id:
            return chunk_by_id[chunk_id].citation_id
    return default
