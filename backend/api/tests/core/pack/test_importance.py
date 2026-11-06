"""Section importance: similarity to the lead, size, position and an outcome heading."""

from __future__ import annotations

import pytest

from tests.factories.packing import make_chunk, make_section
from tests.factories.synthetic import dossier_of
from wke.core import pack
from wke.core.models import Dossier
from wke.core.pack.importance import u_position


def _three_sections() -> Dossier:
    sections = [
        make_section("s0", [], ["l0"]),
        make_section("s1", ["S1"], ["a"]),
        make_section("s2", ["S2"], ["b"]),
    ]
    chunks = [
        make_chunk("l0", [], 0, 50, 1.0),
        make_chunk("a", ["S1"], 1, 100, 0.4),
        make_chunk("b", ["S2"], 2, 200, 0.8),
    ]
    return dossier_of(sections, chunks)


def test_importance_is_half_similarity_three_tenths_size_one_fifth_position() -> None:
    dossier = _three_sections()
    scores = pack.section_importance(dossier.sections, dossier.chunks)
    assert scores == pytest.approx({"s0": 0.775, "s1": 0.45, "s2": 0.9})


def test_ranking_leaves_out_the_lead_and_puts_the_most_important_first() -> None:
    dossier = _three_sections()
    ranked = pack.ranked_sections(dossier.sections, dossier.chunks)
    assert [s.id for s in ranked] == ["s2", "s1"]


def test_a_long_table_counts_for_a_fixed_number_of_tokens_when_sections_are_sized() -> None:
    sections = [
        make_section("s0", [], ["l0"]),
        make_section("s1", ["S1"], ["a"]),
        make_section("s2", ["S2"], ["t"]),
    ]
    chunks = [
        make_chunk("l0", [], 0, 10, 1.0),
        make_chunk("a", ["S1"], 1, 600, 0.5),
        make_chunk("t", ["S2"], 2, 5000, 0.5, "table"),
    ]
    scores = pack.section_importance(sections, chunks)
    # similarity 0.5, size 300 of 600 (the table is capped), position 1.0
    assert scores["s2"] == pytest.approx(0.5 * 0.5 + 0.3 * 0.5 + 0.2 * 1.0)


def _late_section(heading: str, headed: int = 9) -> Dossier:
    """A lead plus nine similar-sized sections; the last one is lead-similar.

    Args:
        heading: the label of the section at index `headed`.
        headed: which section gets that label.

    Returns:
        Dossier: the lead and sections s1..s9.
    """
    sections = [make_section("s0", [], ["l0"])]
    chunks = [make_chunk("l0", [], 0, 100, 1.0)]
    for i in range(1, 10):
        last = i == 9
        section = make_section(f"s{i}", [f"S{i}"], [f"s{i}:0"])
        sections.append(section.model_copy(update={"label": heading if i == headed else f"S{i}"}))
        chunks.append(make_chunk(f"s{i}:0", [f"S{i}"], 10 * i, 120, 0.8 if last else 0.3))
    return dossier_of(sections, chunks)


def test_a_lead_similar_last_section_ranks_in_the_top_three() -> None:
    dossier = _late_section("Background")
    ranked = pack.ranked_sections(dossier.sections, dossier.chunks)
    assert "s9" in [s.id for s in ranked[:3]]


def test_an_outcome_heading_adds_a_quarter_to_the_score_which_stays_within_one() -> None:
    plain = pack.section_importance(*_parts(_late_section("Background", headed=4)))
    outcome = pack.section_importance(*_parts(_late_section("Death", headed=4)))
    assert plain["s4"] < 0.75
    assert outcome["s4"] - plain["s4"] == pytest.approx(0.25)
    capped = pack.section_importance(*_parts(_late_section("Death")))
    assert capped["s9"] == 1.0


def _parts(dossier: Dossier):
    return dossier.sections, dossier.chunks


@pytest.mark.parametrize(
    ("index", "count", "score"), [(0, 10, 1.0), (9, 10, 1.0), (4, 9, 0.5), (0, 1, 1.0)]
)
def test_the_position_prior_is_high_at_both_ends_and_half_in_the_middle(
    index: int, count: int, score: float
) -> None:
    assert u_position(index, count) == pytest.approx(score)
