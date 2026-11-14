"""The hard fidelity rules, through the summary gate."""

from __future__ import annotations

import pytest

from tests.factories.summaries import DEFECTIVE_SUMMARIES
from wke.core.summaries.check import check_summary

_LANDER_SOURCE = "In April 2021, SpaceX was selected by NASA to develop a lunar lander."


@pytest.mark.parametrize("name", DEFECTIVE_SUMMARIES)
def test_gate_withholds_the_defect(name: str) -> None:
    summary, source, expected = DEFECTIVE_SUMMARIES[name]
    reason = check_summary(summary, source)
    assert reason is not None
    assert expected in reason


def test_faithful_condensation_passes() -> None:
    source = (
        "In April 2021, NASA selected SpaceX to develop a modified Starship spacecraft as a "
        "lunar lander. The first crewed landing is planned for later in the decade."
    )
    summary = "NASA selected SpaceX to develop a modified Starship spacecraft as a lunar lander ."
    assert check_summary(summary, source) is None


def test_passive_source_sentence_backs_the_active_summary() -> None:
    summary = "NASA selected SpaceX to develop a lunar lander ."
    assert check_summary(summary, _LANDER_SOURCE) is None


def test_role_evidence_drops_a_leading_function_word() -> None:
    reason = check_summary("When SpaceX selected NASA to develop a lunar lander .", _LANDER_SOURCE)
    assert reason == (
        "a sentence says 'SpaceX selected NASA' but the source never has them in that order"
    )


def test_closing_space_before_full_stop_is_not_a_glitch() -> None:
    source = "Limonene is a colourless liquid hydrocarbon found in citrus peel oils."
    assert check_summary("Limonene is a liquid hydrocarbon .", source) is None


def test_attributed_quotation_is_narration_not_a_lift() -> None:
    source = (
        "Nigella said that she would never again cook anything that takes more than an hour "
        "to prepare."
    )
    summary = "Nigella said she would never again cook anything that takes more than an hour ."
    assert check_summary(summary, source) is None


def test_heading_year_may_sit_with_other_words_than_in_the_source() -> None:
    source = "The club moved to a new ground in 1999. It won the league with a young squad."
    summary = "The club won the league in 1999 with a young squad ."
    assert check_summary(summary, source) is not None
    assert check_summary(summary, source, heading="1999") is None
