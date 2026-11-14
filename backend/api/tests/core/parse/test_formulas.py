"""Formulas stay in the text as their TeX source."""

from __future__ import annotations

import pytest

from tests.factories.parsed import LEAD, facts_lines, parse_sections, texts


def _inline(tex: str, via: str = "alt") -> str:
    wrapped = f"{{\\displaystyle {tex}}}"
    mathml = f"<span style='display: none;'><math alttext='{wrapped}'></math></span>"
    image = f"<img class='mwe-math-fallback-image-inline' alt='{wrapped}'/>"
    body = image if via == "alt" else mathml
    return f"<span class='mwe-math-element mwe-math-element-inline'>{body}</span>"


def test_inline_formula_is_kept_as_tex_from_the_image_alt() -> None:
    html = f"<p>The search ran in time {_inline('O(n\\log n)')} on average.</p>"
    assert texts(parse_sections(html))[0] == "The search ran in time O(n\\log n) on average."


def test_inline_formula_is_kept_as_tex_from_the_mathml_alttext() -> None:
    html = f"<p>The search ran in time {_inline('O(n)', via='mathml')} on average.</p>"
    assert texts(parse_sections(html))[0] == "The search ran in time O(n) on average."


def test_tex_with_angle_brackets_is_not_read_as_markup() -> None:
    html = f"<p>We require {_inline('a<b')} for every pair.</p>"
    assert texts(parse_sections(html))[0] == "We require a<b for every pair."


def test_formula_without_source_is_dropped() -> None:
    html = "<p>Where <span class='mwe-math-element'></span> is small it holds.</p>"
    assert texts(parse_sections(html))[0] == "Where is small it holds."


def test_infobox_row_holding_only_a_formula_is_left_out() -> None:
    rows = (
        f"<tr><th>Worst case</th><td>{_inline('O(V^2)')}</td></tr>"
        "<tr><th>Type</th><td>Search</td></tr>"
    )
    assert facts_lines(rows) == ["Type: Search"]


def test_infobox_row_with_a_formula_among_text_is_kept() -> None:
    rows = f"<tr><th>Space</th><td>{_inline('O(V)')} words</td></tr>"
    assert facts_lines(rows) == ["Space: O(V) words"]


def test_formula_picture_without_tex_becomes_a_placeholder() -> None:
    picture = "<span class='mwe-math-element'><img src='x.svg'/></span>"
    html = f"<p>The value {picture} is small and it holds.</p>"
    chunk = parse_sections(html).chunks[0]
    assert chunk.text == "The value [formula] is small and it holds."
    assert chunk.formulas == []


def test_inline_formula_is_a_formula_span() -> None:
    html = f"<p>The search ran in time {_inline('O(n)')} on average.</p>"
    chunk = parse_sections(html).chunks[0]
    assert [chunk.text[s.start : s.end] for s in chunk.formulas] == ["O(n)"]


def _block(tex: str) -> str:
    """Build a display equation as Parsoid renders it: a block span with MathML and an image."""
    wrapped = f"{{\\displaystyle {tex}}}"
    return (
        "<span class='mwe-math-element mwe-math-element-block' typeof='mw:Extension/math'>"
        "<span class='mwe-math-mathml-a11y' style='display: none;'>"
        f"<math display='block' alttext='{wrapped}'></math></span>"
        f"<img class='mwe-math-fallback-image-display' alt='{wrapped}'/></span>"
    )


# A display equation standing between paragraphs, in the older div form and
# in the current form of a paragraph that holds only a block span.
def _native(tex: str, block: bool = False) -> str:
    """Build a formula as native MathML: the math element itself, its TeX only in data-mw."""
    kind = "block' display='block" if block else "inline"
    data = f'{{"name":"math","attrs":{{}},"body":{{"extsrc":"{tex}"}}}}'
    return (
        f"<math class='mwe-math-element mwe-math-element-{kind}' typeof='mw:Extension/math'"
        f" data-mw='{data}'><mrow><mi>x</mi></mrow></math>"
    )


DISPLAY_FORMS = {
    "div": "<div class='mwe-math-element'><img alt='{\\displaystyle x=1}'/></div>",
    "paragraph": f"<p>{_block('x=1')}</p>",
    "indented-native": f"<div class='block-indent'>{_native('x=1', block=True)}</div>",
}


