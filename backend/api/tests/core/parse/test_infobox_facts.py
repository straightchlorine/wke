"""How the infobox reader finds labels, groups and values."""

from __future__ import annotations

import pytest

from tests.factories.parsed import facts_lines

BULLET = chr(0x2022)


def test_rows_of_a_table_nested_in_a_full_width_cell_are_facts() -> None:
    rows = (
        "<tr><td colspan='2'><table style='display:inline-table'>"
        "<tr><th>Date</th><td>1 July 1942</td></tr>"
        "<tr><th>Location</th><td>Stalingrad</td></tr></table></td></tr>"
        "<tr><th>Result</th><td>Soviet victory</td></tr>"
    )
    assert facts_lines(rows) == [
        "Date: 1 July 1942",
        "Location: Stalingrad",
        "Result: Soviet victory",
    ]


def test_plain_td_pairs_are_facts_when_no_row_has_a_header_label() -> None:
    rows = (
        "<tr><th colspan='2'>Identifiers</th></tr>"
        "<tr><td>CAS Number</td><td>7487-94-7</td></tr>"
        "<tr><th colspan='2'>Properties</th></tr>"
        "<tr><td>Chemical formula</td><td>HgCl2</td></tr>"
        "<tr><td>Molar mass</td><td>271.52 g/mol</td></tr>"
    )
    assert facts_lines(rows) == ["Chemical formula: HgCl2", "Molar mass: 271.52 g/mol"]


def test_td_pairs_next_to_header_labels_are_not_facts() -> None:
    rows = "<tr><th>Date</th><td>1942</td></tr><tr><td>Germany</td><td>Soviet Union</td></tr>"
    assert facts_lines(rows) == ["Date: 1942"]


def test_td_label_over_forty_characters_is_not_a_label() -> None:
    long_label = "A very long cell of running text that is no label at all"
    rows = f"<tr><td>{long_label}</td><td>x</td></tr><tr><td>Short</td><td>y</td></tr>"
    assert facts_lines(rows) == ["Short: y"]


def test_label_with_a_block_child_keeps_a_space() -> None:
    rows = "<tr><th>Capital<div>and largest city</div></th><td>Thimphu</td></tr>"
    assert facts_lines(rows) == ["Capital and largest city: Thimphu"]


def test_label_with_a_line_break_keeps_a_space() -> None:
    rows = "<tr><th>Capital<br/>city</th><td>Thimphu</td></tr>"
    assert facts_lines(rows) == ["Capital city: Thimphu"]


def test_bulleted_rows_carry_the_group_header_above_them() -> None:
    rows = (
        "<tr><th colspan='2'>Population (2010 Census)</th></tr>"
        "<tr><th>&bull; Total</th><td>60,755</td></tr>"
        "<tr><th>&bull; Density</th><td>20/km2</td></tr>"
        "<tr><th>Demonym</th><td>Bhutanese</td></tr>"
        "<tr><th>&bull; Odd one</th><td>z</td></tr>"
    )
    assert facts_lines(rows) == [
        "Population (2010 Census) Total: 60,755",
        "Population (2010 Census) Density: 20/km2",
        "Demonym: Bhutanese",
        BULLET + " Odd one: z",
    ]


def test_the_infobox_title_row_is_not_a_group() -> None:
    rows = (
        "<tr><th colspan='2' class='infobox-above'>Bhutan</th></tr>"
        "<tr><th>&bull; Total</th><td>1</td></tr>"
    )
    assert facts_lines(rows) == [BULLET + " Total: 1"]


def test_increase_and_decrease_icons_read_as_words() -> None:
    rows = (
        "<tr><th>Turnout</th><td>64.3%<img alt='Decrease' src='x.svg'/> 2.3 pp</td></tr>"
        "<tr><th>Seats</th><td>12<img alt='Increase'/>3<img alt='Steady'/></td></tr>"
    )
    assert facts_lines(rows) == ["Turnout: 64.3% down 2.3 pp", "Seats: 12 up 3"]


def test_a_colon_before_a_line_break_leaves_no_comma() -> None:
    rows = "<tr><th>Reign</th><td>22 regnal years:<br/>1479-1457 BC</td></tr>"
    assert facts_lines(rows) == ["Reign: 22 regnal years: 1479-1457 BC"]


