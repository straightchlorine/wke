"""Header rows and cell residue of wikitables."""

from __future__ import annotations

from tests.factories.parsed import table_text

DISCOGRAPHY = (
    "<table class='wikitable'>"
    "<tr><th rowspan='2'>Title</th><th rowspan='2'>Details</th>"
    "<th colspan='2'>Peak chart positions</th></tr>"
    "<tr><th>UK</th><th>UK Indie</th></tr>"
    "<tr><td>Unknown</td><td>1979</td><td>71</td><td>1</td></tr></table>"
)


def test_leading_header_rows_are_joined_per_column() -> None:
    lines = table_text(DISCOGRAPHY)
    assert (
        lines[1] == "| Title | Details | Peak chart positions UK | Peak chart positions UK Indie |"
    )
    assert lines[3:] == ["| Unknown | 1979 | 71 | 1 |"]


def test_a_rowspan_header_cell_is_named_once() -> None:
    assert table_text(DISCOGRAPHY)[1].count("Title") == 1


def test_full_width_title_row_becomes_the_caption() -> None:
    html = (
        "<table class='wikitable'><tr><th colspan='2'>Symptoms</th></tr>"
        "<tr><th>Symptom</th><th>Prevalence (%)</th></tr>"
        "<tr><td>Tremor</td><td>70</td></tr></table>"
    )
    lines = table_text(html)
    assert lines[0] == "Symptoms"
    assert lines[1] == "| Symptom | Prevalence (%) |"


def test_single_header_row_keeps_empty_cells_for_a_colspan() -> None:
    html = (
        "<table class='wikitable'><tr><th>A</th><th colspan='2'>B</th></tr>"
        "<tr><td>1</td><td>2</td><td>3</td></tr></table>"
    )
    assert table_text(html)[1] == "| A | B |  |"


def test_a_line_break_in_a_header_cell_is_a_space_and_in_a_data_cell_a_comma() -> None:
    html = (
        "<table class='wikitable'><tr><th>Title</th><th><a href='./UK'>UK<br>Indie</a></th></tr>"
        "<tr><td>Meat Is Murder</td><td>1<br>2</td></tr></table>"
    )
    assert table_text(html)[1:4:2] == ["| Title | UK Indie |", "| Meat Is Murder | 1, 2 |"]


def test_navbar_links_in_a_header_cell_are_dropped() -> None:
    html = (
        "<table class='wikitable'><tr><th>Team<div class='navbar'><ul>"
        "<li class='nv-view'>v</li><li class='nv-talk'>t</li><li class='nv-edit'>e</li></ul>"
        "</div></th><th>Pts</th></tr><tr><td>A</td><td>3</td></tr></table>"
    )
    assert table_text(html)[1] == "| Team | Pts |"
