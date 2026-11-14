"""The count note that ends a table or list cut at a row or item boundary."""

from __future__ import annotations

import re
from typing import Literal

Noun = Literal["rows", "items"]


def _note_pattern(nouns: str) -> re.Pattern[str]:
    """Build the pattern of a whole note line; groups: total, noun, shown."""
    return re.compile(rf"^\((\d+) ({nouns}); (\d+) shown\)$")


TABLE_NOTE = _note_pattern("rows")
LIST_NOTE = _note_pattern("items")
COUNT_NOTE = _note_pattern("rows|items")


def shown_note(total: int, shown: int, noun: Noun) -> str:
    """Build the "(N rows; M shown)" note.

    Args:
        total: how many rows or items the source holds in all.
        shown: how many the text carries.
        noun: "rows" or "items".

    Returns:
        str: the note, in the shape TABLE_NOTE, LIST_NOTE and COUNT_NOTE match.
    """
    return f"({total} {noun}; {shown} shown)"
