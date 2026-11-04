"""Text of a list chunk: one "- item" line per item, nested items indented."""

from __future__ import annotations

from wke.core.formats.notes import shown_note

LIST_ITEM_CEILING = 200
LIST_INDENT = "  "


def item_groups(lines: list[str]) -> list[list[str]]:
    """Group list lines into top-level items with their nested lines.

    Args:
        lines: lines as read_list returns them.

    Returns:
        list[list[str]]: one group per unindented line, holding that line and
        the indented lines that follow it.
    """
    groups: list[list[str]] = []
    for line in lines:
        if line.startswith(LIST_INDENT) and groups:
            groups[-1].append(line)
        else:
            groups.append([line])
    return groups


def list_text(lines: list[str]) -> str:
    """Render list lines as the text of a list chunk.

    Args:
        lines: lines as read_list returns them.

    Returns:
        str: the lines joined with newlines; a list of more than
        LIST_ITEM_CEILING items is cut at an item boundary and ends with a
        "(N items; M shown)" note.
    """
    groups = item_groups(lines)
    shown = groups[:LIST_ITEM_CEILING]
    out = [line for group in shown for line in group]
    if len(shown) < len(groups):
        out.append(shown_note(len(groups), len(shown), "items"))
    return "\n".join(out)
