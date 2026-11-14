"""Sentence splitting and the sentence-end check shared by the parser, packer and checks."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from wke.core.text.sentences import ends_at_sentence_end, split_sentences


def test_split_sentences_only_at_real_ends() -> None:
    assert split_sentences("A is B (i.e. in the person of C). Then D.") == [
        "A is B (i.e. in the person of C).",
        "Then D.",
    ]
    assert split_sentences("Mary J. Blige sang. No. 1 hit. It is 5 p.m. today.") == [
        "Mary J. Blige sang.",
        "No. 1 hit.",
        "It is 5 p.m. today.",
    ]
    assert split_sentences('By J.R.R. Tolkien. He said: "Yes." Then left.') == [
        "By J.R.R. Tolkien.",
        'He said: "Yes."',
        "Then left.",
    ]
    assert split_sentences("Who? (Me.) Fine! 3 cats. lower case.") == [
        "Who?",
        "(Me.)",
        "Fine!",
        "3 cats. lower case.",
    ]
    assert split_sentences("") == []


@pytest.mark.parametrize(
    "text",
    ["He left.", "Why?", "Stop!", "It went on\u2026", 'He said "Yes."', "(It ended.)", "Done.  "],
)
def test_text_ending_with_a_sentence_end_mark_ends_at_a_sentence_end(text: str) -> None:
    assert ends_at_sentence_end(text)


@pytest.mark.parametrize("text", ["He left", "It cost 5", "He said: ", "", "Lists:"])
def test_text_without_a_final_mark_does_not(text: str) -> None:
    assert not ends_at_sentence_end(text)


@given(st.text(max_size=60))
def test_the_end_check_agrees_with_the_splitter(text: str) -> None:
    """A text ends at a sentence end exactly when its last sentence does.

    The two functions share one rule, so a text the splitter cuts short may
    never be reported as complete, nor the other way round.
    """
    sentences = split_sentences(text)
    if not sentences:
        assert not ends_at_sentence_end(text)
        return
    assert ends_at_sentence_end(text) is ends_at_sentence_end(sentences[-1])
