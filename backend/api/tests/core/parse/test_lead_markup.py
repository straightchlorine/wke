"""Hidden markup and the pronunciation never reach the prose text."""

from __future__ import annotations

import pytest
from selectolax.lexbor import LexborHTMLParser

from tests.factories.parsed import parse_sections, texts
from wke.core.parse.pronunciation import has_pronunciation

RESPELLING = (
    "<a rel='mw:WikiLink' href='./Help:Pronunciation_respelling_key'>"
    "<i title='English pronunciation respelling'>chih-<span>KOH</span>-nee</i></a>"
)
IPA_SPAN = (
    "<span class='rt-commentedText nowrap'><span class='IPA nopopups'>"
    "<a rel='mw:WikiLink' href='./Help:IPA/English'>/fu&#720;/</a></span></span>"
)


def test_hidden_coordinates_are_dropped_from_a_paragraph() -> None:
    html = (
        "<p>Nokia is a company, with a market capital of 70%.<span class='geo-inline-hidden "
        "noexcerpt'>60 13N 24 45E / 60.225 N 24.756 E</span></p>"
    )
    assert texts(parse_sections(html))[0] == "Nokia is a company, with a market capital of 70%."


def test_nondefault_coordinate_form_and_display_none_spans_are_dropped() -> None:
    html = (
        "<p>It lies at 60 N.<span class='geo-nondefault'>60.2</span>"
        "<span style='display:none'>hidden</span><span style='display: none'>more</span></p>"
    )
    assert texts(parse_sections(html))[0] == "It lies at 60 N."


def test_ipa_span_and_the_punctuation_it_leaves_are_dropped_from_the_lead() -> None:
    html = (
        f"<p><b>Pierre</b> ({IPA_SPAN}; French: [pj]; 1601) was a lawyer and a mathematician.</p>"
    )
    assert texts(parse_sections(html))[0] == (
        "Pierre (French: [pj]; 1601) was a lawyer and a mathematician."
    )


def test_space_left_at_the_start_of_the_parenthetical_is_closed() -> None:
    html = f"<p><b>Foo</b> ({IPA_SPAN} foo-BAR; born 1900) was a poet and a mathematician.</p>"
    assert texts(parse_sections(html))[0] == (
        "Foo (foo-BAR; born 1900) was a poet and a mathematician."
    )


def test_language_label_left_without_its_pronunciation_is_dropped() -> None:
    html = f"<p><b>Madonna</b> (Italian: {IPA_SPAN}; born 1958) is a singer and a songwriter.</p>"
    assert texts(parse_sections(html))[0] == "Madonna (born 1958) is a singer and a songwriter."


def test_respelling_is_dropped_with_the_ipa_from_the_lead() -> None:
    html = (
        f"<p><b>Madonna</b> ({IPA_SPAN} {RESPELLING}, Italian: {IPA_SPAN}; born 1958)"
        " is a singer and a songwriter.</p>"
    )
    assert texts(parse_sections(html))[0] == "Madonna (born 1958) is a singer and a songwriter."


def test_audio_player_is_dropped_with_the_pronunciation() -> None:
    audio = (
        "<span class='ext-phonos'><sup class='ext-phonos-attribution'>"
        "<a href='./File:En-us-Foo.ogg' title='File:En-us-Foo.ogg'>&#9432;</a></sup></span>"
    )
    html = f"<p><b>Foo</b> ({audio} {RESPELLING}; born 1900) was a poet and a mathematician.</p>"
    assert texts(parse_sections(html))[0] == "Foo (born 1900) was a poet and a mathematician."


def test_respelling_alone_leaves_no_empty_brackets() -> None:
    html = f"<p><b>Foo</b> ({RESPELLING}) is a town in the north of the country.</p>"
    assert texts(parse_sections(html))[0] == "Foo is a town in the north of the country."


def test_coordinate_separator_goes_with_the_second_form_in_prose() -> None:
    coordinate = (
        "<span class='geo-default'>51 N 4 W</span><span class='geo-multi-punct'> / </span>"
        "<span class='geo-nondefault'>51.99 N 4.74 W</span>"
    )
    html = f"<p>It came from a crag ({coordinate}), near the town of Crymych.</p>"
    assert (
        texts(parse_sections(html))[0]
        == "It came from a crag (51 N 4 W), near the town of Crymych."
    )


