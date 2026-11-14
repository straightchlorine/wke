"""Read the label and value rows of an infobox as facts."""

from __future__ import annotations

import re

from selectolax.lexbor import LexborNode

from wke.core.parse.cells import cell_text, child_tables, classes, own_rows, row_cells
from wke.core.parse.formulas import is_formula_only
from wke.core.text.clean import clean_text

INFOBOX_MAX_ROWS = 12
TD_LABEL_MAX_CHARS = 40
# "A / A" where the second half ends the value or is followed by a comma or semicolon.
_DOUBLED = re.compile(r"(?P<half>[^/]{3,80}?) / (?P=half)(?=[,;]|$)")

# Rows under these headers hold registry codes, not facts a reader needs.
_SKIPPED_GROUPS = frozenset(("identifiers",))

_BULLETS = "\u2022-\u2013"

_TITLE_CLASSES = frozenset(("infobox-above", "infobox-title", "infobox-image"))

_PLACEHOLDER_VALUE = re.compile(
    r"^\(?(?:full |complete |partial )?(?:list|lists)\)?$"
    r"|^\(?see (?:below|above|list|the list|article|text|table)\)?$",
    re.I,
)

_LIST_LINK_LABEL = re.compile(r"^(?:full |complete )?lists? of\b|^see\b", re.I)

_SKIPPED_LABEL = re.compile(
    r"^(?:image|images|map|maps|signature|logo|coat of arms|flag|seal|caption|alt)\b", re.I
)


def is_infobox(table: LexborNode) -> bool:
    """Tell an infobox table from any other table.

    Args:
        table: a `<table>` element.

    Returns:
        bool: True when the table carries the infobox class.
    """
    return "infobox" in classes(table)


def _is_placeholder(value: str, value_cell: LexborNode) -> bool:
    """Tell whether an infobox value is a pointer to elsewhere, not a fact.

    Args:
        value: the cleaned cell text.
        value_cell: the cell, to see whether the value is one bare link.

    Returns:
        bool: True for an empty value, "Full list", "See below" and the like,
        or a single link whose label is "List of ..." or "See ...".
    """
    if not value or _PLACEHOLDER_VALUE.match(value):
        return True
    links = value_cell.css("a")
    return (
        len(links) == 1
        and clean_text(links[0].text(separator="", strip=False)) == value
        and _LIST_LINK_LABEL.match(value) is not None
    )


def _fact_rows(table: LexborNode) -> list[LexborNode]:
    """Return the rows of an infobox, with those of tables nested in a full-width cell.

    Args:
        table: a `table.infobox` element, or a table nested in one.

    Returns:
        list[LexborNode]: the `<tr>` elements in reading order. A row whose only
        cell holds tables is replaced by the rows of those tables.
    """
    rows: list[LexborNode] = []
    for row in own_rows(table):
        cells = row_cells(row)
        nested = child_tables(cells[0]) if len(cells) == 1 else []
        if nested:
            for inner in nested:
                rows.extend(_fact_rows(inner))
        else:
            rows.append(row)
    return rows


def _is_group_header(cells: list[LexborNode]) -> bool:
    """Tell a row that titles the rows below it from a label and value row.

    Args:
        cells: the cells of one row.

    Returns:
        bool: True for a single header cell that is not the infobox title.
    """
    return (
        len(cells) == 1
        and cells[0].tag == "th"
        and not classes(cells[0]) & _TITLE_CLASSES
        and cells[0].css_first("img") is None
    )


def _is_column_header_row(first: LexborNode, second: LexborNode) -> bool:
    """Tell the header row of a nested table, which names columns and states no fact.

    Args:
        first: the first cell of a two-cell row.
        second: the second cell.

    Returns:
        bool: True when both cells are headers.
    """
    return first.tag == "th" and second.tag == "th"


def _uses_td_labels(rows: list[LexborNode]) -> bool:
    """Tell an infobox whose rows are all plain `td` pairs, such as a chembox.

    Args:
        rows: the rows from `_fact_rows`.

    Returns:
        bool: True when no two-cell row has a header or label-class first cell.
    """
    pairs = [cells for cells in map(row_cells, rows) if len(cells) == 2]
    return bool(pairs) and not any(_is_label_cell(cells[0]) for cells in pairs)


