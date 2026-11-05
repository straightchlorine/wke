"""Read a bulleted or numbered list as verbatim "- item" lines."""

from __future__ import annotations

from selectolax.lexbor import LexborNode

from wke.core.formats.list import LIST_INDENT
from wke.core.parse.cells import classes
from wke.core.text.clean import clean_text

LIST_TAGS = frozenset(("ul", "ol", "dl"))

ITEM_TAGS = frozenset(("li", "dt", "dd"))

_EXCLUDED_CLASSES = frozenset(("gallery", "references", "mw-references", "toc", "navbox-list"))


def is_content_list(node: LexborNode) -> bool:
    """Tell a content list from a gallery, reference list or navigation list.

    Args:
        node: a `<ul>`, `<ol>` or `<dl>` element.

    Returns:
        bool: False for a list that is, or sits inside, an excluded block.
    """
    current: LexborNode | None = node
    while current is not None:
        if classes(current) & _EXCLUDED_CLASSES or current.tag == "nav":
            return False
        current = current.parent
    return True


def _item_text(item: LexborNode) -> str:
    """Read one list item as a single line.

    Args:
        item: a `<li>`, `<dt>` or `<dd>` element; line breaks become spaces.

    Returns:
        str: the cleaned item text.
    """
    for br in item.css("br"):
        br.replace_with(" ")
    return clean_text(item.text(separator="", strip=False))


def _lines(list_node: LexborNode, depth: int) -> list[str]:
    """Read the items of one list node and of the lists nested in them.

    Args:
        list_node: a `<ul>`, `<ol>` or `<dl>` element; modified in place
            (nested lists are removed once they are read).
        depth: nesting level of list_node, 0 for the outermost.

    Returns:
        list[str]: one "- item" line per non-empty item, indented by depth.
    """
    lines: list[str] = []
    for item in [c for c in list_node.iter() if c.tag in ITEM_TAGS]:
        nested = [c for c in item.iter() if c.tag in LIST_TAGS]
        nested_lines = [line for sub in nested for line in _lines(sub, depth + 1)]
        for sub in nested:
            sub.decompose()
        text = _item_text(item)
        if text:
            lines.append(f"{LIST_INDENT * depth}- {text}")
        lines.extend(nested_lines)
    return lines


def read_list(node: LexborNode) -> list[str]:
    """Read the items of an outermost list.

    Args:
        node: a `<ul>`, `<ol>` or `<dl>` element; modified in place.

    Returns:
        list[str]: the "- item" lines in order, nested items as indented
        lines; empty when the list holds no text.
    """
    return _lines(node, 0)
