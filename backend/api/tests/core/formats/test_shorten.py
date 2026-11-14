"""Tables and lists shortened at row or item boundaries, with the counts stated."""

from __future__ import annotations

from tests.factories.synthetic import list_chunk_text, table_chunk_text
from wke.core.formats.shorten import shorten_list, shorten_table
from wke.core.text.tokens import est_tokens


def test_a_table_that_fits_is_returned_unchanged() -> None:
    text = table_chunk_text(8)
    assert shorten_table(text, 10_000, est_tokens) == text


def test_shortened_table_keeps_header_first_rows_and_states_the_counts() -> None:
    text = table_chunk_text(40, total=True)
    short = shorten_table(text, 150, est_tokens)
    assert short is not None
    lines = short.splitlines()
    assert lines[:3] == text.splitlines()[:3]
    rows = [ln for ln in lines if ln.startswith("|")][2:]
    assert rows[0] == "| 1 | Nation number 1 | 3 |"
    assert rows[-1] == "| Total |  | 999 |"
    assert lines[-1] == f"(41 rows; {len(rows)} shown)"
    assert 3 < len(rows) < 41
    assert est_tokens(short) <= 150


def test_shown_rows_grow_with_the_room() -> None:
    text = table_chunk_text(60)
    counts = []
    for room in (80, 200, 600):
        short = shorten_table(text, room, est_tokens)
        assert short is not None
        counts.append(len([ln for ln in short.splitlines() if ln.startswith("| ")]) - 2)
    assert counts == sorted(counts) and len(set(counts)) == 3


def test_a_table_with_fewer_than_three_rows_of_room_is_not_shown() -> None:
    assert shorten_table(table_chunk_text(40), 25, est_tokens) is None


def test_a_table_cut_at_parse_time_keeps_its_stated_total() -> None:
    text = table_chunk_text(200) + "\n(350 rows; 200 shown)"
    short = shorten_table(text, 300, est_tokens)
    assert short is not None and short.splitlines()[-1].startswith("(350 rows; ")


def test_shortened_list_cuts_at_item_boundaries_with_nested_lines_kept() -> None:
    short = shorten_list(list_chunk_text(30), 120, est_tokens)
    assert short is not None
    lines = short.splitlines()
    shown = [ln for ln in lines if ln.startswith("- ")]
    assert lines[:2] == ["- Item number 1", "  - Detail of item 1"]
    assert lines[-2] == f"  - Detail of item {len(shown)}"
    assert lines[-1] == f"(30 items; {len(shown)} shown)"
