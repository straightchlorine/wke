"""Read a wikitable with a header row as verbatim rows."""

from __future__ import annotations

from dataclasses import dataclass, field

from selectolax.lexbor import LexborNode

from wke.core.parse.cells import (
    MAX_ROWSPAN,
    cell_span,
    cell_text,
    classes,
    own_rows,
    row_cells,
)

MIN_COLUMNS = 2

_EXCLUDED_CLASSES = frozenset(
    (
        "navbox",
        "navbox-inner",
        "navbox-subgroup",
        "infobox",
        "sidebar",
        "metadata",
        "ambox",
        "mbox-small",
        "vertical-navbox",
    )
)


def is_wikitable(table: LexborNode) -> bool:
    """Tell a content wikitable from a navbox, sidebar or metadata table.

    Args:
        table: a `<table>` element.

    Returns:
        bool: True for a `wikitable` that is not also marked as navigation
        or metadata.
    """
    table_classes = classes(table)
    return "wikitable" in table_classes and not table_classes & _EXCLUDED_CLASSES


def is_content_table(table: LexborNode) -> bool:
    """Tell a table that holds article content from navigation and furniture.

    Args:
        table: an outermost `<table>` element.

    Returns:
        bool: False for an infobox, a navbox, a sidebar, a metadata or
        message box, a table inside one of those, or a table with
        role="presentation"; True otherwise.
    """
    if table.attributes.get("role") == "presentation":
        return False
    current: LexborNode | None = table
    while current is not None:
        if classes(current) & _EXCLUDED_CLASSES:
            return False
        current = current.parent
    return True


@dataclass
class WikiTable:
    """A wikitable with a header row, as plain cell text."""

    caption: str
    header: list[str]
    rows: list[list[str]] = field(default_factory=list[list[str]])


def _take_carried(out: list[str], carried: dict[int, tuple[str, int]]) -> None:
    """Append the cells that rowspans above carry into the next columns of out.

    Args:
        out: the row being laid out, extended in place.
        carried: column -> (text, rows still to cover), updated in place.
    """
    while len(out) in carried:
        column = len(out)
        value, left = carried.pop(column)
        out.append(value)
        if left > 1:
            carried[column] = (value, left - 1)


def _expand_rows(rows: list[LexborNode], repeat_span_rows: int = 0) -> list[list[str]]:
    """Lay the cells of table rows on a grid, repeating spanned cells.

    A cell with a rowspan is repeated in the same column of the rows below
    it; a cell with a colspan is followed by empty cells, except in the
    first repeat_span_rows rows, where it is repeated over the columns it spans.

    Args:
        rows: the `<tr>` elements of one table; cells are read in place.
        repeat_span_rows: how many leading rows repeat a colspan cell's text.

    Returns:
        list[list[str]]: one list of cell texts per non-empty row, with one
        entry per column the row covers.
    """
    carried: dict[int, tuple[str, int]] = {}
    grid: list[list[str]] = []
    for row_index, row in enumerate(rows):
        cells = row_cells(row)
        if not cells:
            continue
        out: list[str] = []
        for cell in cells:
            _take_carried(out, carried)
            # A break in a header cell wraps a label; in a data cell it parts values.
            value = cell_text(cell, break_separator=" " if cell.tag == "th" else ", ")
            down = cell_span(cell, "rowspan", MAX_ROWSPAN)
            for offset in range(cell_span(cell)):
                repeated = offset == 0 or row_index < repeat_span_rows
                entry = value if repeated else ""
                if down > 1:
                    carried[len(out)] = (entry, down - 1)
                out.append(entry)
        while carried and len(out) <= max(carried):
            if len(out) in carried:
                _take_carried(out, carried)
            else:
                out.append("")
        grid.append(out)
    return grid


def _filled_width(row: list[str]) -> int:
    """Count the cells of a row up to its last one that holds text.

    Args:
        row: one expanded row.

    Returns:
        int: the width without trailing empty cells.
    """
    for index in range(len(row) - 1, -1, -1):
        if row[index]:
            return index + 1
    return 0


def _header_row_count(rows: list[LexborNode]) -> int:
    """Count the leading rows that hold only header cells.

    Args:
        rows: the `<tr>` elements of one table.

    Returns:
        int: the number of leading rows with at least one cell, all `<th>`.
    """
    count = 0
    for row in rows:
        cells = row_cells(row)
        if not cells or any(cell.tag != "th" for cell in cells):
            break
        count += 1
    return count


def _join_header(header_rows: list[list[str]], width: int) -> list[str]:
    """Join the header rows column by column, leaving out repeated text.

    Args:
        header_rows: the expanded leading header rows.
        width: the number of columns of the table.

    Returns:
        list[str]: one header text per column; a rowspan cell that repeats
        in every header row is named once.
    """
    header: list[str] = []
    for column in range(width):
        parts: list[str] = []
        for row in header_rows:
            text = row[column] if column < len(row) else ""
            if text and (not parts or parts[-1] != text):
                parts.append(text)
        header.append(" ".join(parts))
    return header


def _title_row_caption(header_rows: list[list[str]], caption: str) -> str:
    """Take a full-width title row above further header rows as the caption.

    Args:
        header_rows: the expanded leading header rows; the title row is
            removed from the list in place.
        caption: the table's own caption, "" when it has none.

    Returns:
        str: the caption to use: the table's own, or the title row's text.
    """
    first = header_rows[0]
    if len(header_rows) > 1 and len(set(first)) == 1 and first[0]:
        title = first[0]
        header_rows.pop(0)
        return caption or title
    return caption


def read_wikitable(table: LexborNode) -> WikiTable | None:
    """Read a wikitable that has a header row and at least one data row.

    Every leading all-header row is a header row; they are joined column by
    column. A full-width title row above them becomes the caption.

    Args:
        table: a `table.wikitable` element; modified in place.

    Returns:
        WikiTable | None: caption, header and data rows (cells padded to a
        common width; a colspan is followed by empty cells and a rowspan
        cell is repeated in the rows it covers); None when the first row is
        not an all-header row, a row is missing, or fewer than two columns
        exist.
    """
    caption_node = table.css_first("caption")
    caption = cell_text(caption_node) if caption_node is not None else ""
    rows = own_rows(table)
    header_count = min(_header_row_count(rows), max(len(rows) - 1, 0))
    parsed = _expand_rows(rows, repeat_span_rows=header_count if header_count > 1 else 0)
    if len(parsed) < 2 or header_count == 0:
        return None
    header_rows, body = parsed[:header_count], parsed[header_count:]
    caption = _title_row_caption(header_rows, caption)
    width = max(max(len(r) for r in header_rows), max(_filled_width(r) for r in parsed))
    if width < MIN_COLUMNS:
        return None
    pad = [""] * width
    rows_text = [r[:width] + pad[len(r) :] for r in body]
    rows_text = [r for r in rows_text if any(r)]
    header = _join_header(header_rows, width)
    return WikiTable(caption=caption, header=header, rows=rows_text) if rows_text else None
