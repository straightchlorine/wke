"""Shorten the text of a table or list chunk at row boundaries.

The text of a table chunk is a caption line, a header row, a separator and one
pipe row per data row; that of a list chunk is one "- item" line per item with
nested items indented. Shortening keeps the head and states the counts; no row
or item is ever cut.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from wke.core.formats.list import item_groups
from wke.core.formats.notes import COUNT_NOTE, Noun, shown_note

MIN_SHOWN = 3
TABLE_HEAD_LINES = 3
_TOTAL = re.compile(r"total", re.I)


def _split_note(lines: list[str]) -> tuple[list[str], int | None]:
    """Separate a trailing count note from the lines it follows; return its total."""
    if lines:
        match = COUNT_NOTE.match(lines[-1])
        if match:
            return lines[:-1], int(match.group(1))
    return lines, None


def _total_row(rows: list[str], after: int) -> str | None:
    """Return the first row past index `after` whose first cell names a total."""
    for row in rows[after:]:
        first = row.split("|")[1] if row.count("|") > 1 else ""
        if _TOTAL.search(first):
            return row
    return None


def _fit(
    head: list[str],
    units: list[list[str]],
    total_units: int,
    noun: Noun,
    max_tokens: int,
    estimate: Callable[[str], int],
    tail: list[str] | None = None,
) -> str | None:
    """Build the longest head-plus-first-units text that fits max_tokens.

    Args:
        head: lines that always lead the text (caption, header, separator).
        units: the rows or item groups available, in order.
        total_units: how many rows or items the source holds in all.
        noun: "rows" or "items", for the count note.
        max_tokens: token ceiling for the whole text.
        estimate: token estimator.
        tail: a unit always appended after the first ones when it lies past
            them (the table's first total row), or None.

    Returns:
        str | None: the text with a "(N rows; M shown)" note, or None when
        not even the minimum number of units fits.
    """
    floor = min(MIN_SHOWN, len(units))
    for count in range(len(units), floor - 1, -1):
        shown = [line for unit in units[:count] for line in unit]
        extra = tail if tail and tail[0] not in shown else []
        count_shown = count + (1 if extra else 0)
        note = shown_note(total_units, count_shown, noun)
        text = "\n".join([*head, *shown, *extra, note])
        if estimate(text) <= max_tokens:
            return text
    return None


def shorten_table(text: str, max_tokens: int, estimate: Callable[[str], int]) -> str | None:
    """Shorten a table chunk's text to fit a token ceiling.

    Args:
        text: the chunk text: caption, header, separator, rows and an
            optional "(N rows; M shown)" note.
        max_tokens: the most tokens the shortened text may take.
        estimate: token estimator.

    Returns:
        str | None: the text unchanged when it fits; otherwise the caption,
        header, separator, the first rows that fit, the first "Total" row
        when it lies past them, and "(N rows; M shown)". None when fewer
        than three rows fit.
    """
    if estimate(text) <= max_tokens:
        return text
    lines, stated_total = _split_note(text.split("\n"))
    head, rows = lines[:TABLE_HEAD_LINES], lines[TABLE_HEAD_LINES:]
    total_rows = stated_total if stated_total is not None else len(rows)
    total = _total_row(rows, MIN_SHOWN)
    return _fit(
        head,
        [[r] for r in rows],
        total_rows,
        "rows",
        max_tokens,
        estimate,
        [total] if total else None,
    )


def shorten_list(text: str, max_tokens: int, estimate: Callable[[str], int]) -> str | None:
    """Shorten a list chunk's text to fit a token ceiling.

    Args:
        text: the chunk text: "- item" lines and an optional
            "(N items; M shown)" note.
        max_tokens: the most tokens the shortened text may take.
        estimate: token estimator.

    Returns:
        str | None: the text unchanged when it fits; otherwise the first
        items that fit, each with its nested lines, and "(N items; M shown)".
        None when fewer than three items fit.
    """
    if estimate(text) <= max_tokens:
        return text
    lines, stated_total = _split_note(text.split("\n"))
    groups = item_groups(lines)
    total_items = stated_total if stated_total is not None else len(groups)
    return _fit([], groups, total_items, "items", max_tokens, estimate)