def _is_label_cell(cell: LexborNode) -> bool:
    """Tell a cell that names the value next to it.

    Args:
        cell: the first cell of a two-cell row.

    Returns:
        bool: True for a `<th>` or a cell with the infobox-label class.
    """
    return cell.tag == "th" or "infobox-label" in classes(cell)


def _is_bold(cell: LexborNode) -> bool:
    """Tell a cell whose whole text is set in bold.

    Args:
        cell: a `<th>` or `<td>` element.

    Returns:
        bool: True when the cell has text and bold elements hold all of it.
    """
    text = clean_text(cell.text(separator="", strip=False))
    bold = clean_text("".join(b.text(separator="", strip=False) for b in cell.css("b, strong")))
    return bool(text) and text == bold


def _is_short_text_label(cell: LexborNode) -> bool:
    """Tell a plain `td` that can serve as a label: short and without an image.

    Args:
        cell: the first cell of a two-cell row.

    Returns:
        bool: True for text under TD_LABEL_MAX_CHARS characters and no image.
    """
    text = clean_text(cell.text(separator="", strip=False))
    return bool(text) and len(text) < TD_LABEL_MAX_CHARS and cell.css_first("img") is None


def _with_group(label: str, group: str) -> str:
    """Put the group header in front of a bulleted label.

    Args:
        label: the cleaned label.
        group: the last group header, "" when none applies.

    Returns:
        str: "Group Label" for a label that starts with a bullet or dash,
        otherwise the label as it is.
    """
    if group and label[:1] in _BULLETS:
        return f"{group} {label.lstrip(_BULLETS + ' ')}"
    return label


def collapse_doubled(value: str) -> str:
    """Collapse a part of a value that states the same thing on both sides of " / ".

    Args:
        value: a cleaned infobox value, such as a coordinate pair.

    Returns:
        str: the value with each "A / A" shortened to "A", else as it is.
    """
    return _DOUBLED.sub(r"\g<half>", value)


def read_facts(table: LexborNode) -> list[tuple[str, str]]:
    """Read the label and value rows of an infobox.

    Skips rows without both a label and a value, image, map and signature
    rows, and rows whose value is empty or a placeholder such as "Full list"
    once images and markers are gone. Rows of a table nested in a full-width
    cell are read as rows of the infobox, except their header rows and rows
    whose value is only a formula; a bulleted label gets the group
    header above it as a prefix; when no row has a header label, the first
    cell of a two-cell row is the label if it is short text.

    Args:
        table: a `table.infobox` element; modified in place.

    Returns:
        list[tuple[str, str]]: up to INFOBOX_MAX_ROWS (label, value) pairs in order.
    """
    facts: list[tuple[str, str]] = []
    rows = _fact_rows(table)
    td_labels = _uses_td_labels(rows)
    group = ""
    for row in rows:
        cells = row_cells(row)
        if _is_group_header(cells):
            group = cell_text(cells[0], break_separator=" ")
            continue
        if len(cells) != 2:
            continue
        label_cell, value_cell = cells
        if _is_bold(label_cell) and _is_bold(value_cell):
            continue
        if _is_column_header_row(label_cell, value_cell) or is_formula_only(value_cell):
            continue
        is_label = _is_label_cell(label_cell) or (td_labels and _is_short_text_label(label_cell))
        if not is_label or value_cell.css_first("table") is not None:
            continue
        if group.lower() in _SKIPPED_GROUPS:
            continue
        label = cell_text(label_cell, break_separator=" ")
        value = collapse_doubled(cell_text(value_cell))
        if not label or _is_placeholder(value, value_cell) or _SKIPPED_LABEL.match(label):
            continue
        facts.append((_with_group(label, group), value))
        if label[:1] not in _BULLETS and not td_labels:
            group = ""
        if len(facts) == INFOBOX_MAX_ROWS:
            break
    return facts
