"""Markdown structure for nested, empty and budget-cut sections."""

from __future__ import annotations

import pytest

from tests.factories.dossier import (
    make_budget_dossier,
    make_freshness,
    make_links,
    make_nested_dossier,
)
from wke.core import pack, render
from wke.core.models import Dossier, Section
from wke.core.models.budgets import BudgetTokens
from wke.core.pack.result import PackedDossier
from wke.core.render.labels import heading_prefix


def _markdown(dossier: Dossier, budget: BudgetTokens = 2000) -> str:
    links = make_links(dossier)
    view = render.build_view(
        dossier, budget, make_freshness(dossier), links, include_summaries=True
    )
    return render.render_markdown(view, include_summaries=True, lean=False)


@pytest.mark.parametrize(
    ("path", "marks"),
    [
        ([], "##"),
        (["A"], "##"),
        (["A", "B"], "###"),
        (list("ABCDE"), "######"),
        (list("ABCDEFG"), "######"),
    ],
)
def test_heading_marks_follow_the_depth_and_stop_at_six(path: list[str], marks: str) -> None:
    section = Section(
        id="x",
        label="X",
        label_source="heading",
        chunk_ids=[],
        heading_path=path,
        summary_state="skipped",
    )
    assert heading_prefix(section) == marks


def test_heading_depth_follows_the_heading_path() -> None:
    text = _markdown(make_nested_dossier())
    assert "\n## Topic\n" in text
    assert "\n## Parent\n" in text
    assert "\n### Child\n" in text
    assert "\n## Busy\n" in text


def test_no_prose_parent_shows_only_its_heading() -> None:
    text = _markdown(make_nested_dossier())
    parent_block = text.split("## Parent\n")[1].split("### Child")[0]
    assert parent_block.strip() == ""


def test_no_prose_leaf_is_left_out_and_named_in_the_header() -> None:
    text = _markdown(make_nested_dossier())
    assert "## Leaf" not in text
    assert "Left out: 1 section without prose: Leaf\n" in text
    assert "No prose passages kept" not in text


def test_header_states_the_budget_even_when_everything_fits() -> None:
    text = _markdown(make_nested_dossier())
    assert "\nBudget 2,000 tokens: all 4 passages\n" in text
    assert "more passage" not in text


def test_no_line_when_no_section_is_left_out() -> None:
    dossier = make_nested_dossier()
    sections = [s for s in dossier.sections if s.id != "3"]
    text = _markdown(dossier.model_copy(update={"sections": sections}))
    assert "without prose" not in text


def test_lord_shape_drops_trailing_no_prose_and_keeps_heading_only_parent() -> None:
    dossier = make_nested_dossier()
    tail = dossier.sections[3].model_copy(update={"id": "6", "label": "External links"})
    text = _markdown(dossier.model_copy(update={"sections": [*dossier.sections, tail]}))
    assert "Left out: 2 sections without prose: Leaf, External links\n" in text
    assert "## External links" not in text
    assert "\n## Parent\n" in text
    assert "\n### Child\n" in text


def test_budget_line_counts_passages_left_out_and_no_section_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dossier = make_nested_dossier()
    real_pack = pack.pack

    def tight(
        d: Dossier,
        requested: BudgetTokens,
        include_summaries: bool = True,
        reserve: int = 0,
        facts: bool = True,
    ) -> PackedDossier:
        packed = real_pack(d, requested, include_summaries, reserve, facts)
        keep = [i for i in packed.budget.included_chunk_ids if i != "1:4:1"]
        budget = packed.budget.model_copy(
            update={"included_chunk_ids": keep, "omitted_chunks": 1, "complete": False}
        )
        return PackedDossier(budget, packed.chunk_texts, packed.included_summary_section_ids)

    monkeypatch.setattr("wke.core.render.view.pack", tight)
    text = _markdown(dossier)
    assert "\nBudget 2,000 tokens: 3 of 4 passages\n" in text
    assert "more passage" not in text


def test_section_whose_passage_does_not_fit_is_represented_by_its_summary() -> None:
    text = _markdown(make_budget_dossier())
    huge = text.split("## Huge\n")[1].split("\n## ")[0]
    assert huge.startswith(f"\n**{render.SUMMARY_LABEL}**\n\nA short summary.\n[c1]\n")
    assert "> x" not in huge
    assert "## Huger" not in text
    assert (
        "Left out: 1 section without prose: Leaf; 1 section left out at this budget: Huger\n"
    ) in text
    assert "\n## Busy\n" in text


