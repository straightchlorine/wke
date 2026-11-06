"""The token budget counts the dossier part only: headings, passages, tags and summaries."""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings

from tests.factories.dossier import (
    dossiers,
    make_budget_dossier,
    make_freshness,
    make_lead_only_dossier,
    make_links,
    make_overflowing_fixture_dossier,
    make_summary,
)
from tests.factories.synthetic import dossier_of, prose, section
from wke.core import pack, render
from wke.core.models import Dossier, DossierView
from wke.core.models.budgets import BudgetTokens
from wke.core.pack.costs import SECTION_HEADING_OVERHEAD_TOKENS, TAG_TOKENS
from wke.core.pack.result import PackedDossier
from wke.core.render.markdown import content_text
from wke.core.text.tokens import est_tokens


def _build(dossier: Dossier, budget: BudgetTokens = 2000) -> DossierView:
    return render.build_view(dossier, budget, make_freshness(dossier), make_links(), False)


def test_content_that_fills_the_budget_still_fits_with_sources_on_top() -> None:
    # The packer charges the heading and the citation tag around the lead; the
    # lead sized to use the rest puts the content at the budget.
    lead_tokens = 2000 - SECTION_HEADING_OVERHEAD_TOKENS - TAG_TOKENS
    view = _build(make_lead_only_dossier(lead_tokens))
    content, _ = content_text(view, False)
    assert view.budget.used_est_tokens == est_tokens(content) <= 2000
    assert 2000 - view.budget.used_est_tokens <= SECTION_HEADING_OVERHEAD_TOKENS
    assert est_tokens(render.render_markdown(view, False)) > 2000


def test_metadata_and_sources_do_not_move_the_selection() -> None:
    base = make_budget_dossier()
    seed = base.citations[0]
    long_pin = seed.pin.model_copy(
        update={"permalink": str(seed.pin.permalink) + "&x=" + "q" * 900}
    )
    heavy = base.model_copy(
        update={
            "topic": base.topic.model_copy(update={"title": "A very long title " * 20}),
            "citations": [
                seed.model_copy(update={"pin": long_pin, "url": "https://x/" + "u" * 900})
            ],
        }
    )
    assert _build(heavy).budget.included_chunk_ids == _build(base).budget.included_chunk_ids


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(dossier=dossiers())
def test_fit_loop_converges_at_2000_for_dense_dossiers(dossier: Dossier) -> None:
    try:
        view = _build(dossier)
    except ValueError:
        pytest.fail("a generated dossier must fit 2000 tokens")
    content, _ = content_text(view, False)
    assert view.budget.used_est_tokens == est_tokens(content) <= 2000
    assert view.chunks


def test_content_that_cannot_fit_raises_not_overshoots() -> None:
    sentence_without_end = "word " * 2500
    with pytest.raises(ValueError, match="cannot fit"):
        _build(make_lead_only_dossier(0, sentence_without_end.strip()))


def test_content_still_over_after_the_rounds_is_trimmed_from_the_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # One-character lines double in size once quoted, which the packer does not
    # see; with no fit rounds only the trim can bring the content under 2000.
    dossier = make_overflowing_fixture_dossier()
    lined = [
        chunk.model_copy(update={"text": "a\n" * 400, "est_tokens": 200, "links": []})
        for chunk in dossier.chunks
    ]
    dossier = dossier.model_copy(update={"chunks": lined})
    monkeypatch.setattr("wke.core.render.view.MAX_FIT_ROUNDS", 0)
    packed = pack.pack(dossier, 2000).budget
    view = _build(dossier)
    content, _ = content_text(view, False)
    assert est_tokens(content) == view.budget.used_est_tokens <= 2000
    kept = view.budget.included_chunk_ids
    assert len(kept) < len(packed.included_chunk_ids)
    assert kept == packed.included_chunk_ids[: len(kept)]
    assert view.budget.omitted_chunks == len(dossier.chunks) - len(kept)
    assert not view.budget.complete