def test_ipa_label_is_dropped_with_the_ipa_from_the_lead() -> None:
    label = "<span class='IPA-label IPA-label-small'>pronounced</span><span> </span>"
    html = f"<p><b>Mostar</b> ({label}{IPA_SPAN}) is a town in the south of the country.</p>"
    assert texts(parse_sections(html))[0] == "Mostar is a town in the south of the country."


def test_ipa_only_parenthetical_leaves_no_empty_brackets() -> None:
    html = f"<p><b>Foo</b> ({IPA_SPAN}) is a town in the north of the country.</p>"
    assert texts(parse_sections(html))[0] == "Foo is a town in the north of the country."


@pytest.mark.parametrize(
    ("lead", "expected"),
    [
        ("Foo (/fu:/; born 1900) was a poet.", "Foo (born 1900) was a poet."),
        ("Foo (/fu:/) was a poet.", "Foo was a poet."),
        ("Foo Bar (/fu: ba:/, French: [fu]) was a poet.", "Foo Bar (French: [fu]) was a poet."),
    ],
)
def test_slash_pronunciation_right_after_the_title_is_dropped(lead: str, expected: str) -> None:
    assert texts(parse_sections(f"<p>{lead}</p>"))[0] == expected


@pytest.mark.parametrize(
    ("lead", "expected"),
    [
        (
            f"Belgrade ({IPA_SPAN} or {IPA_SPAN}; Serbian: Beograd, lit. 'White City', {IPA_SPAN})",
            "Belgrade (Serbian: Beograd, lit. 'White City')",
        ),
        (
            f"Thessaloniki (Greek: Thessalonike {IPA_SPAN}; also known by other names)",
            "Thessaloniki (Greek: Thessalonike; also known by other names)",
        ),
        (f"Zeus ({IPA_SPAN}, Ancient Greek: {IPA_SPAN})", "Zeus"),
        (f"Mostar (Serbo-Croatian: {IPA_SPAN}; founded 1452)", "Mostar (founded 1452)"),
        (f"Foo (born 1900; {IPA_SPAN}, died 1990)", "Foo (born 1900; died 1990)"),
    ],
    ids=[
        "connective-or-and-trailing-comma",
        "space-before-separator",
        "two-word-label",
        "hyphenated-label",
        "stronger-separator-kept",
    ],
)
def test_what_a_dropped_pronunciation_leaves_is_removed(lead: str, expected: str) -> None:
    html = f"<p><b>{lead}</b> is a place in the south of the country.</p>"
    assert texts(parse_sections(html))[0] == f"{expected} is a place in the south of the country."


def test_a_parenthetical_without_pronunciation_is_left_as_written() -> None:
    lead = "Peaks rise above 7,000 metres (23,000 ft; a, b) in the north of the country."
    assert texts(parse_sections(f"<p>{lead}</p>"))[0] == lead


def test_a_slash_pair_later_in_the_lead_is_kept() -> None:
    lead = "Foo was a poet (born 1900) and an editor who wrote either/or and 1/2 of it."
    assert texts(parse_sections(f"<p>{lead}</p>"))[0] == lead


def test_pronunciation_in_a_later_section_is_left_alone() -> None:
    body = "<p>The word (/fu:/) is old and was used by many speakers.</p>"
    assert "(/fu:/)" in texts(parse_sections("<p>The lead is a sentence.</p>", body))[1]


def test_two_separators_left_by_a_pronunciation_and_its_label_leave_no_empty_start() -> None:
    html = (
        f"<p><b>Pierre</b> ({IPA_SPAN}; French: {IPA_SPAN}; 17 August 1601) "
        "was a lawyer and a mathematician.</p>"
    )
    assert texts(parse_sections(html))[0] == (
        "Pierre (17 August 1601) was a lawyer and a mathematician."
    )


@pytest.mark.parametrize(
    ("html", "found"),
    [
        (f"<p>Foo ({IPA_SPAN}) was a poet.</p>", True),
        (f"<p>Foo ({RESPELLING}) was a poet.</p>", True),
        ("<p>Foo <span class='ext-phonos'>x</span> was a poet.</p>", True),
        ("<p>Foo (born 1900) was a poet.</p>", False),
    ],
    ids=["ipa", "respelling", "audio", "none"],
)
def test_has_pronunciation(html: str, found: bool) -> None:
    assert has_pronunciation(LexborHTMLParser(html)) is found
