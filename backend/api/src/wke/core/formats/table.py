"""Text of a table chunk: caption line, pipe header, separator and pipe rows."""

from __future__ import annotations

from wke.core.formats.notes import shown_note

TABLE_ROW_CEILING = 200


def pipe_row(cells: list[str]) -> str:
    """Join cells into one Markdown pipe row, escaping pipes inside cells.

    Args:
        cells: the cell texts of one row.

    Returns:
        str: the row as "| a | b |".
    """
    return "| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |"


def table_text(title: str, header: list[str], rows: list[list[str]]) -> str:
    """Render a table as a caption line and compact Markdown rows.

    Args:
        title: caption to print; the caller passes the section title when
            the table has none.
        header: the header cells.
        rows: the data rows.

    Returns:
        str: the caption, the header row, a separator and every row; a
        table over TABLE_ROW_CEILING rows is cut at a row boundary and ends
        with a "(N rows; M shown)" note.
    """
    shown = rows[:TABLE_ROW_CEILING]
    lines = [title, pipe_row(header), pipe_row(["---"] * len(header))]
    lines.extend(pipe_row(r) for r in shown)
    if len(shown) < len(rows):
        lines.append(shown_note(len(rows), len(shown), "rows"))
    return "\n".join(lines)
