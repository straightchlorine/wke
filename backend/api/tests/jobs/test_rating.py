"""Repacking a dossier under the model rating: rank map, non-prose relevance, summaries."""

from __future__ import annotations

import pytest

from tests.factories.dossier import make_fixture_dossier
from wke.core.models import Dossier
from wke.jobs.build import constants
from wke.jobs.build.rating import (
    RatingConfig,
    RatingDocument,
    apply_rating,
    parse_document,
    rank_map,
    ranks_of,
    rating_key,
    rating_lock_key,
)
from wke.settings import Settings

LEAD = "1382805013:lead:0"
EARLY0 = "1382805013:early_life:0"
EARLY1 = "1382805013:early_life:1"
CAREER0 = "1382805013:career:0"
CAREER1 = "1382805013:career:1"
LEGACY = "1382805013:legacy:0"
TABLE = "1382805013:career:table0"
FACTS = "1382805013:lead:facts"
# Stored prose relevance, ascending: 0.4 0.5 0.6 0.9 0.95 1.0.
SCORES: dict[str, float | None] = {
    LEAD: 1.0,
    EARLY0: 3.0,
    EARLY1: 0.0,
    CAREER0: 2.0,
    CAREER1: None,
    LEGACY: 3.0,
}


def _relevance(dossier: Dossier) -> dict[str, float]:
    return {c.id: c.relevance for c in dossier.chunks}


def test_ranks_are_zero_based_and_ties_share_the_mean_rank() -> None:
    assert ranks_of({"a": 0.2, "b": 0.9, "c": 0.2, "d": 0.5}) == {
        "a": 0.5,
        "c": 0.5,
        "d": 2.0,
        "b": 3.0,
    }


def test_rank_map_gives_the_order_of_the_values_the_level_and_spread_of_the_stored_ones() -> None:
    mapped = rank_map({"a": 0.9, "b": 0.1, "c": 0.5}, {"a": 0.2, "b": 0.8, "c": 0.5})

    assert mapped == pytest.approx({"b": 0.2, "c": 0.5, "a": 0.8})


def test_rank_map_interpolates_a_tie_between_two_stored_positions() -> None:
    mapped = rank_map({"a": 1.0, "b": 1.0, "c": 0.0}, {"a": 0.2, "b": 0.4, "c": 0.8})

    assert mapped == pytest.approx({"c": 0.2, "a": 0.4 + 0.5 * 0.4, "b": 0.4 + 0.5 * 0.4})


# Written out from the lab's selection.quantile_map (docs/research/2026-11-18-recipe/selection.py):
# (values, stored relevance, mapped), an odd count with ties, one passage, an even count, all tied.
LAB_RANK_MAPS = [
    (
        {"a": 0.2, "b": 0.9, "c": 0.2, "d": 0.5, "e": 0.9},
        {"a": 0.31, "b": 0.62, "c": 0.4, "d": 0.95, "e": 0.5},
        {"a": 0.355, "b": 0.785, "c": 0.355, "d": 0.5, "e": 0.785},
    ),
    ({"a": 2.0}, {"a": 0.37}, {"a": 0.37}),
    (
        {"a": 1.0, "b": 3.0, "c": 2.0, "d": 0.0},
        {"a": 0.8, "b": 0.1, "c": 0.5, "d": 0.65},
        {"a": 0.5, "b": 0.8, "c": 0.65, "d": 0.1},
    ),
    (
        {"a": 1.0, "b": 1.0, "c": 1.0},
        {"a": 0.2, "b": 0.4, "c": 0.9},
        {"a": 0.4, "b": 0.4, "c": 0.4},
    ),
]


@pytest.mark.parametrize(("values", "stored", "mapped"), LAB_RANK_MAPS)
def test_rank_map_equals_the_labs(
    values: dict[str, float], stored: dict[str, float], mapped: dict[str, float]
) -> None:
    assert rank_map(values, stored) == pytest.approx(mapped, abs=1e-12)


