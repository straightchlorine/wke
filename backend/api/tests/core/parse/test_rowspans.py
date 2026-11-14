"""Rowspan and colspan expansion and the table drop counts, on small inline HTML."""

from __future__ import annotations

import pytest
from selectolax.lexbor import LexborHTMLParser

from tests.factories.parsed import LEAD, parse_sections
from wke.core.parse import ParsedArticle
from wke.core.parse.wikitable import WikiTable, read_wikitable


def _read(html: str) -> WikiTable | None:
    table = LexborHTMLParser(f"<html><body>{html}</body></html>").css_first("table")
    assert table is not None
    return read_wikitable(table)


def _parse(body: str) -> ParsedArticle:
    return parse_sections(LEAD, body)


def test_rowspan_repeats_the_cell_in_the_rows_below_it() -> None:
    table = _read(
        "<table class='wikitable'>"
        "<tr><th>Date</th><th>State</th><th>Hit</th></tr>"
        "<tr><td>1978</td><td rowspan='2'>Illinois</td><td>Yes</td></tr>"
        "<tr><td>1979</td><td>No</td></tr>"
        "<tr><td>1980</td><td>Utah</td><td>Yes</td></tr></table>"
    )
    assert table is not None
    assert table.rows == [
        ["1978", "Illinois", "Yes"],
        ["1979", "Illinois", "No"],
        ["1980", "Utah", "Yes"],
    ]


def test_rowspan_in_the_first_column_and_a_colspan_in_one_table() -> None:
    table = _read(
        "<table class='wikitable'>"
        "<tr><th>Group</th><th>Name</th><th colspan='2'>Score</th></tr>"
        "<tr><td rowspan='3'>A</td><td>x</td><td>1</td><td>2</td></tr>"
        "<tr><td>y</td><td colspan='2'>draw</td></tr>"
        "<tr><td>z</td><td>3</td><td>4</td></tr></table>"
    )
    assert table is not None
    assert table.header == ["Group", "Name", "Score", ""]
    assert table.rows == [
        ["A", "x", "1", "2"],
        ["A", "y", "draw", ""],
        ["A", "z", "3", "4"],
    ]


def test_rowspan_and_colspan_on_one_cell_fill_a_block() -> None:
    table = _read(
        "<table class='wikitable'><tr><th>A</th><th>B</th><th>C</th></tr>"
        "<tr><td colspan='2' rowspan='2'>wide</td><td>1</td></tr>"
        "<tr><td>2</td></tr></table>"
    )
    assert table is not None
    assert table.rows == [["wide", "", "1"], ["wide", "", "2"]]


def test_rowspan_past_the_last_row_and_a_short_row_stay_aligned() -> None:
    table = _read(
        "<table class='wikitable'><tr><th>A</th><th>B</th><th>C</th></tr>"
        "<tr><td>1</td><td>2</td><td rowspan='5'>end</td></tr>"
        "<tr><td>3</td><td>4</td></tr></table>"
    )
    assert table is not None
    assert all(len(row) == 3 for row in table.rows)
    assert [row[2] for row in table.rows] == ["end", "end"]


def test_a_content_table_without_the_wikitable_class_is_read() -> None:
    article = _parse(
        "<table class='tracklist'><caption>Songs</caption>"
        "<tr><th>No.</th><th>Title</th></tr><tr><th>1.</th><td>First</td></tr></table>"
    )
    section = article.sections[1]
    assert [c.kind for c in article.chunks if c.id in section.chunk_ids] == ["table"]
    assert section.dropped_tables == 0


def test_unreadable_content_tables_and_wikitables_count_as_dropped() -> None:
    article = _parse(
        "<table class='plainrowheaders'><tr><td>a</td><td>b</td></tr></table>"
        "<table class='wikitable'><tr><td>a</td><td>b</td></tr></table>"
        "<table class='wikitable'><tr><th>A</th></tr><tr><td>1</td></tr></table>"
    )
    section = article.sections[1]
    assert section.chunk_ids == []
    assert section.dropped_tables == 3
    assert section.dropped_non_prose is True


def test_navigation_and_metadata_tables_are_never_counted() -> None:
    article = _parse(
        "<div class='navbox'><table class='nowraplinks navbox-inner'>"
        "<tr><td>x</td></tr></table></div>"
        "<table class='sidebar'><tr><td>x</td></tr></table>"
        "<table class='box-Expand plainlinks metadata ambox'>"
        "<tr><td>x</td></tr></table>"
        "<table role='presentation'><tr><td>x</td></tr></table>"
    )
    section = article.sections[1]
    assert section.dropped_tables == 0
    assert section.dropped_non_prose is False


def test_a_table_over_the_chunk_cap_is_counted_and_truncates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("wke.core.parse.state.MAX_CHUNKS", 1)
    article = _parse(
        "<table class='wikitable'><tr><th>A</th><th>B</th></tr>"
        "<tr><td>1</td><td>2</td></tr></table>"
    )
    assert article.sections[1].dropped_tables == 1
    assert article.truncated is True


def test_a_table_over_200_rows_is_cut_at_a_row_with_the_note() -> None:
    rows = "".join(f"<tr><td>{n}</td><td>v{n}</td></tr>" for n in range(1, 251))
    article = _parse(f"<table class='wikitable'><tr><th>A</th><th>B</th></tr>{rows}</table>")
    text = next(c.text for c in article.chunks if c.kind == "table")
    lines = text.splitlines()
    assert lines[-1] == "(250 rows; 200 shown)"
    assert lines[-2] == "| 200 | v200 |"
