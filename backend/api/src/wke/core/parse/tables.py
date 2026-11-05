"""Read every outermost infobox and wikitable before the tables are emptied."""

from __future__ import annotations

from dataclasses import dataclass

from selectolax.lexbor import LexborHTMLParser, LexborNode

from wke.core.parse.infobox import is_infobox, read_facts
from wke.core.parse.wikitable import WikiTable, is_content_table, is_wikitable, read_wikitable


@dataclass
class TableInfo:
    """What the pre-pass read from one table before it was hollowed."""

    infobox: list[tuple[str, str]] | None = None
    wikitable: WikiTable | None = None
    is_wikitable: bool = False
    is_content: bool = False


def inside_table(node: LexborNode) -> bool:
    """Tell whether an element sits inside a table.

    Args:
        node: any element.

    Returns:
        bool: True when an ancestor is a `<table>`.
    """
    parent = node.parent
    while parent is not None:
        if parent.tag == "table":
            return True
        parent = parent.parent
    return False


def read_tables(tree: LexborHTMLParser) -> dict[int, TableInfo]:
    """Read every outermost infobox and wikitable before the tables are emptied.

    Args:
        tree: the parsed document, furniture already removed.

    Returns:
        dict[int, TableInfo]: what each read table held, keyed by mem_id.
    """
    found: dict[int, TableInfo] = {}
    for table in tree.css("table"):
        if inside_table(table):
            continue
        if is_infobox(table):
            found[table.mem_id] = TableInfo(infobox=read_facts(table))
        elif is_wikitable(table):
            found[table.mem_id] = TableInfo(wikitable=read_wikitable(table), is_wikitable=True)
        elif is_content_table(table):
            found[table.mem_id] = TableInfo(wikitable=read_wikitable(table), is_content=True)
    return found
