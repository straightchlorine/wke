"""The budget line, the flat-budget notice, the Left out cap and the summary notices."""

from __future__ import annotations

from tests.factories.dossier import (
    make_fixture_dossier,
    make_fixture_view,
    make_freshness,
    make_links,
)
from tests.factories.synthetic import dossier_of, prose, section, sized
from wke.core import render
from wke.core.models import Dossier, DossierView, Section
from wke.core.models.budgets import BudgetTokens
from wke.core.render.budget import FLAT_NOTICE
from wke.core.render.header import PROVENANCE_NOTICE

CUT_NOTE = "more passage"


def _markdown(dossier: Dossier, budget: BudgetTokens = 32000, summaries: bool = False) -> str:
    view = render.build_view(
        dossier, budget, make_freshness(dossier), make_links(dossier), summaries
    )
    return render.render_markdown(view, summaries)


def _small() -> Dossier:
    chunks = [
        prose("l0", [], 0, "Alpha builds boats.", 1.0),
        prose("a:0", ["A"], 10, "Harbour rules apply to every boat."),
    ]
    return dossier_of(
        [section("s0", [], ["l0"]), section("a", ["A"], ["a:0"])],
        chunks,
    )


def test_the_budget_line_counts_the_passages_in_one_sentence() -> None:
    text = _markdown(_small())
    assert "\nBudget 32,000 tokens: all 2 passages\n" in text


def test_a_single_passage_reads_the_1_passage() -> None:
    dossier = dossier_of([section("s0", [], ["l0"])], [prose("l0", [], 0, "Alpha builds boats.")])
    assert "\nBudget 32,000 tokens: the 1 passage\n" in _markdown(dossier)


def test_a_cut_lead_is_named_in_the_opening_note_not_in_a_section_note() -> None:
    lead = prose("l0", [], 0, "Alpha builds boats on the river. " * 400, 1.0)
    text = _markdown(dossier_of([section("s0", [], ["l0"])], [lead]), 2000)
    line = next(ln for ln in text.splitlines() if ln.startswith("Opening passages"))
    assert line.endswith("; some openings are shortened at a sentence end.")
    assert "shortened" not in next(ln for ln in text.splitlines() if ln.startswith("Budget "))
    assert "first passage is cut" not in text


def test_passages_left_out_are_counted_on_the_budget_line_and_the_opening_note() -> None:
    ids = [f"a:{n}" for n in range(30)]
    chunks = [prose("l0", [], 0, "Alpha builds boats.", 1.0)]
    chunks += [
        prose(cid, ["A"], 10 + n, sized(f"Rule{n} applies.", 150)) for n, cid in enumerate(ids)
    ]
    text = _markdown(
        dossier_of([section("s0", [], ["l0"]), section("a", ["A"], ids)], chunks), 2000
    )
    line = next(ln for ln in text.splitlines() if ln.startswith("Budget "))
    assert " of 31 passages" in line and "sections" not in line
    note = next(ln for ln in text.splitlines() if ln.startswith("Opening passages are shown for"))
    assert note.endswith(" passages are left out at this budget.")
    assert CUT_NOTE not in text


def test_one_passage_left_out_reads_is_not_are() -> None:
    chunks = [
        prose("l0", [], 0, "Alpha builds boats.", 1.0),
        prose("a:0", ["A"], 10, "Harbour rules apply to every boat."),
        prose("b:0", ["B"], 11, sized("Quay rules began.", 2100)),
    ]
    sections = [
        section("s0", [], ["l0"]),
        section("a", ["A"], ["a:0"]),
        section("b", ["B"], ["b:0"]),
    ]
    text = _markdown(dossier_of(sections, chunks), 2000)
    assert (
        "Opening passages are shown for 2 sections; 1 passage is left out at this budget." in text
    )


def test_the_flat_notice_appears_only_when_nothing_of_the_article_is_left_out() -> None:
    assert FLAT_NOTICE in _markdown(_small())
    dropped = _small()
    sections = [s.model_copy(update={"dropped_tables": 1}) for s in dropped.sections]
    assert FLAT_NOTICE not in _markdown(dropped.model_copy(update={"sections": sections}))
    big = [prose("l0", [], 0, "Alpha builds boats.", 1.0)]
    big += [prose(f"a:{n}", ["A"], 10 + n, sized(f"Rule{n} applies.", 400)) for n in range(12)]
    many = dossier_of(
        [section("s0", [], ["l0"]), section("a", ["A"], [c.id for c in big[1:]])], big
    )
    assert FLAT_NOTICE not in _markdown(many, 2000)


