"""Section labels and the structural fallback's merge of nested sections."""

from __future__ import annotations

import pytest

from tests.factories.dossier import make_pin
from tests.support.builds import make_queue
from tests.support.constants import FIXTURE_PAGE_ID, FIXTURE_TITLE, PIPELINE_VERSION
from tests.support.jobs import make_job
from wke.clients.redis import RedisClient
from wke.core import keys
from wke.core.models import Chunk, Citation, Dossier
from wke.core.parse import ParsedArticle, ParsedSection
from wke.jobs.build.sections import label_sections
from wke.jobs.build.structural import persist_structural

Spec = tuple[str, str, list[str], list[str]]


def _sections(*specs: Spec) -> list[ParsedSection]:
    """Build ParsedSections from (id, heading, heading_path, chunk_ids) tuples."""
    return [
        ParsedSection(
            id=section_id,
            anchor=section_id,
            heading=heading,
            heading_path=heading_path,
            chunk_ids=chunk_ids,
            order=order,
        )
        for order, (section_id, heading, heading_path, chunk_ids) in enumerate(specs)
    ]


LABEL_CASES: dict[str, tuple[list[Spec], list[str]]] = {
    "duplicate top-level headings take an ordinal": (
        [("s0", "", [], ["c0"]), ("s1", "History", [], ["c1"]), ("s2", "History", [], ["c2"])],
        [FIXTURE_TITLE, "History", "History (2)"],
    ),
    "duplicates under one ancestor take an ordinal after the ancestor": (
        [("s0", "Legacy", ["Impact"], ["c0"]), ("s1", "Legacy", ["Impact"], ["c1"])],
        ["Legacy (Impact)", "Legacy (Impact) (2)"],
    ),
    "duplicates under different ancestors take the ancestor": (
        [("s0", "Legacy", ["Early life"], ["c0"]), ("s1", "Legacy", ["Career"], ["c1"])],
        ["Legacy (Early life)", "Legacy (Career)"],
    ),
    "a unique heading stays as it is": (
        [("s0", "Legacy", ["Early life"], ["c0"]), ("s1", "Career", [], ["c1"])],
        ["Legacy", "Career"],
    ),
}


@pytest.mark.parametrize(("specs", "expected"), list(LABEL_CASES.values()), ids=list(LABEL_CASES))
def test_section_labels_stay_distinct(specs: list[Spec], expected: list[str]) -> None:
    labelled = label_sections(_sections(*specs), FIXTURE_TITLE)

    labels = [label for _, label, _ in labelled]
    assert labels == expected
    assert len(set(labels)) == len(labels)


def test_label_source_follows_the_heading_and_the_requested_fallback_source() -> None:
    sections = _sections(("s0", "", [], ["c0"]), ("s1", "History", [], ["c1"]))

    assert [source for _, _, source in label_sections(sections, FIXTURE_TITLE)] == [
        "article_title",
        "heading",
    ]
    structural = label_sections(sections, FIXTURE_TITLE, heading_label_source="structural")
    assert [source for _, _, source in structural] == ["article_title", "structural"]


async def test_persist_structural_merges_nested_sections_into_the_preceding_top_level_section(
    redis_client: RedisClient,
) -> None:
    """Two top-level "History" sections each with a nested child.

    A nested section joins the top-level section that precedes it in document
    order, not the one whose heading text it names, so each duplicate keeps
    its own child chunks.
    """
    parsed = ParsedArticle(
        sections=_sections(
            ("s0", "", [], ["c0"]),
            ("s1", "History", [], ["c1"]),
            ("s1a", "Details", ["History"], ["c1a"]),
            ("s1b", "More", ["History"], ["c1b"]),
            ("s2", "History", [], ["c2"]),
            ("s2a", "Details", ["History"], ["c2a"]),
        ),
        chunks=[
            Chunk(
                id=cid,
                citation_id="c1",
                heading_path=[],
                order=i,
                text="x",
                est_tokens=1,
                relevance=1.0,
            )
            for i, cid in enumerate(["c0", "c1", "c1a", "c1b", "c2", "c2a"])
        ],
        truncated=True,
    )
    for section, lists, tables in zip(parsed.sections, [0, 1, 2, 4, 0, 0], [0, 0, 1, 2, 0, 0]):
        section.dropped_lists, section.dropped_tables = lists, tables
    seed_citation = Citation(
        id="c1", pin=make_pin(FIXTURE_PAGE_ID, FIXTURE_TITLE, 1), role="seed", anchor=None, url=None
    )
    job = make_job(rev_id=1, title=None, status="running", stage="parse")
    queue = make_queue(redis_client)
    await queue.set_job(job)

    await persist_structural(
        redis=redis_client,
        job=job,
        job_queue=queue,
        pipeline_version=PIPELINE_VERSION,
        page_id=FIXTURE_PAGE_ID,
        rev_id=1,
        title=FIXTURE_TITLE,
        dossier_id=f"{FIXTURE_PAGE_ID}@1:abc123456789",
        seed_citation=seed_citation,
        related_citations=[],
        section_citations=[],
        citation_of={},
        related_nodes=[],
        parsed=parsed,
        stage_seconds={},
    )

    raw = await redis_client.get(keys.dossier(FIXTURE_PAGE_ID, 1, PIPELINE_VERSION))
    assert raw is not None
    dossier = Dossier.model_validate_json(raw)
    by_id = {s.id: s for s in dossier.sections}
    assert sorted(by_id) == ["s0", "s1", "s2"]
    assert by_id["s1"].chunk_ids == ["c1", "c1a", "c1b"]
    assert by_id["s2"].chunk_ids == ["c2", "c2a"]
    assert by_id["s1"].label == "History"
    assert by_id["s2"].label == "History (2)"
    assert by_id["s1"].label_source == "structural"
    assert (by_id["s1"].dropped_lists, by_id["s1"].dropped_tables) == (7, 3)
    assert by_id["s1"].dropped_non_prose is True
    assert (by_id["s2"].dropped_lists, by_id["s2"].dropped_tables) == (0, 0)
    assert by_id["s2"].dropped_non_prose is False
    assert dossier.build.truncated is True
    assert {c.id: c.relevance for c in dossier.chunks} == pytest.approx(
        {"c0": 1.0, "c1": 0.5, "c1a": 1 / 3, "c1b": 0.25, "c2": 0.2, "c2a": 1 / 6}
    )
