"""Content tokens, opening keys, overlap and the named-subject test of a passage."""

from __future__ import annotations

import pytest

from wke.core.text.openings import (
    content_tokens,
    has_named_subject,
    opening_key,
    overlap_with,
)


def test_content_tokens_drop_stopwords_and_keep_numbers() -> None:
    assert content_tokens("The Battle of 1942 was in Stalingrad") == [
        "battle",
        "1942",
        "stalingrad",
    ]


def test_opening_key_is_the_first_three_content_tokens() -> None:
    assert opening_key("The Red Army launched a new offensive") == ("red", "army", "launched")
    assert opening_key("It was") == ()


def test_overlap_is_the_share_of_distinct_tokens_found_in_the_reference() -> None:
    reference = {"red", "army", "city"}
    assert overlap_with("Red Army city", reference) == 1.0
    assert overlap_with("Red Army winter attack", reference) == 0.5
    assert overlap_with("the of", reference) == 0.0


@pytest.mark.parametrize(
    "text",
    [
        "The council met on Friday.",
        "Turing studied at King's College.",
        "In 1942 the army advanced.",
    ],
)
def test_a_passage_with_a_named_subject_can_start_a_section(text: str) -> None:
    assert has_named_subject(text)


@pytest.mark.parametrize(
    "text",
    [
        "He studied at King's College.",
        "It was built in 1900.",
        "This led to a ban.",
        "Later, the army advanced.",
        "Then the army advanced.",
        "However, the army stayed.",
        '"Ask not," he said.',
        "\u201cAsk not,\u201d he said.",
        "- Ask not what your country can do.",
        "\u2014 Ask not what your country can do.",
        "",
    ],
)
def test_pronouns_continuations_and_quotations_cannot_start_a_section(text: str) -> None:
    assert not has_named_subject(text)
