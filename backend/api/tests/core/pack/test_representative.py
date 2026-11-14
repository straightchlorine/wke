"""Which whole paragraph stands for a section, and which late passage joins it."""

from __future__ import annotations

import pytest

from tests.factories.synthetic import dossier_of, prose, section, sized
from wke.core import pack
from wke.core.models import Dossier
from wke.core.pack.lead import place_lead
from wke.core.pack.openers import place_openers
from wke.core.pack.representative import ShownOpenings, pick_representative
from wke.core.pack.state import Packer, PackState

LEAD = "Alpha Corporation is a company that builds river boats and sells them worldwide."


def _packer(dossier: Dossier, budget: int = 2000) -> Packer:
    packer = Packer(dossier, budget, PackState(used=0), False)
    place_lead(packer)
    return packer


def _opened(dossier: Dossier, budget: int = 2000) -> set[str]:
    packer = _packer(dossier, budget)
    place_openers(packer)
    return packer.included


def _pick(dossier: Dossier, section_id: str = "s1") -> str | None:
    """Id of the paragraph chosen for a section after the lead, or None."""
    packer = _packer(dossier)
    target = packer.section_by_id[section_id]
    chosen = pick_representative(packer, packer.prose_of(target), ShownOpenings.of(packer))
    return chosen.id if chosen else None


def _one_section(texts: list[str], sizes: list[int] | None = None) -> Dossier:
    """A lead plus one section holding the given paragraphs in order."""
    ids = [f"s1:{n}" for n in range(len(texts))]
    chunks = [prose("l0", [], 0, LEAD, 1.0)]
    for n, text in enumerate(texts):
        body = sized(text, sizes[n]) if sizes else text
        chunks.append(prose(ids[n], ["S1"], 10 + n, body))
    return dossier_of([section("s0", [], ["l0"]), section("s1", ["S1"], ids)], chunks)


def test_the_first_paragraph_stands_for_the_section_whole_when_it_fits() -> None:
    dossier = _one_section(["The council met on Friday.", "The mayor spoke on Monday."])
    assert _pick(dossier) == "s1:0"


def test_a_first_paragraph_over_its_share_gives_way_to_the_shortest_named_one() -> None:
    texts = ["The council met.", "The committee voted.", "Smith voted."]
    dossier = _one_section(texts, [1500, 300, 100])
    assert _pick(dossier) == "s1:2"


@pytest.mark.parametrize(
    "unfit",
    ["He voted.", "Later the vote passed.", "However the vote passed.", '"Ask," he said.'],
)
def test_pronoun_continuation_and_quotation_openings_are_passed_over(unfit: str) -> None:
    dossier = _one_section(["The council met.", unfit, "Smith voted."], [1500, 100, 400])
    assert _pick(dossier) == "s1:2"


def test_a_section_where_no_paragraph_fits_is_left_out_whole() -> None:
    dossier = _one_section(["The council met.", "The mayor spoke."], [2100, 2100])
    assert _pick(dossier) is None
    assert "s1:0" not in pack.pack(dossier, 2000).budget.included_chunk_ids


def test_an_opening_repeating_a_shown_one_gives_way_to_the_next_paragraph() -> None:
    first = "Harbour Authority regulations cover every boat. " + "word " * 30
    other = "Harbour Authority regulations apply to every pilot. " + "term " * 30
    ids = ["a:0", "b:0", "b:1"]
    chunks = [
        prose("l0", [], 0, LEAD, 1.0),
        prose("a:0", ["A"], 10, first),
        prose("b:0", ["B"], 20, other),
        prose("b:1", ["B"], 21, "Pilots must register before any voyage. " + "name " * 30),
    ]
    sections = [
        section("s0", [], ["l0"]),
        section("a", ["A"], ids[:1]),
        section("b", ["B"], ids[1:]),
    ]
    dossier = dossier_of(sections, chunks)
    packer = _packer(dossier)
    packer.add_chunk(packer.chunk_by_id["a:0"])
    chosen = pick_representative(
        packer, packer.prose_of(packer.section_by_id["b"]), ShownOpenings.of(packer)
    )
    assert chosen is not None and chosen.id == "b:1"


def test_an_opening_made_of_words_the_lead_already_has_gives_way() -> None:
    echo = "Alpha Corporation builds river boats and sells them worldwide company."
    dossier = _one_section([echo, "Pilots must register before any voyage in the estuary."])
    assert _pick(dossier) == "s1:1"


def test_the_first_pick_stays_when_every_candidate_repeats_the_lead() -> None:
    echo = "Alpha Corporation builds river boats and sells them worldwide company."
    dossier = _one_section([echo, echo + " Again."])
    assert _pick(dossier) == "s1:0"


def _long_section(relevances: list[float]) -> Dossier:
    ids = [f"s1:{n}" for n in range(len(relevances))]
    chunks = [prose("l0", [], 0, LEAD, 1.0)]
    for n, relevance in enumerate(relevances):
        chunks.append(prose(ids[n], ["S1"], 10 + n, sized(f"Event{n} happened.", 150), relevance))
    return dossier_of([section("s0", [], ["l0"]), section("s1", ["S1"], ids)], chunks)


def test_the_late_passage_is_the_most_lead_similar_of_the_last_third() -> None:
    dossier = _long_section([0.2, 0.9, 0.3, 0.2, 0.2, 0.2, 0.3, 0.6, 0.4])
    included = _opened(dossier)
    assert "s1:7" in included
    assert "s1:1" not in included


def test_the_late_passage_of_a_top_section_comes_before_the_next_sections_opener() -> None:
    first = [
        prose(f"a:{n}", ["A"], 10 + n, sized(f"Alpha{n} began.", 150), 0.2 + 0.7 * (n == 2))
        for n in range(3)
    ]
    second = [prose("b:0", ["B"], 20, sized("Beta began.", 150), 0.1)]
    chunks = [prose("l0", [], 0, LEAD, 1.0), *first, *second]
    sections = [
        section("s0", [], ["l0"]),
        section("a", ["A"], [c.id for c in first]),
        section("b", ["B"], ["b:0"]),
    ]
    packer = Packer(dossier_of(sections, chunks), 2000, PackState(used=0), False)
    place_openers(packer)
    order = packer.state.included
    assert order.index("a:2") < order.index("b:0")


def test_the_lead_gets_its_late_passage_beyond_the_lead_share() -> None:
    ids = [f"l{n}" for n in range(6)]
    chunks = [
        prose(cid, [], n, sized(f"Lead{n} began.", 150), 0.9 if n == 4 else 0.3)
        for n, cid in enumerate(ids)
    ]
    packed = pack.pack(dossier_of([section("s0", [], ids)], chunks), 2000)
    assert "l4" in packed.budget.included_chunk_ids
