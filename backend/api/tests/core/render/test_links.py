"""Link spans of a passage written as Markdown links on its verbatim text."""

from __future__ import annotations

import re

from tests.factories.dossier import FACTORY_TITLE, make_freshness, make_links
from tests.factories.synthetic import dossier_of, prose, section
from wke.core import render
from wke.core.models import Chunk, Dossier, LinkSpan
from wke.core.models.budgets import BUDGETS, BudgetTokens
from wke.core.render.markdown import content_text
from wke.core.text.tokens import est_tokens

TEXT = "Turing studied at King's College, Cambridge and worked at Bletchley Park on Mercury."
SPANS = [
    LinkSpan(start=TEXT.index("King's"), end=TEXT.index(" and"), title="King's College, Cambridge"),
    LinkSpan(start=TEXT.index("Bletchley"), end=TEXT.index(" on"), title="Bletchley Park"),
    LinkSpan(start=TEXT.index("Mercury"), end=len(TEXT) - 1, title="Mercury (planet)"),
]
LINK = re.compile(r"\[((?:\\.|[^\]\\])*)\]\((https://[^)\s]*)\)")


def _dossier(links: list[LinkSpan]) -> Dossier:
    chunk = prose("l0", [], 0, TEXT, 1.0, links)
    return dossier_of([section("s0", [], ["l0"])], [chunk])


def _markdown(dossier: Dossier, budget: BudgetTokens = 32000, links: bool = True) -> str:
    view = render.build_view(dossier, budget, make_freshness(dossier), make_links(dossier), False)
    return render.render_markdown(view, False, links)


def test_each_link_text_is_the_verbatim_substring_of_the_passage() -> None:
    found = LINK.findall(_markdown(_dossier(SPANS)))
    assert [text for text, _ in found] == [TEXT[s.start : s.end] for s in SPANS]


def test_targets_are_wikipedia_pages_with_parentheses_encoded() -> None:
    urls = [url for _, url in LINK.findall(_markdown(_dossier(SPANS)))]
    assert urls == [
        "https://en.wikipedia.org/wiki/King's_College,_Cambridge",
        "https://en.wikipedia.org/wiki/Bletchley_Park",
        "https://en.wikipedia.org/wiki/Mercury_%28planet%29",
    ]


def test_without_the_link_markup_the_passage_reads_as_the_verbatim_text() -> None:
    quoted = next(ln for ln in _markdown(_dossier(SPANS)).splitlines() if ln.startswith("> Turing"))
    assert LINK.sub(lambda m: m.group(1), quoted)[2:] == TEXT


def test_citations_and_sources_are_the_same_with_and_without_links() -> None:
    linked = _markdown(_dossier(SPANS))
    plain = _markdown(_dossier([]))
    assert linked.split("## Sources")[1] == plain.split("## Sources")[1]
    assert re.findall(r"^\[c\d+\]$", linked, re.M) == re.findall(r"^\[c\d+\]$", plain, re.M)


def test_markup_inside_link_text_stays_escaped() -> None:
    text = "See the <b> tag page for details."
    span = LinkSpan(start=4, end=11, title="B tag")
    dossier = dossier_of([section("s0", [], ["l0"])], [prose("l0", [], 0, text, 1.0, [span])])
    assert LINK.findall(_markdown(dossier)) == [
        ("the \\<b\\>", "https://en.wikipedia.org/wiki/B_tag")
    ]


def test_the_view_keeps_the_spans_and_clips_those_past_a_cut_passage() -> None:
    head = "First sentence about the topic. " * 300
    tail = " Last sentence names Bletchley Park."
    text = head + tail.strip()
    span = LinkSpan(start=len(text) - 14, end=len(text) - 1, title="Bletchley Park")
    early = LinkSpan(start=0, end=5, title="First")
    dossier = dossier_of(
        [section("s0", [], ["l0"])], [prose("l0", [], 0, text, 1.0, [early, span])]
    )
    whole = render.build_view(dossier, 32000, make_freshness(dossier), make_links(dossier), False)
    assert whole.chunks[0].links == [early, span]
    assert whole.chunks[0].text == text
    cut = render.build_view(dossier, 2000, make_freshness(dossier), make_links(dossier), False)
    assert len(cut.chunks[0].text) < len(text)
    assert cut.chunks[0].links == [early]


def test_links_are_off_by_default_and_not_charged_to_the_budget() -> None:
    sentence = "Turing and Church studied computability at Princeton University in 1936. "
    text = sentence * 60
    spans = [
        LinkSpan(start=i * len(sentence), end=i * len(sentence) + 6, title=FACTORY_TITLE)
        for i in range(60)
    ]
    chunks: list[Chunk] = [prose("l0", [], 0, text.strip(), 1.0, spans)]
    dossier = dossier_of([section("s0", [], ["l0"])], chunks)
    for budget in BUDGETS:
        view = render.build_view(
            dossier, budget, make_freshness(dossier), make_links(dossier), False
        )
        plain, _ = content_text(view, False)
        linked = render.render_markdown(view, False, True)
        assert not LINK.search(plain)
        assert est_tokens(plain) <= budget
        assert view.budget.used_est_tokens == est_tokens(plain)
        assert "inline links are not counted in the budget" in linked
        assert "inline links" not in plain
