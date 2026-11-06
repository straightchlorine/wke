"""Coverage-first packing: order of inclusion, summaries as stand-ins, monotone budgets."""

from __future__ import annotations

from tests.factories.dossier import FACTORY_REV_ID, make_fixture_dossier, make_summary
from tests.factories.packing import make_chunk, make_section
from tests.factories.synthetic import dossier_of
from wke.core import pack
from wke.core.models import Chunk, Dossier, Section
from wke.core.pack.costs import SECTION_HEADING_OVERHEAD_TOKENS, SUMMARY_FRAME_TOKENS, TAG_TOKENS
from wke.core.pack.openers import place_openers
from wke.core.pack.state import Packer, PackState
from wke.core.text.tokens import est_tokens


def _wide() -> Dossier:
    """A lead plus six sections of three passages each, the relevant one last."""
    sections = [make_section("s0", [], ["l0"])]
    chunks = [make_chunk("l0", [], 0, 100, 1.0)]
    for i in range(1, 7):
        ids = [f"s{i}:{n}" for n in range(3)]
        sections.append(make_section(f"s{i}", [f"S{i}"], ids))
        for n, cid in enumerate(ids):
            relevance = 0.9 if i == 6 else 0.1 + 0.01 * i
            chunks.append(make_chunk(cid, [f"S{i}"], 10 * i + n, 120, relevance))
    return dossier_of(sections, chunks)


def test_every_section_gets_a_paragraph_and_the_top_one_its_late_passage_next() -> None:
    packed = pack.pack(_wide(), 2000)
    ids = packed.budget.included_chunk_ids
    assert {f"s{i}:0" for i in range(1, 7)} <= set(ids)
    assert ids.index("s6:2") == ids.index("s6:0") + 1


def test_lead_is_capped_at_a_share_of_the_budget_before_the_openers() -> None:
    lead_ids = [f"l{n}" for n in range(8)]
    sections = [make_section("s0", [], lead_ids)]
    chunks = [make_chunk(cid, [], n, 240, 1.0) for n, cid in enumerate(lead_ids)]
    for i in range(1, 4):
        sections.append(make_section(f"s{i}", [f"S{i}"], [f"s{i}:0"]))
        chunks.append(make_chunk(f"s{i}:0", [f"S{i}"], 10 + i, 120, 0.2))
    dossier = dossier_of(sections, chunks)
    ids = pack.pack(dossier, 2000).budget.included_chunk_ids
    # The lead opens the pack, the share leaves it short of the whole lead, and
    # every section still gets its opener. How many lead passages fit is a
    # function of the share, so the count is not asserted here.
    assert ids[0] == "l0"
    assert set(lead_ids) - set(ids)
    assert {"s1:0", "s2:0", "s3:0"} <= set(ids)
    wide = set(pack.pack(dossier, 8000).budget.included_chunk_ids)
    assert set(ids) <= wide
    assert set(lead_ids) <= wide


def test_summary_stands_in_for_a_section_and_is_counted_in_the_budget() -> None:
    summary = make_summary("A short summary of the section.")
    sections = [make_section("s0", [], ["l0"]), make_section("s1", ["S1"], ["s1:0"], summary)]
    huge = make_chunk("s1:0", ["S1"], 1, 1900, 0.9)
    dossier = dossier_of(sections, [make_chunk("l0", [], 0, 100, 1.0), huge])
    packed = pack.pack(dossier, 2000)
    assert packed.budget.included_chunk_ids == ["l0"]
    assert packed.included_summary_section_ids == frozenset({"s1"})
    expected = (
        2 * SECTION_HEADING_OVERHEAD_TOKENS
        + dossier.chunks[0].est_tokens
        + TAG_TOKENS
        + est_tokens(summary.text)
        + SUMMARY_FRAME_TOKENS
        + TAG_TOKENS
    )
    assert packed.budget.used_est_tokens == expected
    layout = pack.section_layout(dossier.sections, ["l0"], packed.included_summary_section_ids)
    assert "s1" in layout.kept_ids and not layout.budget_empty


