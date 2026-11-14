"""Read link and formula marks of cleaned paragraph text back as spans."""

from __future__ import annotations

from wke.core.models import FormulaSpan, LinkSpan
from wke.core.parse.formulas import FORMULA_END, FORMULA_START
from wke.core.parse.links import LINK_END, LINK_START_BASE, MAX_LINKS_PER_PARAGRAPH
from wke.core.parse.passage import Passage
from wke.core.text.clean import clean_text


def _trimmed(plain: list[str], start: int) -> tuple[int, int] | None:
    """Close a span at the end of the text read so far, without edge spaces.

    Args:
        plain: the characters read so far.
        start: where the span opened.

    Returns:
        tuple[int, int] | None: the span's start and end, or None when it
        covers no visible character.
    """
    end = len(plain)
    while start < end and plain[start] == " ":
        start += 1
    while end > start and plain[end - 1] == " ":
        end -= 1
    return (start, end) if end > start else None


def read_marked(marked: str, titles: list[str]) -> Passage:
    """Strip the marks from cleaned text and turn them into spans.

    Args:
        marked: cleaned paragraph text that still holds the marks.
        titles: the titles `mark_links` returned, in order.

    Returns:
        Passage: the text without marks and its spans. A space inside a
        link (`<a> largest city</a>`) leaves one space in the text and none
        in the span. The spans are left out when the text still differs from
        its clean_text form, because the offsets could then not be trusted.
    """
    plain: list[str] = []
    links: list[LinkSpan] = []
    formulas: list[FormulaSpan] = []
    opened: tuple[int, int] | None = None
    formula_start: int | None = None
    for char in marked:
        if LINK_START_BASE <= ord(char) < LINK_START_BASE + MAX_LINKS_PER_PARAGRAPH:
            opened = (len(plain), ord(char) - LINK_START_BASE)
        elif char == LINK_END:
            span = _trimmed(plain, opened[0]) if opened is not None else None
            if span is not None and opened is not None and opened[1] < len(titles):
                links.append(LinkSpan(start=span[0], end=span[1], title=titles[opened[1]]))
            opened = None
        elif char == FORMULA_START:
            formula_start = len(plain)
        elif char == FORMULA_END:
            span = _trimmed(plain, formula_start) if formula_start is not None else None
            if span is not None:
                formulas.append(FormulaSpan(start=span[0], end=span[1]))
            formula_start = None
        elif char != " " or (plain and plain[-1] != " "):
            # A mark between two spaces would leave both; keep one, as clean_text does.
            plain.append(char)
    text = "".join(plain).rstrip(" ")
    if text != clean_text(text):
        return Passage(clean_text(text))
    return Passage(text, tuple(links), tuple(formulas))
