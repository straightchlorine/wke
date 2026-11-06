"""Tests for wke.offline.reparse: packing a stored dossier and re-parsing its HTML."""

from __future__ import annotations

import pytest

from tests.factories.dossier import FACTORY_RELATED_TITLE, make_fixture_dossier, make_summary
from tests.support.wikimedia import WmFixtures
from wke.core.citations import seed_pin
from wke.core.models import Dossier, Section
from wke.core.render.labels import SUMMARY_LABEL
from wke.jobs.build.summarize import summary_input
from wke.offline.reparse import reparse, view_and_markdown

# A summary sentence the source check rejects: neither number is in the section.
UNSUPPORTED = "It happened in 1987 and 4242 people attended."


@pytest.fixture
def html(wm_fixtures: WmFixtures) -> str:
    return wm_fixtures.text("parsoid.html")


@pytest.fixture
def parsed(html: str) -> Dossier:
    """The factory dossier re-parsed from the recorded article: real section ids."""
    return reparse(make_fixture_dossier(), html)


def _prose_sections(dossier: Dossier) -> list[Section]:
    """Sections with a heading and at least one prose passage."""
    kind = {c.id: c.kind for c in dossier.chunks}
    return [
        s
        for s in dossier.sections
        if s.heading_path and any(kind[c] == "prose" for c in s.chunk_ids)
    ]


def _prose_section(dossier: Dossier) -> Section:
    return _prose_sections(dossier)[0]


def _first_sentence(dossier: Dossier, section: Section) -> str:
    _, ids = summary_input(section, dossier.chunks)
    chunk = next(c for c in dossier.chunks if c.id == ids[0])
    return chunk.text.split(". ")[0] + "."


def test_view_and_markdown_packs_to_the_budget_and_renders():
    dossier = make_fixture_dossier()
    view, markdown = view_and_markdown(dossier, 2000)
    assert view.budget.requested == 2000
    assert view.budget.used_est_tokens <= 2000
    assert dossier.topic.title in markdown


def test_view_and_markdown_shows_summaries_only_when_asked():
    dossier = make_fixture_dossier()
    text = next(s.summary.text for s in dossier.sections if s.summary)
    with_summaries = view_and_markdown(dossier, 8000, True)[1]
    assert SUMMARY_LABEL in with_summaries
    assert text in with_summaries
    without_summaries = view_and_markdown(dossier, 8000)[1]
    assert text not in without_summaries
    # The note for a section that has none is written only when summaries were asked for.
    assert "Summary pending" in with_summaries
    assert "Summary pending" not in without_summaries


def test_view_and_markdown_scores_importance_of_an_older_dossier_in_place():
    dossier = make_fixture_dossier()
    for section in dossier.sections:
        section.importance = 0.0
    view_and_markdown(dossier, 8000)
    assert all(section.importance > 0 for section in dossier.sections)


def test_reparse_rebuilds_sections_and_chunks_from_the_html(parsed: Dossier):
    original = make_fixture_dossier()
    assert len(parsed.sections) > len(original.sections)
    assert len(parsed.chunks) > len(original.chunks)
    assert Dossier.model_validate(parsed.model_dump()) == parsed
    assert parsed.id == original.id


def test_reparse_keeps_the_seed_and_related_citations_first(parsed: Dossier):
    original = make_fixture_dossier()
    assert parsed.citations[0].id == "c1"
    assert parsed.citations[0].role == "seed"
    assert parsed.citations[0].pin == seed_pin(original)
    assert parsed.citations[1].role == "related"
    assert parsed.citations[1].pin.title == FACTORY_RELATED_TITLE
    assert {c.role for c in parsed.citations[2:]} == {"seed"}


def test_reparse_takes_prose_relevance_from_the_same_text_then_head_then_mean(
    parsed: Dossier, html: str
):
    prose = [c for c in parsed.chunks if c.kind == "prose"]
    exact, head, dropped = prose[0], prose[1], prose[2]
    facts = {c.id: c.relevance for c in parsed.chunks if c.kind != "prose"}
    for chunk in parsed.chunks:
        chunk.relevance = 0.5
    exact.relevance = 0.7
    head.relevance = 0.3
    head.text = head.text[:60] + " (edited tail)"
    stored = parsed.model_copy(update={"chunks": [c for c in parsed.chunks if c is not dropped]})

    rebuilt = {c.id: c for c in reparse(stored, html).chunks}

    assert rebuilt[exact.id].relevance == 0.7
    assert rebuilt[head.id].relevance == 0.3
    # The stored relevances average to 0.5, the value an unknown text falls back to.
    assert rebuilt[dropped.id].relevance == pytest.approx(0.5)
    # Facts and tables keep the parser's own relevance rule.
    assert {cid: rebuilt[cid].relevance for cid in facts} == facts


def test_reparse_keeps_a_summary_that_passes_the_source_check_on_the_new_input(
    parsed: Dossier, html: str
):
    section = _prose_section(parsed)
    section.summary = make_summary(_first_sentence(parsed, section))
    section.summary_state = "done"

    rebuilt = reparse(parsed, html)
    again = next(s for s in rebuilt.sections if s.id == section.id)

    _, input_ids = summary_input(again, rebuilt.chunks)
    assert again.summary_state == "done"
    assert again.summary is not None
    assert again.summary.text == section.summary.text
    assert again.summary.input_chunk_ids == input_ids
    assert again.summary.citation_id == again.citation_id


@pytest.mark.parametrize(
    ("text", "reason_part"),
    [
        (UNSUPPORTED, "1987"),
        (f"{FACTORY_RELATED_TITLE} is discussed in this section.", "article"),
    ],
)
def test_reparse_withholds_a_summary_the_source_check_rejects(
    parsed: Dossier, html: str, text: str, reason_part: str
):
    section = _prose_section(parsed)
    section.summary = make_summary(text)
    section.summary_state = "done"

    again = reparse(parsed, html)
    section = next(s for s in again.sections if s.id == section.id)

    assert section.summary is None
    assert section.summary_state == "withheld"
    assert section.withheld_reason is not None and reason_part in section.withheld_reason
    assert [s.summary_state for s in again.sections].count("withheld") == 1


def test_reparse_lets_a_summary_use_a_number_from_its_section_heading(parsed: Dossier, html: str):
    section = next(
        s for s in _prose_sections(parsed) if any(ch.isdigit() for ch in s.heading_path[-1])
    )
    section.summary = make_summary(f"This part is about {section.heading_path[-1].lower()}.")
    section.summary_state = "done"

    again = next(s for s in reparse(parsed, html).sections if s.id == section.id)

    assert again.summary_state == "done"


def test_reparse_drops_summaries_that_were_never_done(parsed: Dossier, html: str):
    section = _prose_section(parsed)
    section.summary = make_summary(_first_sentence(parsed, section))
    section.summary_state = "unavailable"

    again = next(s for s in reparse(parsed, html).sections if s.id == section.id)

    assert again.summary is None
    assert again.summary_state == "pending"
