"""A lean view has no Key facts block and no per-section "left out" lines in the budgeted text."""

from __future__ import annotations

import itertools
import re

import pytest

from tests.factories.dossier import make_fixture_dossier, make_freshness, make_links
from tests.factories.synthetic import dossier_of, prose, section, sized
from wke.core import render
from wke.core.models import Dossier, DossierView
from wke.core.models.budgets import BUDGETS, BudgetTokens
from wke.core.render.markdown import content_text
from wke.core.render.parts import ALL_PARTS, DEFAULT_PARTS, Part
from wke.core.text.tokens import est_tokens

NOTICE = "_1 list of this section is left out at this budget._"
FACTS_LABEL = "**Key facts**"
FACTS_BLOCK = re.compile(r"\*\*Key facts\*\*\n\n(?:> - .*\n)+\[c1\]\n\n")
PART_SETS: list[frozenset[Part]] = [
    frozenset({"dossier", *combo})
    for n in range(3)
    for combo in itertools.combinations(("metadata", "sources"), n)
]


def _dossier() -> Dossier:
    """A lead with Key facts, one section of 40 passages and a list too long for 2000 tokens."""
    rows = "\n".join(f"Fact {n}: {sized('value', 14)}" for n in range(12))
    facts = prose("1:lead:facts", [], 1, rows).model_copy(update={"kind": "facts"})
    items = "\n".join(f"- {'word ' * 120}{n}" for n in range(10))
    structured = prose("1:data:list0", ["Data"], 99, items).model_copy(update={"kind": "list"})
    passages = [
        prose(f"1:data:{n}", ["Data"], n, sized(f"Passage {n} says.", 90), 0.9 - n * 0.01)
        for n in range(40)
    ]
    return dossier_of(
        [
            section("lead", [], ["1:lead:0", facts.id]),
            section("data", ["Data"], [*(p.id for p in passages), structured.id]),
        ],
        [prose("1:lead:0", [], 0, "Alpha builds boats."), facts, *passages, structured],
    )


def _view(dossier: Dossier, budget: BudgetTokens = 2000, lean: bool = False) -> DossierView:
    return render.build_view(
        dossier, budget, make_freshness(dossier), make_links(dossier), lean=lean
    )


def _passage_tokens(view: DossierView) -> int:
    return sum(c.est_tokens for c in view.chunks if c.kind == "prose")


def test_the_default_dossier_part_has_no_key_facts_and_no_left_out_line() -> None:
    text = render.render_markdown(_view(_dossier(), lean=True), parts=DEFAULT_PARTS, lean=True)
    assert FACTS_LABEL not in text
    assert "Fact 0:" not in text
    assert "of this section" not in text


def test_the_base_render_has_both() -> None:
    text = render.render_markdown(_view(_dossier()), parts=DEFAULT_PARTS, lean=False)
    assert FACTS_LABEL in text
    assert NOTICE in text


@pytest.mark.parametrize("parts", PART_SETS, ids=lambda p: ",".join(sorted(p)))
def test_no_part_combination_brings_the_key_facts_back(parts: frozenset[Part]) -> None:
    text = render.render_markdown(_view(_dossier(), lean=True), parts=parts, lean=True)
    assert FACTS_LABEL not in text
    assert "Fact 0:" not in text
    assert (NOTICE in text) == ("metadata" in parts)


def test_metadata_brings_the_left_out_lines_back_and_the_head_still_names_them() -> None:
    parts: frozenset[Part] = frozenset({"dossier", "metadata"})
    text = render.render_markdown(_view(_dossier(), lean=True), parts=parts, lean=True)
    assert NOTICE in text
    assert "1 list left out at this budget\n" in text


def test_the_freed_budget_goes_to_passages() -> None:
    dossier = _dossier()
    base, lean = _view(dossier), _view(dossier, lean=True)
    assert len(lean.chunks) > len(base.chunks)
    assert _passage_tokens(lean) > _passage_tokens(base)
    text, _ = content_text(lean, notes=False)
    assert lean.budget.used_est_tokens == est_tokens(text) <= 2000


@pytest.mark.parametrize("budget", BUDGETS)
def test_a_lean_view_never_holds_fewer_passages(budget: BudgetTokens) -> None:
    for dossier in (_dossier(), make_fixture_dossier()):
        base, lean = _view(dossier, budget), _view(dossier, budget, lean=True)
        assert _passage_tokens(lean) >= _passage_tokens(base)
        assert lean.budget.used_est_tokens <= budget


def test_the_facts_chunk_is_in_no_list_of_the_lean_view_and_stays_in_the_dossier() -> None:
    dossier = _dossier()
    view = _view(dossier, lean=True)
    assert not any(c.kind == "facts" for c in view.chunks)
    assert not any(cid.endswith(":facts") for s in view.sections for cid in s.chunk_ids)
    assert not any(cid.endswith(":facts") for cid in view.budget.included_chunk_ids)
    lead = next(s for s in view.sections if not s.heading_path)
    assert set(lead.chunk_ids) <= set(view.budget.included_chunk_ids)
    assert any(c.kind == "facts" for c in dossier.chunks)
    assert any(cid.endswith(":facts") for s in dossier.sections for cid in s.chunk_ids)


def test_a_lean_pack_does_not_count_the_facts_as_omitted() -> None:
    view = _view(_dossier(), 32000, lean=True)
    assert view.budget.omitted_chunks == 0
    assert view.budget.complete


def test_the_whole_article_notice_survives_without_the_facts() -> None:
    text = render.render_markdown(_view(_dossier(), 32000, lean=True), parts=ALL_PARTS, lean=True)
    assert "This dossier holds the whole article" in text


def test_the_budget_line_does_not_count_the_facts_as_left_out() -> None:
    view = _view(_dossier(), lean=True)
    text = render.render_markdown(view, parts=ALL_PARTS, lean=True)
    assert "passages; 1 list left out at this budget\n" in text


@pytest.mark.parametrize("budget", BUDGETS)
@pytest.mark.parametrize("summaries", [False, True])
def test_where_the_budget_does_not_bind_lean_is_base_without_the_facts_block(
    budget: BudgetTokens, summaries: bool
) -> None:
    dossier = make_fixture_dossier()
    links, fresh = make_links(dossier), make_freshness(dossier)
    base_view = render.build_view(dossier, budget, fresh, links, include_summaries=summaries)
    base = render.render_markdown(base_view, summaries, False, ALL_PARTS, lean=False)
    lean_view = render.build_view(dossier, budget, fresh, links, summaries, lean=True)
    lean = render.render_markdown(lean_view, summaries, False, ALL_PARTS, lean=True)
    assert FACTS_BLOCK.search(base)
    assert lean == FACTS_BLOCK.sub("", base)
