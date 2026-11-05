"""Paragraphs never merge across a dropped list, table, code block or display equation."""

from __future__ import annotations

import pytest

from tests.factories.parsed import LEAD, parse_sections, texts

BEFORE = "<p>The first claim is stated here and it is complete.</p>"
AFTER = "<p>The second claim is stated there and it is complete.</p>"
PROSE_SECTION = "<p>" + "A full sentence of ordinary prose. " * 8 + "</p>"

BLOCKS = {
    "list": "<ul><li>kept out</li></ul>",
    "definition list": "<dl><dd>x = y</dd></dl>",
    "table": "<table><tr><td>cell</td></tr></table>",
    "code block": "<pre>1 let x = 1\n2 return x</pre>",
}


@pytest.mark.parametrize("block", BLOCKS.values(), ids=BLOCKS.keys())
def test_two_short_paragraphs_around_a_dropped_block_stay_two_chunks(block: str) -> None:
    article = parse_sections(LEAD, BEFORE + block + AFTER)
    assert texts(article, "prose")[1:] == [
        "The first claim is stated here and it is complete.",
        "The second claim is stated there and it is complete.",
    ]


def test_paragraphs_with_nothing_between_them_still_merge() -> None:
    article = parse_sections(LEAD, BEFORE + AFTER)
    assert texts(article, "prose")[1:] == [
        "The first claim is stated here and it is complete. "
        "The second claim is stated there and it is complete."
    ]


def test_a_figure_between_paragraphs_is_not_a_boundary() -> None:
    article = parse_sections(LEAD, BEFORE + "<figure><img alt='x'/></figure>" + AFTER)
    assert len(texts(article, "prose")) == 2


def test_code_block_is_counted_with_the_lists_left_out() -> None:
    article = parse_sections(LEAD, PROSE_SECTION + BLOCKS["code block"] + AFTER)
    section = article.sections[1]
    assert section.dropped_lists == 1
    assert section.dropped_non_prose is True
    assert all("let x" not in text for text in texts(article))


def test_list_lead_in_is_dropped_and_the_text_after_the_list_starts_a_chunk() -> None:
    article = parse_sections(
        LEAD, "<p>The plan has two parts:</p><ul><li>a</li><li>b</li></ul>" + AFTER
    )
    assert texts(article, "prose")[1:] == ["The second claim is stated there and it is complete."]


def test_a_colon_paragraph_with_nothing_after_it_is_a_fragment_not_an_intro() -> None:
    article = parse_sections(LEAD, BEFORE + "<p>And the list would go here:</p>")
    assert texts(article, "prose")[1:] == ["The first claim is stated here and it is complete."]


def test_a_blockquote_holding_only_its_citation_adds_nothing() -> None:
    quote = "<blockquote><div class='templatequotecite'>Dunn 2003</div></blockquote>"
    article = parse_sections(LEAD, BEFORE + quote)
    assert texts(article)[1:] == ["The first claim is stated here and it is complete."]
