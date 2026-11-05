"""Infobox key facts, wikitable chunks and drop counts on a synthetic revision."""

from __future__ import annotations

import pytest

from tests.factories.parsed import CITATION_ID, REV_ID
from tests.support.constants import SYNTHETIC_DIR
from wke.core.models import ChunkKind
from wke.core.parse import ParsedArticle, ParsedSection, parse_html


@pytest.fixture(scope="module")
def article() -> ParsedArticle:
    html = (SYNTHETIC_DIR / "infobox_tables.html").read_text(encoding="utf-8")
    return parse_html(html, REV_ID, CITATION_ID)


def _chunk(article: ParsedArticle, kind: ChunkKind, section: str) -> str:
    prefix = f"{REV_ID}:{section}:"
    return next(c.text for c in article.chunks if c.kind == kind and c.id.startswith(prefix))


def _section(article: ParsedArticle, section_id: str) -> ParsedSection:
    return next(s for s in article.sections if s.id == section_id)


def test_infobox_becomes_one_facts_chunk_after_the_lead_prose(article: ParsedArticle) -> None:
    lead = _section(article, "0")
    kinds = [c.kind for c in article.chunks if c.id in lead.chunk_ids]
    assert kinds == ["prose", "facts"]
    facts = _chunk(article, "facts", "0")
    assert facts.splitlines()[0] == "Born: Ada Example, 1 January 1900, London, England"


def test_facts_skip_image_map_signature_and_empty_rows_and_cap_at_twelve(
    article: ParsedArticle,
) -> None:
    lines = _chunk(article, "facts", "0").splitlines()
    labels = [line.split(":")[0] for line in lines]
    assert "Signature" not in labels and "Map" not in labels and "Empty" not in labels
    assert "Ada Example" not in labels
    assert len(lines) == 12
    assert "Known for: Engines, Poems" in lines
    assert all("[" not in line for line in lines)


def test_table_with_caption_keeps_header_and_cells_verbatim(article: ParsedArticle) -> None:
    lines = _chunk(article, "table", "1").splitlines()
    assert lines[0] == "Selected works"
    assert lines[1] == "| Year | Title | Pages |"
    assert lines[2] == "| --- | --- | --- |"
    assert lines[3] == "| 1840 | Notes | 52 |"
    assert lines[4] == "| 1843 | Sketch \\| draft | 30 |"
    assert len(lines) == 5


def test_uncaptioned_table_is_kept_and_a_headerless_one_is_counted(
    article: ParsedArticle,
) -> None:
    works = _section(article, "1")
    tables = [c for c in article.chunks if c.kind == "table" and c.id in works.chunk_ids]
    assert [t.text.splitlines()[0] for t in tables] == ["Selected works", "Works"]
    assert works.dropped_tables == 1
    assert works.dropped_lists == 1
    assert works.dropped_non_prose is True


def test_long_table_keeps_every_row_in_the_chunk_text(article: ParsedArticle) -> None:
    lines = _chunk(article, "table", "2").splitlines()
    assert lines[0] == "Medal table"
    data = lines[3:]
    assert len(data) == 14
    assert data[9] == "| 10 | J | 10 |"
    assert data[-1] == "| Total |  | 91 |"
    assert not lines[-1].startswith("(")


def test_table_only_section_carries_its_chunk_and_no_drops(article: ParsedArticle) -> None:
    medals = _section(article, "2")
    assert [c.kind for c in article.chunks if c.id in medals.chunk_ids] == ["table"]
    assert medals.dropped_non_prose is False


def test_navigation_phrases_and_fragments_never_reach_a_passage(article: ParsedArticle) -> None:
    nav = _section(article, "3")
    texts = [c.text for c in article.chunks if c.id in nav.chunk_ids]
    assert texts == ["A plain sentence stays here.", "Another plain sentence stays too."]
    joined = " ".join(texts)
    for phrase in ("See also", "This article is about", "see the", "without an end"):
        assert phrase not in joined
    assert _section(article, "3").dropped_tables == 0


def test_table_est_tokens_count_the_emitted_text(article: ParsedArticle) -> None:
    for chunk in article.chunks:
        if chunk.kind != "prose":
            assert chunk.est_tokens == -(-len(chunk.text) // 4)
