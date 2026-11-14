"""Relevance of non-prose chunks, section importance and the choice of sections to summarise."""

from __future__ import annotations

import pytest

from wke.core import pack
from wke.core.models import Chunk, ChunkKind, Section
from wke.core.parse import ParsedArticle, ParsedSection
from wke.jobs.build.sections import non_prose_relevance, set_importance
from wke.jobs.build.select import select_summary_sections


def _importance_fixture() -> tuple[list[Section], list[Chunk]]:
    def section(sid: str, chunk_ids: list[str], path: list[str]):
        return Section(
            id=sid,
            label=sid,
            label_source="heading",
            chunk_ids=chunk_ids,
            heading_path=path,
            summary_state="pending" if chunk_ids else "no_prose",
        )

    def chunk(cid: str, order: int, tokens: int, relevance: float):
        return Chunk(
            id=cid,
            citation_id="c1",
            heading_path=[],
            order=order,
            text="x",
            est_tokens=tokens,
            relevance=relevance,
        )

    sections = [
        section("lead", ["l0"], []),
        section("a", [], ["A"]),
        section("b", ["b0"], ["B"]),
        section("c", ["c0", "c1"], ["C"]),
        section("d", [], ["D"]),
    ]
    chunks = [
        chunk("l0", 0, 100, 1.0),
        chunk("b0", 1, 50, 0.2),
        chunk("c0", 2, 100, 0.6),
        chunk("c1", 3, 100, 0.6),
    ]
    return sections, chunks


def test_set_importance_stores_the_packer_score_on_each_section() -> None:
    sections, chunks = _importance_fixture()
    set_importance(sections, chunks)
    scores = pack.section_importance(sections, chunks)
    assert {s.id: s.importance for s in sections} == pytest.approx(scores)
    assert next(s for s in sections if s.id == "a").importance == 0.0
    assert (
        Section(
            id="x", label="x", label_source="heading", chunk_ids=[], summary_state="no_prose"
        ).importance
        == 0.0
    )


def test_select_summary_sections_ranks_by_importance_and_skips_lead_and_no_prose() -> None:
    sections, chunks = _importance_fixture()
    assert select_summary_sections(sections, chunks, 8) == ["c", "b"]


def test_select_summary_sections_count_follows_article_size_between_3_and_cap() -> None:
    def make(n: int):
        sections = [
            Section(
                id=f"s{i}",
                label=f"s{i}",
                label_source="heading",
                chunk_ids=[f"s{i}:0"],
                heading_path=[f"S{i}"],
                summary_state="pending",
            )
            for i in range(12)
        ]
        chunks = [
            Chunk(
                id=f"s{i}:0",
                citation_id="c1",
                heading_path=[f"S{i}"],
                order=i,
                text="x",
                est_tokens=n,
                relevance=0.5,
            )
            for i in range(12)
        ]
        return sections, chunks

    small = select_summary_sections(*make(100), 8)
    assert len(small) == 3
    assert len(select_summary_sections(*make(1000), 8)) == 6
    assert len(select_summary_sections(*make(5000), 8)) == 8
    assert len(select_summary_sections(*make(5000), 4)) == 4


def _kind_chunk(cid: str, kind: ChunkKind, tokens: int = 10, relevance: float = 0.0) -> Chunk:
    return Chunk(
        id=cid,
        citation_id="c1",
        heading_path=[],
        order=0,
        text="x",
        est_tokens=tokens,
        relevance=relevance,
        kind=kind,
    )


def test_non_prose_chunks_take_their_relevance_from_the_section() -> None:
    chunks = [
        _kind_chunk("p1", "prose", tokens=100, relevance=1.0),
        _kind_chunk("p2", "prose", tokens=300, relevance=0.2),
        _kind_chunk("facts", "facts"),
        _kind_chunk("table", "table"),
        _kind_chunk("list", "list"),
        _kind_chunk("lone-table", "table"),
    ]
    parsed = ParsedArticle(
        sections=[
            ParsedSection(
                id="a",
                anchor="a",
                heading="A",
                heading_path=[],
                order=0,
                chunk_ids=["p1", "p2", "facts", "table", "list"],
            ),
            ParsedSection(
                id="b", anchor="b", heading="B", heading_path=[], order=1, chunk_ids=["lone-table"]
            ),
        ],
        chunks=chunks,
        truncated=False,
    )

    non_prose_relevance(chunks, parsed)

    relevance = {c.id: c.relevance for c in chunks}
    # The mean of the section's prose, weighted by tokens: (100 * 1.0 + 300 * 0.2) / 400.
    assert relevance == pytest.approx(
        {"p1": 1.0, "p2": 0.2, "facts": 1.0, "table": 0.4, "list": 0.4, "lone-table": 0.5}
    )