def test_the_trim_drops_the_summary_of_the_section_it_empties_and_keeps_the_others(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Section "2" has one passage and a summary, section "4" two passages and a
    # summary, section "5" only a summary standing in for a passage too big for
    # the budget. One-character lines double in size once quoted, so only the
    # trim brings the content under 2000: it drops the passages of "2" and the
    # second of "4".
    dossier = make_budget_dossier()
    lined = {"1:0:0", "1:2:0", "1:4:0", "1:4:1"}
    chunks = [
        c.model_copy(update={"text": "a\n" * 640, "est_tokens": 320}) if c.id in lined else c
        for c in dossier.chunks
    ]
    sections = [
        s.model_copy(update={"summary": make_summary("Second summary."), "summary_state": "done"})
        if s.id in {"2", "4"}
        else s
        for s in dossier.sections
    ]
    dossier = dossier.model_copy(update={"chunks": chunks, "sections": sections})
    monkeypatch.setattr("wke.core.render.view.MAX_FIT_ROUNDS", 0)
    packed = pack.pack(dossier, 2000)
    assert packed.included_summary_section_ids == frozenset({"2", "4", "5"})

    view = render.build_view(
        dossier, 2000, make_freshness(dossier), make_links(dossier), include_summaries=True
    )

    assert view.budget.included_chunk_ids == ["1:0:0", "1:4:0"]
    assert {s.id for s in view.sections if s.summary is not None} == {"4", "5"}
    assert set(view.budget.shortened_chunk_ids) <= set(view.budget.included_chunk_ids)


def test_the_held_back_reserve_doubles_each_round_while_the_pack_does_not_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dossier = make_overflowing_fixture_dossier()
    lined = [
        chunk.model_copy(update={"text": "a\n" * 400, "est_tokens": 200, "links": []})
        for chunk in dossier.chunks
    ]
    dossier = dossier.model_copy(update={"chunks": lined})
    reserves: list[int] = []
    real_pack = pack.pack

    def stubborn(
        d: Dossier, requested: BudgetTokens, include_summaries: bool = True, reserve: int = 0
    ) -> PackedDossier:
        reserves.append(reserve)
        return real_pack(d, requested, include_summaries, 0)

    monkeypatch.setattr("wke.core.render.view.pack", stubborn)
    view = _build(dossier)
    step = reserves[1]
    assert step > 0
    assert reserves[1:] == [step * (2**n - 1) for n in range(1, len(reserves))]
    content, _ = content_text(view, False)
    assert est_tokens(content) == view.budget.used_est_tokens <= 2000


def test_the_trim_takes_a_cut_table_out_of_the_shortened_ids_with_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # One-character rows are cheap for the packer and double once quoted.
    rows = "\n".join(f"| {n} |" for n in range(3000))
    table = prose("s1:table0", ["Data"], 2, f"Caption\n| N |\n| --- |\n{rows}")
    table = table.model_copy(update={"kind": "table"})
    dossier = dossier_of(
        [section("s0", [], ["l0"]), section("s1", ["Data"], ["s1:0", table.id])],
        [prose("l0", [], 0, "Alpha builds boats."), prose("s1:0", ["Data"], 1, "Harbour."), table],
    )
    monkeypatch.setattr("wke.core.render.view.MAX_FIT_ROUNDS", 0)
    assert pack.pack(dossier, 2000).budget.shortened_chunk_ids == [table.id]

    view = _build(dossier)

    assert table.id not in view.budget.included_chunk_ids
    assert view.budget.shortened_chunk_ids == []
    assert view.budget.omitted_chunks == 1


def test_a_dossier_without_a_passage_cannot_be_viewed() -> None:
    dossier = make_overflowing_fixture_dossier().model_copy(update={"chunks": []})
    with pytest.raises(ValueError, match="no passage"):
        _build(dossier)