def test_section_with_neither_opener_nor_summary_is_left_out() -> None:
    huge = make_chunk("s1:0", ["S1"], 1, 1900, 0.9)
    sections = [make_section("s0", [], ["l0"]), make_section("s1", ["S1"], ["s1:0"])]
    dossier = dossier_of(sections, [make_chunk("l0", [], 0, 100, 1.0), huge])
    packed = pack.pack(dossier, 2000)
    layout = pack.section_layout(dossier.sections, packed.budget.included_chunk_ids)
    assert [s.id for s in layout.budget_empty] == ["s1"]
    assert packed.budget.omitted_chunks == 1
    assert not packed.budget.complete


def test_facts_come_right_after_the_lead_and_tables_follow_the_openers() -> None:
    dossier = make_fixture_dossier()
    packed = pack.pack(dossier, 2000)
    ids = packed.budget.included_chunk_ids
    assert ids[0] == f"{FACTORY_REV_ID}:lead:0"
    assert ids[1] == f"{FACTORY_REV_ID}:lead:facts"
    assert ids.index(f"{FACTORY_REV_ID}:career:table0") > ids.index(
        f"{FACTORY_REV_ID}:early_life:0"
    )


def test_a_larger_budget_extends_the_pack_of_the_smaller_one() -> None:
    dossier = _wide()
    small = pack.pack(dossier, 2000).budget.included_chunk_ids
    large = pack.pack(dossier, 8000).budget.included_chunk_ids
    assert small == large[: len(small)]
    assert set(small) < set(large)
    assert pack.pack(dossier, 32000).budget.complete


def test_the_lead_is_cut_at_a_sentence_end_and_the_pack_stays_within_the_budget() -> None:
    text = ("First sentence is here. " + "Another sentence follows it. " * 400).strip()
    lead = make_chunk("l0", [], 0, 240, 1.0).model_copy(
        update={"text": text, "est_tokens": est_tokens(text)}
    )
    dossier = dossier_of([make_section("s0", [], ["l0"])], [lead])
    packed = pack.pack(dossier, 2000)
    shown = packed.chunk_texts["l0"]
    assert shown != text
    assert text.startswith(shown)
    assert shown.endswith("follows it.")
    assert packed.budget.used_est_tokens <= 2000


def test_a_late_lead_similar_passage_of_a_top_section_reaches_the_first_budget() -> None:
    ids = [f"s1:{n}" for n in range(9)]
    sections = [make_section("s0", [], ["l0"]), make_section("s1", ["Flight"], ids)]
    chunks = [make_chunk("l0", [], 0, 100, 1.0)]
    for n, cid in enumerate(ids):
        chunks.append(make_chunk(cid, ["Flight"], 10 + n, 150, 0.9 if n == 8 else 0.2))
    packer = Packer(dossier_of(sections, chunks), 2000, PackState(used=0), False)
    place_openers(packer)
    assert packer.included >= {"s1:0", "s1:8"}
    assert not packer.included & {"s1:1", "s1:4", "s1:7"}


def test_the_late_passage_comes_from_the_last_third_only() -> None:
    ids = [f"s1:{n}" for n in range(9)]
    sections = [make_section("s0", [], ["l0"]), make_section("s1", ["Flight"], ids)]
    chunks = [make_chunk("l0", [], 0, 100, 1.0)]
    for n, cid in enumerate(ids):
        chunks.append(make_chunk(cid, ["Flight"], 10 + n, 150, 0.95 if n == 3 else 0.2 + 0.01 * n))
    packer = Packer(dossier_of(sections, chunks), 2000, PackState(used=0), False)
    place_openers(packer)
    assert "s1:3" not in packer.included
    assert "s1:8" in packer.included


def _long_opener_dossier() -> Dossier:
    """A short lead and one section whose opening passage is about 1900 tokens."""
    sentence = "The committee published its findings on the matter " + "word " * 25 + "today. "
    opener = make_chunk("s1:0", ["S1"], 10, 1900, 0.9)
    opener = opener.model_copy(update={"text": (sentence * 42).strip()})
    sections = [make_section("s0", [], ["l0"]), make_section("s1", ["S1"], ["s1:0"])]
    chunks = [make_chunk("l0", [], 0, 100, 1.0), opener]
    return dossier_of(sections, chunks)


