"""Read the cells and rows of a table element as plain text."""

from __future__ import annotations

import re

from selectolax.lexbor import LexborNode

from wke.core.text.clean import clean_text

MAX_COLSPAN = 20

MAX_ROWSPAN = 200

_SPACE_BEFORE_COMMA = re.compile(r"\s+,")

_SEPARATOR_RUN = re.compile(r"(?:,\s*){2,}")

_EDGE_SEPARATOR = re.compile(r"^(?:,\s*)+|(?:\s*,)+$")

_HIDDEN = (
    "[style*='display:none'], [style*='display: none'], .sortkey, .mw-collapsible-toggle, .navbar"
)

# The title of a collapsible list ("See list"): a toggle label, not a value.
_COLLAPSIBLE_TITLE = ".collapsible-list > :not(.mw-collapsible-content)"

# A line break before a bracket ("1665<br>(aged 63)") reads as a space.
_COMMA_BEFORE_BRACKET = re.compile(r",\s*(?=\()")

# An icon that carries a value: its alt text is the word the cell is missing.
_TREND_ICON_WORDS = {"increase": "up", "decrease": "down"}

_COLON_COMMA = re.compile(r"([:;]),\s*")


def classes(node: LexborNode) -> set[str]:
    """Return the class names of an element.

    Args:
        node: any element.

    Returns:
        set[str]: the whitespace-separated class names, empty when none.
    """
    return set((node.attributes.get("class") or "").split())


def icon_word(image: LexborNode) -> str:
    """Read the word an increase or decrease icon stands for.

    Args:
        image: an `<img>` element.

    Returns:
        str: "up" or "down" for an Increase or Decrease alt text, else "".
    """
    return _TREND_ICON_WORDS.get((image.attributes.get("alt") or "").lower(), "")


def cell_text(cell: LexborNode, break_separator: str = ", ") -> str:
    """Read one table cell as plain text, keeping link text and line order.

    Args:
        cell: a `<th>` or `<td>` element; modified in place (hidden sort
            keys and collapsible-list titles removed, breaks and list items
            turned into separators).
        break_separator: what a line break becomes; ", " for values, " "
            for a label that wraps over two lines.

    Returns:
        str: the cell text on one line.
    """
    for hidden in cell.css(f"{_HIDDEN}, {_COLLAPSIBLE_TITLE}"):
        hidden.decompose()
    for image in cell.css("img"):
        image.replace_with(f" {icon_word(image)} ")
    for br in cell.css("br"):
        br.replace_with(break_separator)
    for block in cell.css("div, p"):
        block.insert_before(" ")
        block.insert_after(" ")
    for items in cell.css("ul, ol, dl"):
        children = [c for c in items.iter() if c.tag in ("li", "dt", "dd")]
        for item in children[1:]:
            item.insert_before(", ")

    text = clean_text(cell.text(separator="", strip=False))
    text = _SEPARATOR_RUN.sub(", ", _SPACE_BEFORE_COMMA.sub(",", _COLON_COMMA.sub(r"\1 ", text)))
    text = _COMMA_BEFORE_BRACKET.sub(" ", text)

    return _EDGE_SEPARATOR.sub("", text)


def own_rows(table: LexborNode) -> list[LexborNode]:
    """Return the `<tr>` elements that belong to table, not to a nested one.

    Args:
        table: a `<table>` element.

    Returns:
        list[LexborNode]: the rows in document order.
    """
    rows: list[LexborNode] = []
    for row in table.css("tr"):
        parent = row.parent
        while parent is not None and parent.tag != "table":
            parent = parent.parent
        if parent is not None and parent.mem_id == table.mem_id:
            rows.append(row)
    return rows


def child_tables(cell: LexborNode) -> list[LexborNode]:
    """Return the tables nested directly in a cell, not those nested deeper.

    Args:
        cell: a `<th>` or `<td>` element.

    Returns:
        list[LexborNode]: the `<table>` descendants with no other table between
        them and the cell.
    """
    found: list[LexborNode] = []
    for table in cell.css("table"):
        parent = table.parent
        while parent is not None and parent.tag != "table" and parent.mem_id != cell.mem_id:
            parent = parent.parent
        if parent is not None and parent.mem_id == cell.mem_id:
            found.append(table)
    return found


def row_cells(row: LexborNode) -> list[LexborNode]:
    """Return the header and data cells of a row.

    Args:
        row: a `<tr>` element.

    Returns:
        list[LexborNode]: the `<th>` and `<td>` children in order.
    """
    return [c for c in row.iter() if c.tag in ("th", "td")]


def cell_span(cell: LexborNode, attribute: str = "colspan", limit: int = MAX_COLSPAN) -> int:
    """Read a colspan or rowspan attribute.

    Args:
        cell: a `<th>` or `<td>` element.
        attribute: "colspan" or "rowspan".
        limit: the largest span honoured.

    Returns:
        int: the span, 1 when absent, malformed or above limit.
    """
    raw = cell.attributes.get(attribute) or "1"
    return int(raw) if raw.isdigit() and 0 < int(raw) <= limit else 1