def test_rank_map_of_one_passage_is_its_stored_relevance() -> None:
    assert rank_map({"a": 3.0}, {"a": 0.37}) == {"a": 0.37}


def test_the_rating_replaces_the_prose_relevance_by_rank() -> None:
    repacked = apply_rating(make_fixture_dossier(), SCORES, summary_sections=8)

    assert repacked is not None
    # Scores / 3, the missing one filled by the mean 1.8 / 3: 0.33 1.0 0.0 0.67 0.6 1.0.
    assert _relevance(repacked) == pytest.approx(
        {
            EARLY1: 0.4,
            LEAD: 0.5,
            CAREER1: 0.6,
            CAREER0: 0.9,
            EARLY0: 0.975,
            LEGACY: 0.975,
            FACTS: 1.0,
            TABLE: (15 * 0.9 + 12 * 0.6) / 27,
        }
    )


def test_a_passage_without_a_score_takes_the_mean_of_the_others_before_the_division() -> None:
    scores: dict[str, float | None] = {
        LEAD: 3.0,
        EARLY0: 3.0,
        EARLY1: 0.0,
        CAREER0: 0.0,
        CAREER1: None,
        LEGACY: 3.0,
    }

    repacked = apply_rating(make_fixture_dossier(), scores, summary_sections=8)

    assert repacked is not None
    rel = _relevance(repacked)
    # The mean is 1.8, so None ranks between the two 0.0 passages and the three 3.0 ones.
    assert rel[CAREER1] == pytest.approx(0.6)
    assert rel[EARLY1] == rel[CAREER0] == pytest.approx(0.45)
    assert rel[LEAD] == rel[EARLY0] == rel[LEGACY] == pytest.approx(0.95)


def test_without_any_score_every_passage_ties() -> None:
    repacked = apply_rating(make_fixture_dossier(), dict.fromkeys(SCORES), summary_sections=8)

    assert repacked is not None
    prose = [c.relevance for c in repacked.chunks if c.kind == "prose"]
    assert prose == pytest.approx([0.75] * 6)


def test_the_apply_leaves_the_stored_dossier_unchanged() -> None:
    dossier = make_fixture_dossier()
    before = dossier.model_dump_json()

    apply_rating(dossier, SCORES, summary_sections=1)

    assert dossier.model_dump_json() == before


def test_table_and_facts_relevance_and_section_importance_are_recomputed() -> None:
    dossier = make_fixture_dossier()

    repacked = apply_rating(dossier, SCORES, summary_sections=8)

    assert repacked is not None
    assert _relevance(repacked)[FACTS] == 1.0
    assert all(s.importance > 0 for s in repacked.sections)
    assert all(s.importance == 0.0 for s in dossier.sections)


def test_summaries_of_sections_the_selection_no_longer_picks_are_dropped() -> None:
    repacked = apply_rating(make_fixture_dossier(), SCORES, summary_sections=1)

    assert repacked is not None
    by_id = {s.id: s for s in repacked.sections}
    # One summary section is chosen; the stored "done" and "unavailable" sections not chosen
    # are skipped, a "pending" section keeps its state.
    kept = [s for s in (by_id["s1"], by_id["s3"]) if s.summary_state != "skipped"]
    assert len(kept) <= 1
    for section in (by_id["s1"], by_id["s3"]):
        if section.summary_state == "skipped":
            assert section.summary is None
            assert section.withheld_reason is None
    assert by_id["s2"].summary_state == "pending"
    assert by_id["s0"].summary_state == "skipped"
    assert repacked.build.summaries_done == 1  # as stored


def test_all_sections_keep_their_summaries_when_the_setting_allows_them_all() -> None:
    dossier = make_fixture_dossier()

    repacked = apply_rating(dossier, SCORES, summary_sections=8)

    assert repacked is not None
    assert [s.summary_state for s in repacked.sections] == [
        s.summary_state for s in dossier.sections
    ]