def test_a_long_opener_without_a_summary_is_left_out_whole_at_2000() -> None:
    packed = pack.pack(_long_opener_dossier(), 2000)
    assert "s1:0" not in packed.budget.included_chunk_ids
    assert "s1:0" not in packed.budget.shortened_chunk_ids


def test_the_same_opener_is_whole_at_8000() -> None:
    dossier = _long_opener_dossier()
    packed = pack.pack(dossier, 8000)
    opener = next(c for c in dossier.chunks if c.id == "s1:0")
    assert packed.chunk_texts["s1:0"] == opener.text
    assert "s1:0" not in packed.budget.shortened_chunk_ids


def test_a_lead_cut_at_a_small_budget_is_restored_whole_at_a_larger_one() -> None:
    text = ("Another sentence follows it. " * 400).strip()
    lead = make_chunk("l0", [], 0, 240, 1.0).model_copy(
        update={"text": text, "est_tokens": est_tokens(text)}
    )
    dossier = dossier_of([make_section("s0", [], ["l0"])], [lead])
    assert pack.pack(dossier, 2000).budget.shortened_chunk_ids == ["l0"]
    packed = pack.pack(dossier, 8000)
    assert packed.chunk_texts["l0"] == text
    assert packed.budget.shortened_chunk_ids == []


def test_the_key_facts_ignore_the_reserve() -> None:
    sections = [make_section("s0", [], ["l0", "facts"])]
    chunks = [make_chunk("l0", [], 0, 100, 1.0), make_chunk("facts", [], 1, 300, 1.0, "facts")]
    dossier = dossier_of(sections, chunks)
    assert "facts" in pack.pack(dossier, 2000, reserve=1800).budget.included_chunk_ids


def _packer_after_lead_and_opener(sections: list[Section], chunks: list[Chunk]) -> Packer:
    packer = Packer(dossier_of(sections, chunks), 2000, PackState(used=0), False)
    place_openers(packer)
    return packer


def test_a_late_passage_over_its_share_of_the_room_left_is_not_placed() -> None:
    sections = [make_section("s0", [], ["l0"]), make_section("s1", ["S1"], ["s1:0", "s1:1"])]
    chunks = [
        make_chunk("l0", [], 0, 100, 1.0),
        make_chunk("s1:0", ["S1"], 10, 100, 0.1),
        make_chunk("s1:1", ["S1"], 11, 700, 0.9),
    ]
    packer = _packer_after_lead_and_opener(sections, chunks)
    assert "s1:0" in packer.included
    assert "s1:1" not in packer.included


def test_each_heading_is_charged_once() -> None:
    sections = [
        make_section("s0", [], ["l0"]),
        make_section("a", ["A"], ["a0"]),
        make_section("b", ["A", "B"], ["b0"]),
    ]
    chunks = [
        make_chunk("l0", [], 0, 10, 1.0),
        make_chunk("a0", ["A"], 1, 10, 0.5),
        make_chunk("b0", ["A", "B"], 2, 10, 0.5),
    ]
    packer = Packer(dossier_of(sections, chunks), 2000, PackState(used=0), False)
    packer.add_chunk(packer.chunk_by_id["b0"])
    assert packer.state.used == 2 * SECTION_HEADING_OVERHEAD_TOKENS + 10 + TAG_TOKENS
    packer.add_chunk(packer.chunk_by_id["a0"])
    assert packer.state.used == 2 * SECTION_HEADING_OVERHEAD_TOKENS + 2 * (10 + TAG_TOKENS)


