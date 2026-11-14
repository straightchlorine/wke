"""The count note a cut table or list ends with, and the patterns that recognise it."""

from __future__ import annotations

import pytest

from wke.core.formats.notes import COUNT_NOTE, LIST_NOTE, TABLE_NOTE, Noun, shown_note


@pytest.mark.parametrize(
    ("noun", "own", "other"), [("rows", TABLE_NOTE, LIST_NOTE), ("items", LIST_NOTE, TABLE_NOTE)]
)
def test_a_note_matches_its_own_pattern_only(noun: Noun, own, other) -> None:
    note = shown_note(250, 200, noun)
    assert own.match(note) and not other.match(note)
    match = COUNT_NOTE.match(note)
    assert match is not None and match.groups() == ("250", noun, "200")


@pytest.mark.parametrize(
    "line", ["(250 rows; 200 shown) ", "| (250 rows; 200 shown) |", "(rows; 200 shown)"]
)
def test_a_line_that_only_contains_a_note_is_not_one(line: str) -> None:
    assert not COUNT_NOTE.match(line)
