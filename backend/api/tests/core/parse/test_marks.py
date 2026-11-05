"""Link and formula marks read back as spans, including the marks that make no span."""

from __future__ import annotations

from wke.core.models import FormulaSpan, LinkSpan
from wke.core.parse.formulas import FORMULA_END, FORMULA_START
from wke.core.parse.links import LINK_END, LINK_START_BASE
from wke.core.parse.marks import read_marked

OPEN = chr(LINK_START_BASE)


def test_marks_become_spans_on_the_text_without_marks() -> None:
    passage = read_marked(f"A {OPEN}cat{LINK_END} ate {FORMULA_START}x=1{FORMULA_END}.", ["Cat"])
    assert passage.text == "A cat ate x=1."
    assert passage.links == (LinkSpan(start=2, end=5, title="Cat"),)
    assert passage.formulas == (FormulaSpan(start=10, end=13),)


def test_a_space_inside_a_mark_pair_stays_out_of_the_span() -> None:
    passage = read_marked(f"the capital{OPEN} city {LINK_END} here", ["City"])
    assert passage.text == "the capital city here"
    assert passage.links == (LinkSpan(start=12, end=16, title="City"),)


def test_a_space_inside_the_last_link_leaves_no_trailing_space() -> None:
    passage = read_marked(f"A {OPEN}cat {LINK_END}", ["Cat"])
    assert passage.text == "A cat"
    assert passage.links == (LinkSpan(start=2, end=5, title="Cat"),)


def test_marks_around_nothing_or_out_of_order_make_no_span() -> None:
    marked = (
        f"An {OPEN} {LINK_END}empty{LINK_END} link{FORMULA_END}"
        f" and{FORMULA_START}{FORMULA_END} more."
    )
    passage = read_marked(marked, ["Empty"])
    assert passage.text == "An empty link and more."
    assert passage.links == () and passage.formulas == ()


def test_a_mark_with_no_title_makes_no_span() -> None:
    passage = read_marked(f"A {chr(LINK_START_BASE + 3)}cat{LINK_END}.", ["Cat"])
    assert passage.links == ()


def test_text_that_marks_kept_apart_is_cleaned_and_its_spans_dropped() -> None:
    # The mark sat between a letter and its combining accent, which NFC then joins.
    passage = read_marked(f"Caf{OPEN}e{LINK_END}\u0301 noir", ["Cafe"])
    assert passage.text == "Caf\u00e9 noir"
    assert passage.links == ()
