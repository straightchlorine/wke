"""Formulas stay TeX in the chunk text and read as inline code in the Markdown."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.factories.dossier import make_freshness, make_links
from tests.factories.synthetic import dossier_of, prose, section
from wke.core import render
from wke.core.models import Chunk, FormulaSpan, LinkSpan
from wke.core.parse import parse_html
from wke.core.render.inline import code_span, inline_markup
from wke.core.render.quote import quote

SYNTHETIC = Path(__file__).parent.parent.parent / "fixtures" / "synthetic"


def _chunks(name: str, wrapper: str = "{}") -> list[Chunk]:
    body = wrapper.format((SYNTHETIC / name).read_text(encoding="ascii"))
    html = f"<html><body><section data-mw-section-id='0'>{body}</section></body></html>"
    return parse_html(html, 1, "c1").chunks


def test_code_span_outgrows_a_backtick_run_in_the_tex() -> None:
    assert code_span("a``b") == "```a``b```"
    assert code_span("`x") == "`` `x ``"


def test_inline_markup_writes_formulas_as_code_and_escapes_the_rest() -> None:
    text = "Take [x] and x_{1} here."
    formula = FormulaSpan(start=text.index("x_"), end=text.index(" here"))
    assert inline_markup(text, [], [formula]) == "Take \\[x\\] and `x_{1}` here."


def test_a_link_beside_a_formula_stays_a_link_and_one_across_it_is_left_out() -> None:
    text = "See cats and a_b or dogs."
    formula = FormulaSpan(start=text.index("a_b"), end=text.index(" or"))
    beside = LinkSpan(start=4, end=8, title="Cat")
    across = LinkSpan(start=text.index("and"), end=text.index(" or"), title="Mix")
    marked = inline_markup(text, [beside, across], [formula], "https://en.wikipedia.org")
    assert marked == "See [cats](https://en.wikipedia.org/wiki/Cat) and `a_b` or dogs."


def test_general_relativity_paragraph_keeps_tex_in_text_and_code_in_markdown() -> None:
    chunk = _chunks("general_relativity_formulas.html")[0]
    assert "\\kappa is a constant and T_{\\mu \\nu } is the stress" in chunk.text
    lines = quote(chunk, chunk.text)
    assert (
        "> On the right-hand side, `\\kappa` is a constant and `T_{\\mu \\nu }` is the" in lines[0]
    )


def test_dijkstra_paragraph_formula_is_code() -> None:
    chunk = _chunks("dijkstra_formulas.html")[0]
    assert [chunk.text[s.start : s.end] for s in chunk.formulas] == ["|V|^{2}"]
    assert "fewer than `|V|^{2}` edges" in quote(chunk, chunk.text)[0]


def test_dijkstra_infobox_row_with_only_a_formula_is_not_a_fact() -> None:
    row = (SYNTHETIC / "dijkstra_infobox_row.html").read_text(encoding="ascii")
    other = "<tr><th class='infobox-label'>Class</th><td class='infobox-data'>Search</td></tr>"
    table = f"<table class='infobox'><tbody>{row}{other}</tbody></table>"
    lead = "<p>The lead is a real sentence about the topic.</p>"
    html = f"<html><body><section data-mw-section-id='0'>{table}{lead}</section></body></html>"
    facts = [c.text for c in parse_html(html, 1, "c1").chunks if c.kind == "facts"]
    assert facts == ["Class: Search"]


def test_the_view_clips_a_formula_past_a_cut_passage() -> None:
    text = "First sentence about the topic. " * 300 + "The cost is O(n) overall."
    start = text.index("O(n)")
    chunk = prose("l0", [], 0, text, 1.0, formulas=[FormulaSpan(start=start, end=start + 4)])
    dossier = dossier_of([section("s0", [], ["l0"])], [chunk])
    whole = render.build_view(dossier, 32000, make_freshness(dossier), make_links(dossier), False)
    assert whole.chunks[0].formulas == chunk.formulas
    cut = render.build_view(dossier, 2000, make_freshness(dossier), make_links(dossier), False)
    assert len(cut.chunks[0].text) < start
    assert cut.chunks[0].formulas == []


@pytest.mark.parametrize("links", [False, True])
def test_markdown_of_a_built_dossier_shows_the_formula_as_code(links: bool) -> None:
    text = "The cost is O(n) overall."
    chunk = prose("l0", [], 0, text, 1.0, formulas=[FormulaSpan(start=12, end=16)])
    dossier = dossier_of([section("s0", [], ["l0"])], [chunk])
    view = render.build_view(dossier, 32000, make_freshness(dossier), make_links(dossier), False)
    assert "> The cost is `O(n)` overall." in render.render_markdown(view, False, links)
    assert view.chunks[0].text == text
