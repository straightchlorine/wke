"""Heading ids of a pinned revision, for the anchor checks."""

from __future__ import annotations

from selectolax.lexbor import LexborHTMLParser

from wke.core.text.clean import clean_text


def heading_map(html: str) -> dict[str, str]:
    """Map every heading id of a Parsoid revision to the heading's text.

    Args:
        html: Parsoid HTML of one revision.

    Returns:
        dict[str, str]: element id -> cleaned heading text, for h1 to h6.
    """
    tree = LexborHTMLParser(html)
    found: dict[str, str] = {}
    for node in tree.css("h1, h2, h3, h4, h5, h6"):
        heading_id = node.attributes.get("id")
        if heading_id:
            found[heading_id] = clean_text(node.text(separator="", strip=False))
    return found
