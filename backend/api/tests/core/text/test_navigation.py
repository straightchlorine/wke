"""Sentences that point at a table or map the passage does not carry."""

from __future__ import annotations

import pytest

from wke.core.text.navigation import points_elsewhere

POINTERS = [
    "Candidates are listed individually below if they received more than 0.1% of the vote.",
    "The results are shown in the table above.",
    "Red denotes states won by the Republican candidate.",
    "Light blue denotes states won by the Democratic candidate.",
]

PLAIN = [
    "The firm was listed on the stock exchange in 1998.",
    "The Red Army entered the city in 1945 after a long siege.",
    "She was given a new name by the monks.",
]


@pytest.mark.parametrize("sentence", POINTERS)
def test_pointer_to_a_table_or_map_is_navigation(sentence: str) -> None:
    assert points_elsewhere(sentence)


@pytest.mark.parametrize("sentence", PLAIN)
def test_ordinary_sentences_are_not_navigation(sentence: str) -> None:
    assert not points_elsewhere(sentence)
