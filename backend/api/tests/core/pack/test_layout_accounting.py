"""Section layout and token accounting of the packer, on the nested and budget fixtures."""

from __future__ import annotations

from tests.factories.dossier import make_budget_dossier, make_nested_dossier
from tests.factories.packing import make_section
from wke.core import pack
from wke.core.models import Section, SummaryState
from wke.core.pack.costs import SECTION_HEADING_OVERHEAD_TOKENS, SUMMARY_FRAME_TOKENS, TAG_TOKENS
from wke.core.pack.truncate import truncate_lead
from wke.core.text.tokens import est_tokens


def test_section_layout_judges_descendants_by_heading_path() -> None:
    def section(sid: str, path: list[str], state: SummaryState) -> Section:
        return Section(
            id=sid,
            label=path[-1] if path else "Lead",
            label_source="heading",
            chunk_ids=[f"c{sid}"] if state != "no_prose" else [],
            heading_path=path,
            summary_state=state,
        )

    sections = [
        section("0", [], "no_prose"),
        section("1", ["A"], "no_prose"),
        section("2", ["A", "B"], "no_prose"),
        section("3", ["A", "B", "C"], "skipped"),
        section("4", ["D"], "no_prose"),
        section("5", ["D", "E"], "no_prose"),
        section("6", ["F"], "skipped"),
    ]
    layout = pack.section_layout(sections, ["c3", "c6"])
    assert [s.id for s in layout.no_prose] == ["0", "4", "5"]
    assert layout.budget_empty == []
    assert layout.kept_ids == {"1", "2", "3", "6"}


def test_a_section_is_not_kept_for_a_later_one_outside_its_heading() -> None:
    sections = [make_section("1", ["A"], ["c1"]), make_section("2", ["D", "E"], ["c2"])]
    layout = pack.section_layout(sections, ["c2"])
    assert layout.kept_ids == {"2"}
    assert [s.id for s in layout.budget_empty] == ["1"]


def test_omitted_sections_do_not_cost_budget_overhead() -> None:
    dossier = make_nested_dossier()
    without_leaf = dossier.model_copy(
        update={"sections": [s for s in dossier.sections if s.id != "3"]}
    )
    assert (
        pack.pack(dossier, 2000).budget.used_est_tokens
        == pack.pack(without_leaf, 2000).budget.used_est_tokens
    )


def test_lead_truncation_cuts_at_a_real_sentence_end() -> None:
    text = "He was a lord (i.e. in the person of the king). " + "Then more words follow. " * 20
    cut = truncate_lead(text, 15)
    assert cut == "He was a lord (i.e. in the person of the king)."
    assert truncate_lead(text, 1) == "He was a lord (i.e. in the person of the king)."


def test_budget_empty_parent_is_kept_only_for_an_included_descendant() -> None:
    dossier = make_budget_dossier()
    parent = dossier.sections[1].model_copy(
        update={"chunk_ids": ["1:9:0"], "summary_state": "skipped"}
    )
    sections = [dossier.sections[0], parent, *dossier.sections[2:]]
    kept = pack.section_layout(sections, ["1:0:0", "1:2:0"])
    assert "1" in kept.kept_ids
    assert "1" not in {s.id for s in kept.budget_empty}
    dropped = pack.section_layout(sections, ["1:0:0"])
    assert "1" not in dropped.kept_ids
    assert "1" in {s.id for s in dropped.budget_empty}


def test_used_tokens_count_only_what_is_emitted() -> None:
    dossier = make_budget_dossier()
    packed = pack.pack(dossier, 2000)
    kept = {"0", "1", "2", "4", "5"}
    included = [c for c in dossier.chunks if c.id in packed.chunk_texts]
    expected = (
        SECTION_HEADING_OVERHEAD_TOKENS * len(kept)
        + sum(chunk.est_tokens + TAG_TOKENS for chunk in included)
        + est_tokens("A short summary.")
        + SUMMARY_FRAME_TOKENS
        + TAG_TOKENS
    )
    assert packed.budget.used_est_tokens == expected
    assert packed.included_summary_section_ids == frozenset({"5"})
