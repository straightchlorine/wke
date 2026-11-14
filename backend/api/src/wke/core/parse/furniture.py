"""Remove page furniture from a revision and empty its tables once they are read."""

from __future__ import annotations

from selectolax.lexbor import LexborHTMLParser, LexborNode

from wke.core.parse.cells import classes
from wke.core.parse.formulas import keep_formulas
from wke.core.parse.tables import TableInfo, inside_table, read_tables

# The separator and the second form of a coordinate pair, as the coord
# template renders them:
#   <span class="geo-default">43 N 17 E</span><span class="geo-multi-punct"> / </span>
#   <span class="geo-nondefault">43.3 N 17.8 E</span>
# Prose keeps the first form only ("43 N 17 E"). An infobox keeps all three,
# so its value reads "43 N 17 E / 43.3 N 17.8 E".
SECOND_COORDINATE_CLASSES = frozenset(("geo-multi-punct", "geo-nondefault"))

# Elements that are not article text; each goes with everything inside it.
DROP_SELECTOR = ", ".join(
    (
        "figure",
        ".hatnote",
        ".mw-editsection",
        "sup.reference",
        # Parsoid's footnote markers.
        "[typeof='mw:Extension/ref']",
        # MathML that is not a formula element; keep_formulas has already
        # reduced each formula element, a `<math>` one included, to its TeX.
        "math:not(.mwe-math-element):not(.wke-formula)",
        # Coordinates the page shows only next to its title.
        ".geo-inline-hidden",
        *(f".{name}" for name in sorted(SECOND_COORDINATE_CLASSES)),
        "[style*='display:none']",
        "[style*='display: none']",
        "style",
        # Metadata links, such as categories and deduplicated template styles.
        "link",
        ".noprint",
        ".mw-empty-elt",
        ".pullquote",
        # The CS1 module's maintenance and error notes, shown as visible text
        # with template braces ("{{cite journal}}: CS1 maint: ..."): citation
        # apparatus, not article prose.
        ".citation-comment",
    )
)


def hollow(node: LexborNode) -> None:
    """Remove every child of a node and keep the empty node.

    Args:
        node: the element to empty, modified in place.
    """
    for child in list(node.iter(include_text=True)):
        child.decompose()


def _inside_any(node: LexborNode, nodes: dict[int, LexborNode]) -> bool:
    """Tell whether an element sits inside another element of a set.

    Args:
        node: the element to test.
        nodes: the candidate ancestors, keyed by mem_id.

    Returns:
        bool: True when an ancestor of the node is in the set.
    """
    parent = node.parent
    while parent is not None:
        if parent.mem_id in nodes:
            return True
        parent = parent.parent
    return False


def drop_furniture(tree: LexborHTMLParser) -> dict[int, TableInfo]:
    """Remove page furniture, then read every table and empty it.

    Formulas are first reduced to their TeX (keep_formulas). Every match of
    DROP_SELECTOR is removed, except the second coordinate form and its
    separator inside a table. The tables are read next and stay in the tree as empty shells.

    Args:
        tree: the parsed document, modified in place.

    Returns:
        dict[int, TableInfo]: what each infobox, wikitable and content table
        held, keyed by the table's mem_id.
    """
    keep_formulas(tree)
    seen: dict[int, LexborNode] = {}
    for node in tree.css(DROP_SELECTOR):
        if classes(node) & SECOND_COORDINATE_CLASSES and inside_table(node):
            continue
        seen[node.mem_id] = node

    # Removing a node frees its subtree, and a match can sit inside another
    # match (a reference inside a noprint span): its handle would then point at
    # freed memory.
    # Pick the outermost matches while the tree is intact and remove only those;
    # the inner ones go with them, whatever order the selector returns.
    outermost = [node for node in seen.values() if not _inside_any(node, seen)]
    for node in outermost:
        # A table is emptied, not removed: the empty table still separates the
        # paragraphs around it and marks the paragraph before it as a list
        # introduction.
        if node.tag == "table":
            hollow(node)
        else:
            node.decompose()
    tables = read_tables(tree)
    # Last first: a nested table is emptied before the table around it frees it.
    for table in reversed(tree.css("table")):
        hollow(table)
    return tables
