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