def test_line_breaks_between_values_still_become_commas() -> None:
    rows = "<tr><th>Languages</th><td>Dzongkha<br/>English</td></tr>"
    assert facts_lines(rows) == ["Languages: Dzongkha, English"]


def test_header_row_of_a_nested_table_is_not_a_fact() -> None:
    rows = (
        "<tr><td colspan='2'><table>"
        "<tr><th>Years</th><th>Team</th></tr>"
        "<tr><th>2010</th><td>Richmond F.C.</td></tr></table></td></tr>"
    )
    assert facts_lines(rows) == ["2010: Richmond F.C."]


def test_text_before_a_block_is_not_glued_to_the_text_after_it() -> None:
    rows = (
        "<tr><th>Location</th><td><div>Stalingrad, Soviet Union</div><span>48N 44E</span></td></tr>"
    )
    assert facts_lines(rows) == ["Location: Stalingrad, Soviet Union 48N 44E"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("36N 11W / 36N 11W", "36N 11W"),
        ("36 N 11 W / 36 N 11 W, 200 km west of the cape", "36 N 11 W, 200 km west of the cape"),
        ("18N 76W / 18.100N 76.667W", "18N 76W / 18.100N 76.667W"),
    ],
    ids=["doubled", "doubled-inside-a-longer-value", "two-forms-stay"],
)
def test_a_value_stated_twice_around_a_slash_is_stated_once(value: str, expected: str) -> None:
    assert facts_lines(f"<tr><th>Coordinates</th><td>{value}</td></tr>") == [
        f"Coordinates: {expected}"
    ]


def test_an_infobox_coordinate_keeps_its_nondefault_form() -> None:
    rows = (
        "<tr><th>Coordinates</th><td><span class='geo-default'>43 N 17 E</span>"
        "<span class='geo-multi-punct'> / </span>"
        "<span class='geo-nondefault'>43.3 N 17.8 E</span></td></tr>"
    )
    assert facts_lines(rows) == ["Coordinates: 43 N 17 E / 43.3 N 17.8 E"]


def test_a_bold_label_and_bold_value_row_is_a_column_header_not_a_fact() -> None:
    rows = (
        "<tr><th><b>Years</b></th><td colspan='3'><b>Team</b></td></tr>"
        "<tr><th>2010</th><td colspan='3'>Richmond</td></tr>"
    )
    assert facts_lines(rows) == ["2010: Richmond"]


def test_placeholder_rows_are_dropped_and_real_rows_kept() -> None:
    rows = "".join(
        f"<tr><th>{label}</th><td>{value}</td></tr>"
        for label, value in (
            ("Awards", "<a href='./X'>Full list</a>"),
            ("Notes", "See below"),
            ("Extra", "see list"),
            ("Gap", ""),
            ("Credits", "<a href='./L'>List of works</a>"),
            ("Born", "1900"),
            ("Genre", "<a href='./P'>Pop</a>, <a href='./R'>Rock</a>"),
            ("Awards won", "Full list of 12 honours"),
        )
    )
    assert facts_lines(rows) == [
        "Born: 1900",
        "Genre: Pop, Rock",
        "Awards won: Full list of 12 honours",
    ]


def test_collapsible_list_title_is_not_part_of_the_value() -> None:
    rows = (
        "<tr><th>Citizenship</th><td><div class='collapsible-list mw-collapsible mw-collapsed'>"
        "<div><span class='nobold'><i>See list</i></span></div>"
        "<ul class='mw-collapsible-content'><li>Kingdom of Wurttemberg</li><li>Switzerland</li>"
        "</ul></div></td></tr>"
    )
    assert facts_lines(rows) == ["Citizenship: Kingdom of Wurttemberg, Switzerland"]


def test_a_line_break_before_a_bracket_reads_as_a_space() -> None:
    rows = "<tr><th>Died</th><td>12 January 1665<br/>(aged 63)<br/>Castres</td></tr>"
    assert facts_lines(rows) == ["Died: 12 January 1665 (aged 63), Castres"]