def test_a_summary_is_left_out_when_its_heading_does_not_fit_beside_it() -> None:
    # 2000 - lead (100 + tag + heading) leaves 1882; the summary costs 1874, its heading 16 more.
    summary = make_summary("w" * (1836 * 4))
    sections = [
        make_section("s0", [], ["l0"]),
        make_section("s1", ["S1"], ["s1:0"], summary),
    ]
    chunks = [make_chunk("l0", [], 0, 100, 1.0), make_chunk("s1:0", ["S1"], 1, 1900, 0.9)]
    packed = pack.pack(dossier_of(sections, chunks), 2000)
    assert packed.included_summary_section_ids == frozenset()


def test_the_summaries_beside_passages_take_a_tenth_of_a_step_before_the_rest_is_placed() -> None:
    summary = make_summary("w" * (360 * 4))
    sections = [
        make_section("s0", [], ["l0"]),
        make_section("s1", ["S1"], ["s1:0", "s1:1"], summary),
    ]
    chunks = [
        make_chunk("l0", [], 0, 100, 1.0),
        make_chunk("s1:0", ["S1"], 10, 100, 0.5),
        make_chunk("s1:1", ["S1"], 11, 1400, 0.5),
    ]
    packed = pack.pack(dossier_of(sections, chunks), 2000)
    assert "s1:1" in packed.budget.included_chunk_ids
    assert packed.included_summary_section_ids == frozenset()


def test_the_rest_is_placed_by_relevance_highest_first() -> None:
    sections = [make_section("s0", [], ["l0"]), make_section("s1", ["S1"], ["a", "b", "c"])]
    chunks = [
        make_chunk("l0", [], 0, 100, 1.0),
        make_chunk("a", ["S1"], 10, 100, 0.5),
        make_chunk("b", ["S1"], 11, 1000, 0.2),
        make_chunk("c", ["S1"], 12, 1000, 0.8),
    ]
    ids = pack.pack(dossier_of(sections, chunks), 2000).budget.included_chunk_ids
    assert "c" in ids and "b" not in ids


def test_the_rest_prefers_the_passage_of_the_more_important_section_at_equal_relevance() -> None:
    # "Legacy" names an outcome (bonus 0.25); "Plain" is later in the article (position 1.0
    # against 0.5); the outcome weighs more. The less important section's passage comes first
    # in document order, so only the importance puts the other one ahead.
    sections = [
        make_section("s0", [], ["l0"]),
        make_section("Legacy", ["Legacy"], ["la", "lx"]),
        make_section("Plain", ["Plain"], ["pa", "px"]),
    ]
    chunks = [
        make_chunk("l0", [], 0, 100, 1.0),
        make_chunk("la", ["Legacy"], 10, 100, 0.5),
        make_chunk("lx", ["Legacy"], 30, 900, 0.5),
        make_chunk("pa", ["Plain"], 20, 100, 0.5),
        make_chunk("px", ["Plain"], 25, 900, 0.5),
    ]
    ids = pack.pack(dossier_of(sections, chunks), 2000).budget.included_chunk_ids
    assert "lx" in ids and "px" not in ids


def test_the_reserve_is_held_at_the_requested_budget_only() -> None:
    # At 2000 the opener fits and the second lead passage is over the lead share; at 8000 that
    # passage joins. With the reserve held at every step the opener would wait for 8000 and
    # come after it.
    sections = [make_section("s0", [], ["l0", "l1"]), make_section("s1", ["S1"], ["s1:0"])]
    chunks = [
        make_chunk("l0", [], 0, 100, 1.0),
        make_chunk("l1", [], 1, 900, 1.0),
        make_chunk("s1:0", ["S1"], 10, 100, 0.5),
    ]
    packed = pack.pack(dossier_of(sections, chunks), 8000, reserve=1900)
    assert packed.budget.included_chunk_ids == ["l0", "s1:0", "l1"]


def test_only_late_passages_of_the_top_sections_follow_their_opener() -> None:
    packer = Packer(_wide(), 2000, PackState(used=0), False)
    place_openers(packer)
    top, sixth = packer.ranked[0], packer.ranked[5]
    assert top.chunk_ids[2] in packer.included
    assert sixth.chunk_ids[0] in packer.included
    assert sixth.chunk_ids[2] not in packer.included
