"""Link spans cover exactly the text of their anchor, whatever markup surrounds it."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from tests.factories.parsed import CITATION_ID, REV_ID, link_spans, parse_sections
from tests.support.constants import SYNTHETIC_DIR
from wke.core.parse import parse_html
from wke.core.text.clean import clean_text

FERMAT_LEAD = SYNTHETIC_DIR / "fermat_lead.html"

# Wrappers a link label can sit in; the span must still cover the label only.
# A label may also carry a space inside the anchor (`<a> largest city</a>`).
WRAPPERS = (
    "{}",
    "<i>{}</i>",
    "<b><i>{}</i></b>",
    "<span class='x'>{}</span>",
    " {}",
    "{} ",
    " <i>{}</i> ",
)
# Text around the links: runs of spaces, newlines, entities and dropped furniture.
FILLERS = (
    " and ",
    "  and\n",
    " &amp; ",
    " &#160;or ",
    "<sup class='reference'><a href='#n'>[1]</a></sup> then ",
    "<span class='mw-empty-elt'><link rel='x' href='./y'></span> then ",
    "<style>.a{}</style> then ",
)


def _link(index: int, label: str, wrapper: str) -> str:
    """Build a wikilink to `Target{index}` holding the label in a wrapper."""
    return f"<a rel='mw:WikiLink' href='./Target{index}'>{wrapper.format(label)}</a>"


@st.composite
def _paragraphs(draw: st.DrawFn) -> tuple[str, list[str]]:
    """Draw a paragraph of linked words and fillers, with the labels in order."""
    count = draw(st.integers(min_value=1, max_value=8))
    parts = ["Intro words "]
    labels: list[str] = []
    for index in range(count):
        label = f"label{index}"
        labels.append(label)
        parts.append(draw(st.sampled_from(FILLERS)))
        parts.append(_link(index, label, draw(st.sampled_from(WRAPPERS))))
    parts.append(" closing words.")
    return "".join(parts), labels


@given(_paragraphs())
def test_every_span_covers_its_label(drawn: tuple[str, list[str]]) -> None:
    html, labels = drawn
    chunk = parse_sections(f"<p>{html}</p>").chunks[0]
    assert link_spans(chunk) == [(label, f"Target{i}") for i, label in enumerate(labels)]
    assert chunk.text == clean_text(chunk.text)


def test_dropped_wrapper_holding_links_does_not_shift_spans() -> None:
    empty = "<span class='mw-empty-elt'><link rel='x' href='./Y'><link rel='x' href='./Z'></span>"
    html = (
        "<p>A <a rel='mw:WikiLink' href='./One'>first</a> and "
        "<a rel='mw:WikiLink' href='./Two'>second</a> end.</p>"
    )
    chunk = parse_sections(f"{html}{empty}").chunks[0]
    assert link_spans(chunk) == [
        ("first", "One"),
        ("second", "Two"),
    ]


def test_fermat_lead_spans_and_pronunciation() -> None:
    article = parse_html(FERMAT_LEAD.read_text(encoding="ascii"), REV_ID, CITATION_ID)
    chunk = article.chunks[0]
    assert link_spans(chunk) == [
        ("polymath", "Polymath"),
        ("mathematician", "Mathematician"),
        ("infinitesimal calculus", "Infinitesimal calculus"),
        ("adequality", "Adequality"),
    ]
    assert chunk.text.startswith("Pierre de Fermat (17 August 1601")