def test_left_out_names_the_first_eight_in_document_order_and_counts_the_rest() -> None:
    chunks = [prose("l0", [], 0, "Alpha builds boats.", 1.0)]
    sections = [section("s0", [], ["l0"])]
    for n in range(12):
        chunks.append(prose(f"x{n}:0", [f"X{n}"], 10 + n, sized(f"Topic{n} began.", 2100)))
        named = section(f"x{n}", [f"X{n}"], [f"x{n}:0"], label=f"Part {n:02d}")
        sections.append(named.model_copy(update={"importance": round(0.1 + 0.05 * n, 2)}))
    text = _markdown(dossier_of(sections, chunks), 2000)
    line = next(ln for ln in text.splitlines() if ln.startswith("Left out:"))
    expected = ", ".join(f"Part {n:02d}" for n in range(8))
    assert line == f"Left out: 12 sections left out at this budget: {expected} and 4 more sections"


def test_the_cap_runs_across_both_groups_and_a_single_leftover_is_not_pluralised() -> None:
    chunks = [prose("l0", [], 0, "Alpha builds boats.", 1.0)]
    sections = [section("s0", [], ["l0"])]
    for n in range(7):
        sections.append(section(f"e{n}", [f"E{n}"], [], label=f"Empty {n}"))
    for n in range(2):
        chunks.append(prose(f"x{n}:0", [f"X{n}"], 10 + n, sized(f"Topic{n} began.", 2100)))
        sections.append(section(f"x{n}", [f"X{n}"], [f"x{n}:0"], label=f"Part {n}"))
    text = _markdown(dossier_of(sections, chunks), 2000)
    line = next(ln for ln in text.splitlines() if ln.startswith("Left out:"))
    empties = ", ".join(f"Empty {n}" for n in range(7))
    assert line == (
        f"Left out: 7 sections without prose: {empties}; "
        "2 sections left out at this budget: Part 0 and 1 more section"
    )


def test_the_provenance_notice_does_not_claim_sections_say_so() -> None:
    assert "says so" not in PROVENANCE_NOTICE and "say so" not in PROVENANCE_NOTICE
    assert PROVENANCE_NOTICE in _markdown(_small())


def _fixture_with_states() -> Dossier:
    dossier = make_fixture_dossier()
    states = {
        "s2": ("withheld", "the text does not end at a sentence end"),
        "s3": ("skipped", None),
    }
    sections: list[Section] = []
    for s in dossier.sections:
        if s.id in states:
            state, reason = states[s.id]
            s = s.model_copy(
                update={"summary": None, "summary_state": state, "withheld_reason": reason}
            )
        sections.append(s)
    return dossier.model_copy(update={"sections": sections})


def test_a_withheld_notice_appears_only_where_a_summary_was_attempted() -> None:
    dossier = _fixture_with_states()
    on = _markdown(dossier, summaries=True)
    assert "Summary withheld: the text does not end at a sentence end." in on
    assert "Summary skipped" not in on
    off = _markdown(dossier, summaries=False)
    assert "Summary withheld" not in off
    assert "Summary pending" not in off and "Summary unavailable" not in off


def _view_without_prose() -> DossierView:
    view = make_fixture_view()
    sections = [
        s.model_copy(update={"chunk_ids": [], "summary": None, "summary_state": "no_prose"})
        for s in view.sections
    ]
    budget = view.budget.model_copy(update={"included_chunk_ids": [], "omitted_chunks": 0})
    return view.model_copy(update={"chunks": [], "sections": sections, "budget": budget})


def test_an_article_without_prose_has_no_opening_note_and_an_empty_sources_list() -> None:
    view = _view_without_prose()
    text = render.render_markdown(view)
    budget_line = next(ln for ln in text.splitlines() if ln.startswith("Budget "))
    assert budget_line.startswith("Budget 32,000 tokens: no passages")
    assert "Opening passages" not in text
    assert FLAT_NOTICE not in text
    assert "Left out: 4 sections without prose: " in text
    assert "## Sources\n\n- (none included at this budget)\n" in text


def test_the_cap_leaves_no_title_for_a_group_after_eight_named_sections() -> None:
    chunks = [prose("l0", [], 0, "Alpha builds boats.", 1.0)]
    sections = [section("s0", [], ["l0"])]
    for n in range(8):
        sections.append(section(f"e{n}", [f"E{n}"], [], label=f"Empty {n}"))
    chunks.append(prose("x:0", ["X"], 10, sized("Topic began.", 2100)))
    sections.append(section("x", ["X"], ["x:0"], label="Part X"))
    text = _markdown(dossier_of(sections, chunks), 2000)
    line = next(ln for ln in text.splitlines() if ln.startswith("Left out:"))
    assert line.endswith("; 1 section left out at this budget")
