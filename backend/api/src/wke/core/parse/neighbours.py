"""Look at the element after a paragraph."""

from __future__ import annotations

from selectolax.lexbor import LexborNode

from wke.core.parse.formulas import display_tex
from wke.core.text.clean import clean_text

LIST_LIKE_TAGS = frozenset(("ul", "ol", "dl", "table"))


def next_element(node: LexborNode) -> LexborNode | None:
    """Return the next sibling element, skipping text and comments.

    Args:
        node: any element.

    Returns:
        LexborNode | None: the sibling, or None at the end of the parent.
    """
    sibling = node.next
    while sibling is not None and sibling.tag in ("-text", "-comment"):
        sibling = sibling.next
    return sibling


def quote_follows(node: LexborNode) -> bool:
    """Tell whether a quotation follows the paragraph and completes it.

    Args:
        node: the `<p>` element.

    Returns:
        bool: True when the next element is a blockquote or a wrapper holding
        a paragraph or blockquote.
    """
    following = next_element(node)
    if following is None:
        return False
    if following.tag == "blockquote":
        return True
    return following.tag == "div" and following.css_first("p, blockquote") is not None


def formula_follows(node: LexborNode) -> bool:
    """Tell whether a display equation follows the paragraph and completes it.

    Args:
        node: the `<p>` element.

    Returns:
        bool: True when the next element is a display equation.
    """
    following = next_element(node)
    return following is not None and bool(display_tex(following))


def dropped_block_follows(node: LexborNode) -> bool:
    """Tell whether the block after a paragraph is a list or table whose content is dropped.

    Args:
        node: the `<p>` element.

    Returns:
        bool: True when the next element is a list or table, or a wrapper
        (column list, cladogram, reference list) that holds a list or has
        no text left and no paragraph or quote.
    """
    following = next_element(node)
    if following is None:
        return False
    if following.tag in LIST_LIKE_TAGS:
        return True
    if following.tag != "div" or display_tex(following):
        return False
    if following.css_first("p, blockquote") is not None:
        return False
    holds_list = any(following.css_first(tag) is not None for tag in LIST_LIKE_TAGS)
    return holds_list or not clean_text(following.text(separator="", strip=False))
