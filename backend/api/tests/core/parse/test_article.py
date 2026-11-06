"""Parser properties that hold for any article, checked on the recorded Parsoid fixture."""

from __future__ import annotations

import re

import pytest
from selectolax.lexbor import LexborHTMLParser

from tests.factories.parsed import CITATION_ID
from tests.support.wikimedia import WmFixtures
from wke.core.parse import ParsedArticle, parse_html
from wke.core.parse.chunks import (
    INTRO_MERGE_MAX_TOKENS,
    MERGE_THRESHOLD_TOKENS,
    SPLIT_THRESHOLD_TOKENS,
)
from wke.core.parse.furniture import DROP_SELECTOR
from wke.core.parse.pronunciation import drop_pronunciation_spans, tidy_pronunciation
from wke.core.parse.sections import BOILERPLATE_ANCHORS, HEADING_SELECTOR
from wke.core.text.clean import clean_text
from wke.core.text.sentences import split_sentences


@pytest.fixture
def article(wm_fixtures: WmFixtures) -> ParsedArticle:
    html = wm_fixtures.text("parsoid.html")
    return parse_html(html, rev_id=wm_fixtures.revision_id, citation_id=CITATION_ID)


def test_boilerplate_dropped(article: ParsedArticle) -> None:
    anchors = {section.anchor for section in article.sections}
    assert anchors.isdisjoint(BOILERPLATE_ANCHORS)


def test_no_prose_chunk_over_the_split_threshold(article: ParsedArticle) -> None:
    prose = [chunk for chunk in article.chunks if chunk.kind == "prose"]
    assert all(chunk.est_tokens <= INTRO_MERGE_MAX_TOKENS for chunk in prose)
    # In this article only an introduction kept with its quotation passes the threshold.
    assert all(chunk.est_tokens <= SPLIT_THRESHOLD_TOKENS or ":" in chunk.text for chunk in prose)


def test_no_adjacent_chunks_could_have_merged(article: ParsedArticle) -> None:
    by_id = {chunk.id: chunk for chunk in article.chunks}
    for section in article.sections:
        for left_id, right_id in zip(section.chunk_ids, section.chunk_ids[1:]):
            left, right = by_id[left_id], by_id[right_id]
            mergeable = (
                left.est_tokens < MERGE_THRESHOLD_TOKENS
                and left.est_tokens + right.est_tokens <= SPLIT_THRESHOLD_TOKENS
            )
            assert not mergeable, f"{left_id} and {right_id} should have merged"


def test_no_loss_no_invention(article: ParsedArticle, wm_fixtures: WmFixtures) -> None:
    expected = _reconstruct_kept_text(wm_fixtures.text("parsoid.html"))
    prose = [chunk.text for chunk in article.chunks if chunk.kind == "prose"]
    actual = re.sub(r"\s+", " ", " ".join(prose)).strip()
    # Nothing is invented: every kept sentence is in the source text.
    assert all(sentence in expected for sentence in split_sentences(actual))
    # Nothing is lost beyond the odd trailing piece without a sentence end.
    assert 0 <= len(expected) - len(actual) < len(expected) * 0.01


def _reconstruct_kept_text(html: str) -> str:
    """Independently rebuild the expected text of every kept paragraph.

    Mirrors the parser's drop rules (drop selector, boilerplate anchors)
    but walks the tree itself rather than calling the parser's own
    section-walking helpers, so this is not just re-running parse_html.
    """
    tree = LexborHTMLParser(html)
    for node in tree.css(DROP_SELECTOR):
        node.decompose()
    for table in tree.css("table"):
        table.decompose()
    drop_pronunciation_spans(tree)

    body = tree.body
    assert body is not None

    for section in tree.css("section[data-mw-section-id]"):
        heading_node = section.css_first(HEADING_SELECTOR)
        anchor = heading_node.attributes.get("id") if heading_node else None
        if anchor in BOILERPLATE_ANCHORS:
            section.decompose()

    texts = [
        clean_text(tidy_pronunciation(clean_text(p.text(separator="", strip=False))))
        for p in tree.css("p")
        if clean_text(p.text(separator="", strip=False))
    ]
    return re.sub(r"\s+", " ", " ".join(texts)).strip()