@pytest.mark.parametrize("block", DISPLAY_FORMS.values(), ids=DISPLAY_FORMS.keys())
def test_display_equation_is_a_formula_span(block: str) -> None:
    html = "<p>The value is defined as:</p>" + block + "<p>where x is one.</p>"
    chunk = parse_sections(LEAD, html).chunks[1]
    assert [chunk.text[s.start : s.end] for s in chunk.formulas] == ["x=1"]


@pytest.mark.parametrize("block", DISPLAY_FORMS.values(), ids=DISPLAY_FORMS.keys())
def test_display_equation_is_kept_between_the_paragraphs_around_it(block: str) -> None:
    html = "<p>The value is defined as:</p>" + block + "<p>where x is one.</p>"
    assert texts(parse_sections(LEAD, html))[1] == "The value is defined as: x=1 where x is one."


@pytest.mark.parametrize("block", DISPLAY_FORMS.values(), ids=DISPLAY_FORMS.keys())
def test_display_equation_with_no_text_before_it_is_left_out(block: str) -> None:
    assert texts(parse_sections(block + "<p>Then x is one.</p>")) == ["Then x is one."]


def test_display_equation_inside_a_paragraph_reads_in_line() -> None:
    html = f"<p>The identity is the equality {_block('x=1')} where x is one.</p>"
    chunk = parse_sections(LEAD, html).chunks[1]
    assert chunk.text == "The identity is the equality x=1 where x is one."
    assert [chunk.text[s.start : s.end] for s in chunk.formulas] == ["x=1"]


def test_display_equation_ending_a_paragraph_completes_its_sentence() -> None:
    html = f"<p>For x one then has {_block('x=1')}</p><p>Other prose follows here.</p>"
    assert (
        texts(parse_sections(LEAD, html))[1] == "For x one then has x=1 Other prose follows here."
    )


def test_native_inline_formula_is_kept_as_its_source_tex() -> None:
    html = f"<p>The search ran in time {_native('O(n)')} on average.</p>"
    chunk = parse_sections(html).chunks[0]
    assert chunk.text == "The search ran in time O(n) on average."
    assert [chunk.text[s.start : s.end] for s in chunk.formulas] == ["O(n)"]


def test_native_formula_without_source_becomes_a_placeholder() -> None:
    bare = "<math class='mwe-math-element mwe-math-element-inline'><mi>x</mi></math>"
    html = f"<p>The value {bare} is small and it holds.</p>"
    assert texts(parse_sections(html))[0] == "The value [formula] is small and it holds."


def test_mathml_outside_a_formula_element_is_dropped() -> None:
    html = "<p>The value <math><mi>x</mi></math> is small and it holds.</p>"
    assert texts(parse_sections(html))[0] == "The value is small and it holds."


def test_a_paragraph_ending_on_an_equation_without_a_full_stop_is_kept() -> None:
    html = f"<p>The probability that x lies below b is therefore {_block('P(x<b)=F(b)')}</p>"
    assert texts(parse_sections(LEAD, html))[1:] == [
        "The probability that x lies below b is therefore P(x<b)=F(b)"
    ]


def test_the_sentence_an_equation_continues_stays_in_its_chunk() -> None:
    # Both paragraphs are too long to merge by size or as a short tail.
    opening = "A full sentence of ordinary prose. " * 8 + "The norm is"
    rest = "where c is the hypotenuse. " + "Another full sentence of prose. " * 6
    html = f"<p>{opening} {_block('c^2=a^2+b^2')}</p><p>{rest}</p>"
    assert texts(parse_sections(LEAD, html))[1:] == [f"{opening} c^2=a^2+b^2 {rest.strip()}"]


def test_an_equation_set_in_a_paragraph_is_spaced_off_the_word_before() -> None:
    reference = "<sup class='reference'><a href='#n'>[1]</a></sup>"
    html = f"<p>The value is therefore{reference}{_block('x=1')} for every x.</p>"
    assert texts(parse_sections(LEAD, html))[1] == "The value is therefore x=1 for every x."


def test_multi_line_source_tex_reads_as_one_line() -> None:
    # data-mw holds JSON: the two characters backslash and n decode to a newline.
    html = f"<p>The system reads {_native('a=1\\nb=2', block=True)} for both.</p>"
    chunk = parse_sections(LEAD, html).chunks[1]
    assert chunk.text == "The system reads a=1 b=2 for both."
