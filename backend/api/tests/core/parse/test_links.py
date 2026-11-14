"""Wikilinks of kept paragraphs become spans on the chunk text."""

from __future__ import annotations

import pytest

from tests.factories.parsed import LEAD, link_spans, parse_sections


def _link(title: str, label: str, extra: str = "") -> str:
    return f"<a rel='mw:WikiLink' href='./{title}{extra}'>{label}</a>"


def _spans(html: str) -> list[tuple[str, str]]:
    """Return (covered text, title) for every span of the lead's first chunk."""
    return link_spans(parse_sections(html).chunks[0])


def test_spans_cover_exactly_the_link_text() -> None:
    html = f"<p>The {_link('Cat', 'cat')} sat on the {_link('Mat', 'mat')} today.</p>"
    assert _spans(html) == [("cat", "Cat"), ("mat", "Mat")]


def test_title_is_decoded_without_fragment_or_underscores() -> None:
    html = (
        f"<p>He moved to {_link('S%C3%A3o_Paulo', 'Sao Paulo', '#History')} "
        f"in the {_link('Pierre_de_Fermat', 'old days')} era.</p>"
    )
    assert _spans(html) == [
        ("Sao Paulo", "S" + chr(0xE3) + "o Paulo"),
        ("old days", "Pierre de Fermat"),
    ]


def test_external_red_and_fragment_only_links_are_excluded() -> None:
    html = (
        "<p>Read <a rel='mw:ExtLink' href='https://example.org/'>the site</a>, "
        "<a rel='mw:WikiLink' href='./Nobody?action=edit&amp;redlink=1'>nobody</a> "
        "and <a rel='mw:WikiLink' href='#cite_note-1'>a note</a> or "
        f"{_link('Cat', 'cat')} here.</p>"
    )
    assert _spans(html) == [("cat", "Cat")]


@pytest.mark.parametrize(
    "title",
    [
        "File:Cat.jpg",
        "Category:Cats",
        "Help:IPA/English",
        "Wikipedia:Citation_needed",
        "Template:Cats",
        "Template_talk:Cats",
        "Portal:Cats",
        "Talk:Cat",
    ],
)
def test_links_to_pages_that_are_not_articles_are_excluded(title: str) -> None:
    html = f"<p>A {_link(title, 'note')} and a {_link('Cat', 'cat')} here.</p>"
    assert _spans(html) == [("cat", "Cat")]


def test_a_space_inside_the_anchor_stays_out_of_the_span_and_the_text_stays_clean() -> None:
    html = f"<p>It is the capital and {_link('Largest', ' largest city')} of it.</p>"
    chunk = parse_sections(html).chunks[0]
    assert chunk.text == "It is the capital and largest city of it."
    assert link_spans(chunk) == [("largest city", "Largest")]


def test_spans_follow_the_text_through_a_merge_of_two_paragraphs() -> None:
    html = f"<p>First {_link('One', 'one')} here.</p><p>Second {_link('Two', 'two')} here.</p>"
    chunk = parse_sections(LEAD, html).chunks[1]
    assert chunk.text == "First one here. Second two here."
    assert link_spans(chunk) == [
        ("one", "One"),
        ("two", "Two"),
    ]


def test_spans_survive_a_dropped_navigation_sentence_before_the_link() -> None:
    html = f"<p>See also the article on cats. A {_link('Dog', 'dog')} barked loudly.</p>"
    assert _spans(html) == [("dog", "Dog")]


def test_spans_shift_after_the_pronunciation_is_dropped_from_the_lead() -> None:
    html = (
        "<p><b>Foo</b> (<span class='IPA'>/fu:/</span>; born 1900) was a "
        f"{_link('Poet', 'poet')} of note.</p>"
    )
    assert _spans(html) == [("poet", "Poet")]


def test_spans_follow_the_text_when_a_long_paragraph_is_split() -> None:
    sentence = "A filler sentence of ordinary words goes right here. "
    html = f"<p>{sentence * 40}Last {_link('End', 'end')} of it all.</p>"
    article = parse_sections(LEAD, html)
    linked = [c for c in article.chunks if c.links]
    assert len(article.chunks) > 2
    assert [span for c in linked for span in link_spans(c)] == [("end", "End")]


def test_a_link_whose_sentence_is_dropped_leaves_no_span() -> None:
    html = f"<p>A fine sentence stands. See also {_link('Cats', 'cats')}.</p>"
    article = parse_sections(LEAD, html)
    assert article.chunks[1].links == []


def test_chunks_without_links_carry_an_empty_list() -> None:
    assert parse_sections(f"<p>{LEAD[3:-4]}</p>").chunks[0].links == []


def test_links_past_the_per_paragraph_cap_are_not_marked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("wke.core.parse.links.MAX_LINKS_PER_PARAGRAPH", 2)
    html = f"<p>{_link('A', 'one')}, {_link('B', 'two')} and {_link('C', 'three')} end.</p>"
    assert _spans(html) == [("one", "A"), ("two", "B")]


def test_a_link_in_a_quoted_paragraph_keeps_its_span() -> None:
    html = f"<blockquote><p>The {_link('Cat', 'cat')} sat on the mat.</p></blockquote>"
    assert link_spans(parse_sections(LEAD, html).chunks[1]) == [("cat", "Cat")]
