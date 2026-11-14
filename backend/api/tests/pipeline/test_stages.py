"""Steps between fetch and persist: the lead sent to wke-ml, its answer and the partial dossier."""

from __future__ import annotations

import pytest

from tests.factories.dossier import make_pin
from tests.support.constants import FIXTURE_PAGE_ID, FIXTURE_TITLE, PIPELINE_VERSION
from tests.support.jobs import make_job
from wke.core.models import Chunk, ChunkKind, Citation
from wke.core.parse import ParsedArticle, ParsedSection
from wke.jobs.build.progress import bump_done, set_total
from wke.jobs.build.stages import Fetched, apply_analysis, assemble_dossier, lead_text


def _chunk(cid: str, path: list[str], text: str = "x", kind: ChunkKind = "prose") -> Chunk:
    return Chunk(
        id=cid,
        citation_id="c1",
        heading_path=path,
        order=0,
        text=text,
        est_tokens=1,
        relevance=0.3,
        kind=kind,
    )


@pytest.mark.parametrize(
    ("chunks", "expected"),
    [
        pytest.param(
            [
                _chunk("a", [], "Lead one."),
                _chunk("b", ["History"], "Body."),
                _chunk("c", [], "Two."),
            ],
            "Lead one. Two.",
            id="the lead chunks joined",
        ),
        pytest.param(
            [_chunk("b", ["History"], "Body."), _chunk("c", ["Legacy"], "Later.")],
            "Body.",
            id="the first prose chunk when there is no lead",
        ),
        pytest.param([], "", id="empty without prose"),
    ],
)
def test_lead_text(chunks: list[Chunk], expected: str) -> None:
    assert lead_text(chunks) == expected


def test_analysis_sets_relevance_and_cluster_by_chunk_id_and_keeps_unscored_chunks() -> None:
    scored, unscored = _chunk("a", []), _chunk("b", [])
    analysis = {
        "relevance": {"a": 0.9},
        "cluster_ids": {"a": 2},
        "edges": [{"source": 1, "target": 2, "weight": 0.5}],
    }

    edges = apply_analysis([scored, unscored], analysis)

    assert (scored.relevance, scored.cluster_id) == (0.9, 2)
    assert (unscored.relevance, unscored.cluster_id) == (0.3, None)
    assert [(e.source, e.target, e.weight) for e in edges] == [(1, 2, 0.5)]


@pytest.mark.parametrize("truncated", [False, True])
def test_partial_dossier_carries_the_parse_truncation_and_the_selected_summaries(
    truncated: bool,
) -> None:
    chunks = [_chunk("p0", [], "Lead."), _chunk("p1", ["History"], "Body " * 40)]
    parsed = ParsedArticle(
        sections=[
            ParsedSection(
                id="s0", anchor="s0", heading="", heading_path=[], order=0, chunk_ids=["p0"]
            ),
            ParsedSection(
                id="s1", anchor="s1", heading="History", heading_path=[], order=1, chunk_ids=["p1"]
            ),
        ],
        chunks=chunks,
        truncated=truncated,
    )
    seed = Citation(id="c1", pin=make_pin(FIXTURE_PAGE_ID, FIXTURE_TITLE, 1), role="seed")
    fetched = Fetched(
        dossier_id=f"{FIXTURE_PAGE_ID}@1:abc123456789",
        parsed=parsed,
        seed_citation=seed,
        related_citations=[],
        related_nodes=[],
        related_leads=[],
        section_citations=[],
        citation_of={},
    )

    dossier, selected = assemble_dossier(
        make_job(rev_id=1),
        fetched,
        {},
        pipeline_version=PIPELINE_VERSION,
        summary_sections=8,
        build_seconds=1.5,
    )

    assert dossier.build.truncated is truncated
    assert (dossier.build.state, dossier.build.analysis) == ("partial", "ml")
    assert selected == ["s1"]
    assert dossier.build.summaries_total == 1
    assert dossier.build.stage_seconds == {"build": 1.5}


def test_progress_never_passes_its_total() -> None:
    job = make_job()
    set_total(job, 2)
    for _ in range(4):
        bump_done(job)
    assert (job.progress.done, job.progress.total) == (2, 2)
