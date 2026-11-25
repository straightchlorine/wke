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


def test_no_split_inside_an_open_double_quotation() -> None:
    text = 'He wrote: "It was late. Nobody came. We left." Then he slept.'
    assert split_sentences(text) == [
        'He wrote: "It was late. Nobody came. We left."',
        "Then he slept.",
    ]


def test_split_resumes_after_the_closing_quote() -> None:
    assert split_sentences('She said "I am done." Then she left. It was over.') == [
        'She said "I am done."',
        "Then she left.",
        "It was over.",
    ]


def test_curly_and_nested_quotes() -> None:
    text = (
        "He said \u201cShe told me \u201cgo home. Now.\u201d and I went. Later.\u201d "
        "Then it ended."
    )
    assert split_sentences(text) == [
        "He said \u201cShe told me \u201cgo home. Now.\u201d and I went. Later.\u201d",
        "Then it ended.",
    ]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            'He said "It was late. Nobody came. Then we left. The end.',
            ['He said "It was late.', "Nobody came.", "Then we left.", "The end."],
        ),
        (
            "He said \u201cIt was late. Nobody came. Then we left.",
            ["He said \u201cIt was late.", "Nobody came.", "Then we left."],
        ),
        (
            "It was late.\u201d Nobody came. Then we left.",
            ["It was late.\u201d", "Nobody came.", "Then we left."],
        ),
    ],
)
def test_unbalanced_quotes_fall_back_to_the_old_rule(text: str, expected: list[str]) -> None:
    assert split_sentences(text) == expected


def test_abbreviation_inside_a_quote() -> None:
    text = 'He said "Dr. Smith arrived. Mr. Jones left." Then it ended.'
    assert split_sentences(text) == [
        'He said "Dr. Smith arrived. Mr. Jones left."',
        "Then it ended.",
    ]


def test_apostrophes_do_not_open_a_quotation() -> None:
    text = "It was Tom\u2019s turn. The dogs\u2019 bowls were empty. He said 'no.' Then he left."
    assert split_sentences(text) == [
        "It was Tom\u2019s turn.",
        "The dogs\u2019 bowls were empty.",
        "He said 'no.'",
        "Then he left.",
    ]


@given(st.text(alphabet="ab. \"\u201c\u201d'?", max_size=60))
def test_joined_sentences_equal_the_text(text: str) -> None:
    text = " ".join(text.split())
    assert " ".join(split_sentences(text)) == text


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
