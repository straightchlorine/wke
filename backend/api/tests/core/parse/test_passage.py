"""Passages keep their link and formula spans through slicing, joining and sentence splits."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from wke.core.models import FormulaSpan, LinkSpan
from wke.core.parse.passage import Passage, join_passages

WORDS = st.sampled_from(["alpha", "beta", "x=1", "Gamma", "delta.", "Epsilon!", "zeta?"])


@st.composite
def passages(draw: st.DrawFn) -> Passage:
    """Draw a passage of words with links and formulas on whole words."""
    words = draw(st.lists(WORDS, min_size=1, max_size=8))
    text = " ".join(words)
    links: list[LinkSpan] = []
    formulas: list[FormulaSpan] = []
    start = 0
    for word in words:
        kind = draw(st.sampled_from(["plain", "link", "formula"]))
        if kind == "link":
            links.append(LinkSpan(start=start, end=start + len(word), title=word.title()))
        elif kind == "formula":
            formulas.append(FormulaSpan(start=start, end=start + len(word)))
        start += len(word) + 1
    return Passage(text, tuple(links), tuple(formulas))


def _covered(passage: Passage) -> list[str]:
    spans = sorted([*passage.links, *passage.formulas], key=lambda s: s.start)
    return [passage.text[s.start : s.end] for s in spans]


@given(st.lists(passages(), min_size=1, max_size=4))
def test_slicing_a_joined_passage_gives_back_each_part(parts: list[Passage]) -> None:
    joined = join_passages(parts)
    offset = 0
    for part in parts:
        assert joined.slice(offset, offset + len(part.text)) == part
        offset += len(part.text) + 1


@given(passages())
def test_sentences_rejoin_to_the_text_and_keep_every_span_inside_one(passage: Passage) -> None:
    sentences = passage.sentences()
    assert " ".join(s.text for s in sentences) == passage.text
    assert [text for s in sentences for text in _covered(s)] == _covered(passage)


def test_slice_drops_a_span_that_crosses_its_edge() -> None:
    link = LinkSpan(start=2, end=9, title="Cross")
    passage = Passage("A cross link.", (link,))
    assert passage.slice(0, 5).links == ()
    assert passage.slice(2, 13).links == (LinkSpan(start=0, end=7, title="Cross"),)


@pytest.mark.parametrize(
    ("passage", "ends"),
    [
        (Passage("It holds."), True),
        (Passage('He said "no."'), True),
        (Passage("It holds"), False),
        (Passage("It is x=1", formulas=(FormulaSpan(start=6, end=9),)), True),
        (Passage("If x=1 then", formulas=(FormulaSpan(start=3, end=6),)), False),
    ],
    ids=["full-stop", "stop-inside-quote", "no-end", "ends-with-formula", "formula-inside"],
)
def test_ends_sentence(passage: Passage, ends: bool) -> None:
    assert passage.ends_sentence() is ends


# Whitespace a passage may carry after its last mark: ends_at_sentence_end
# ignores all of it, so ends_sentence must ignore it too.
WHITESPACE = [" ", "  ", "\t", "\n", "\n\n", "\r\n", "\u00a0", "\u2009", "\u3000"]


@pytest.mark.parametrize(
    "space",
    WHITESPACE,
    ids=["space", "spaces", "tab", "nl", "nls", "crlf", "nbsp", "thin", "ideographic"],
)
def test_ends_sentence_ignores_trailing_whitespace(space: str) -> None:
    assert Passage(f"It holds.{space}").ends_sentence() is True
    assert Passage(f'He said "no."{space}').ends_sentence() is True
    assert Passage(f"It went on\u2026{space}").ends_sentence() is True
    assert Passage(f"It holds.{space}Then").ends_sentence() is False


def test_a_formula_at_the_end_counts_even_with_trailing_whitespace() -> None:
    span = FormulaSpan(start=6, end=9)
    assert Passage("It is x=1", formulas=(span,)).ends_sentence() is True
    assert Passage("It is x=1 ", formulas=(span,)).ends_sentence() is True
    assert Passage("It is x=1\n", formulas=(span,)).ends_sentence() is True


def test_an_empty_passage_ends_at_nothing() -> None:
    assert Passage("").ends_sentence() is False
    assert Passage("   ").ends_sentence() is False


@given(st.text(max_size=40), st.sampled_from(WHITESPACE))
def test_trailing_whitespace_never_decides_how_a_passage_ends(text: str, space: str) -> None:
    """Appending whitespace may not change either boundary verdict."""
    assert Passage(text + space).ends_sentence() is Passage(text).ends_sentence()
    assert Passage(text + space).ends_intro() is Passage(text).ends_intro()


@pytest.mark.parametrize(
    ("passage", "intro"),
    [
        (Passage("The parts are:"), True),
        (Passage("The parts are: "), True),
        (Passage("The parts are:\n"), True),
        (Passage("The parts are"), False),
        (Passage("The parts are;"), False),
        (Passage(""), False),
    ],
    ids=["colon", "colon-space", "colon-newline", "no-colon", "semicolon", "empty"],
)
def test_ends_intro(passage: Passage, intro: bool) -> None:
    assert passage.ends_intro() is intro