@pytest.mark.parametrize(
    "scores",
    [
        {k: v for k, v in SCORES.items() if k != LEGACY},
        {**SCORES, "1382805013:other:0": 1.0},
        {**{k: v for k, v in SCORES.items() if k != LEGACY}, FACTS: 1.0},
        {},
    ],
    ids=["missing", "extra", "facts_instead_of_prose", "empty"],
)
def test_scores_for_other_ids_than_the_prose_chunks_apply_nothing(
    scores: dict[str, float | None],
) -> None:
    assert apply_rating(make_fixture_dossier(), scores, summary_sections=8) is None


def test_a_document_is_read_only_under_the_current_prompt_and_model() -> None:
    document = RatingDocument(
        prompt_sha256=constants.RATING_PROMPT_SHA256,
        model=constants.RATING_MODEL,
        done=True,
        scores={"a": 1.0, "b": None},
    )

    assert parse_document(document.model_dump_json()) == document
    assert parse_document(None) is None
    assert parse_document("not json") is None
    assert parse_document('{"done": true}') is None
    other_prompt = document.model_copy(update={"prompt_sha256": "0" * 64})
    assert parse_document(other_prompt.model_dump_json()) is None
    other_model = document.model_copy(update={"model": "other"})
    assert parse_document(other_model.model_dump_json()) is None


def test_the_keys_carry_the_prompt_hash_prefix_and_the_model() -> None:
    prompt12 = constants.RATING_PROMPT_SHA256[:12]

    assert rating_key(7, 9, "pv") == f"rating:7:9:pv:{prompt12}:gemma4-e4b"
    assert rating_lock_key(7, 9, "pv") == f"rate:lock:7:9:pv:{prompt12}:gemma4-e4b"


def test_the_constants_are_the_measured_prompt_and_model() -> None:
    assert constants.RATING_PROMPT_SHA256 == (
        "f68afeb2bc1aaf3734cdeb0127500589966f47fbb7b74c20a004941e69bc6ec7"
    )
    assert constants.RATING_MODEL == "gemma4-e4b"
    assert constants.RATING_MODEL_FILE == "gemma-4-E4B-it-Q4_K_M.gguf"
    assert (constants.RATING_CALL_ATTEMPTS, constants.RATING_RETRY_PAUSE_SECONDS) == (3, 5)


def test_the_config_is_off_by_default_and_reads_the_settings(settings: Settings) -> None:
    assert RatingConfig().enabled is False
    assert RatingConfig.from_settings(settings) == RatingConfig(False, 1800, 120, 8, 0.9, 3, 60)

    settings.selection_rating = True
    settings.rating_deadline_seconds = 60
    settings.rating_call_timeout_seconds = 30
    settings.summary_sections = 3
    settings.rating_min_coverage = 0.5
    settings.rating_max_attempts = 2
    settings.rating_retry_backoff_seconds = 7

    assert RatingConfig.from_settings(settings) == RatingConfig(True, 60, 30, 3, 0.5, 2, 7)


def test_a_rating_with_few_real_scores_applies_nothing() -> None:
    dossier = make_fixture_dossier()
    ids = [c.id for c in dossier.chunks if c.kind == "prose"]
    scores: dict[str, float | None] = {i: None for i in ids}
    scores[ids[0]] = 3.0

    assert apply_rating(dossier, scores, 8, min_coverage=0.9) is None
    assert apply_rating(dossier, scores, 8, min_coverage=1 / len(ids)) is not None


def test_the_coverage_is_the_share_of_prose_passages_with_a_real_score() -> None:
    dossier = make_fixture_dossier()
    ids = [c.id for c in dossier.chunks if c.kind == "prose"]
    scores: dict[str, float | None] = {i: 2.0 for i in ids}
    scores[ids[0]] = None  # 5 of 6 passages hold a score

    assert apply_rating(dossier, scores, 8, min_coverage=0.8) is not None
    assert apply_rating(dossier, scores, 8, min_coverage=0.9) is None
    assert apply_rating(dossier, {i: 2.0 for i in ids}, 8, min_coverage=1.0) is not None