def test_heading_only_parent_is_kept_for_an_included_child() -> None:
    dossier = make_budget_dossier()
    text = _markdown(dossier)
    parent_block = text.split("## Parent\n")[1].split("### Child")[0]
    assert parent_block.strip() == ""
    assert "\n### Child\n" in text


def _jumping(paths: list[list[str]], kinds: list[str] | None = None) -> Dossier:
    """The nested dossier whose last section, "Busy", holds one chunk per heading path, in order."""
    base = make_nested_dossier()
    template = base.chunks[2]
    chunks = [
        template.model_copy(
            update={
                "id": f"1:4:{n}",
                "heading_path": path,
                "text": f"Busy passage {n}.",
                "kind": kinds[n] if kinds else "prose",
            }
        )
        for n, path in enumerate(paths)
    ]
    busy = base.sections[4].model_copy(update={"chunk_ids": [c.id for c in chunks]})
    sections = [*base.sections[:4], busy]
    return base.model_copy(update={"sections": sections, "chunks": [*base.chunks[:2], *chunks]})


def _busy_block(text: str) -> str:
    return text.split("\n## Busy\n")[1].split("\n## Sources")[0]


def test_structural_view_shows_a_subsection_heading_on_a_jump() -> None:
    block = _busy_block(
        _markdown(_jumping([["Busy"], ["Busy", "Alpha"], ["Busy", "Alpha"], ["Busy", "Beta"]]))
    )
    assert block.index("passage 0.") < block.index("\n### Alpha\n") < block.index("passage 1.")
    assert block.index("passage 2.") < block.index("\n### Beta\n") < block.index("passage 3.")
    assert block.count("### Alpha") == 1


def test_no_heading_for_the_first_chunk_or_the_same_path() -> None:
    assert "###" not in _busy_block(_markdown(_jumping([["Busy", "Alpha"], ["Busy", "Alpha"]])))
    assert "###" not in _busy_block(_markdown(_jumping([["Busy"], ["Busy"]])))


def test_no_heading_for_a_return_to_the_sections_own_path() -> None:
    block = _busy_block(_markdown(_jumping([["Busy", "Alpha"], ["Busy"]])))
    assert "###" not in block


def test_ml_view_gets_no_extra_heading() -> None:
    text = _markdown(make_nested_dossier())
    assert text.count("###") == 1


def test_heading_level_is_one_below_the_section_and_stops_at_six() -> None:
    deep = list("ABCDE")
    block = _busy_block(_markdown(_jumping([["Busy"], ["Busy", "Alpha"]])))
    assert "\n### Alpha\n" in block
    base = _jumping([["Busy"], [*deep, "Z"]])
    busy = base.sections[4].model_copy(update={"heading_path": deep})
    text = _markdown(base.model_copy(update={"sections": [*base.sections[:4], busy]}))
    assert "\n###### Z\n" in text
    assert "####### Z" not in text


def test_subsection_heading_is_escaped() -> None:
    block = _busy_block(_markdown(_jumping([["Busy"], ["Busy", "<b>Alpha</b>"]])))
    assert "<b>" not in block


def test_facts_table_and_list_chunks_do_not_change_the_previous_path() -> None:
    kinds = ["prose", "table", "prose", "facts", "prose", "list", "prose"]
    paths = [["Busy", "A"], ["Busy", "B"], ["Busy", "A"], ["Busy", "C"], ["Busy", "A"]]
    paths += [["Busy", "D"], ["Busy", "A"]]
    assert "###" not in _busy_block(_markdown(_jumping(paths, kinds)))


def test_flag_off_is_byte_equal_to_today() -> None:
    jumping = _jumping([["Busy"], ["Busy", "Alpha"], ["Busy", "Beta"]])
    flat = _jumping([["Busy"], ["Busy"], ["Busy"]])
    links = make_links(jumping)
    view = render.build_view(
        jumping,
        2000,
        make_freshness(jumping),
        links,
        include_summaries=True,
        subsection_headings=False,
    )
    off = render.render_markdown(
        view, include_summaries=True, subsection_headings=False, lean=False
    )
    assert "###" not in _busy_block(off)
    assert off == _markdown(flat)
    assert "### Alpha" in _markdown(jumping)
