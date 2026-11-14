"""Inline Markdown for a passage: wiki links and formulas on its verbatim text."""

from __future__ import annotations

import re

from wke.core.models import FormulaSpan, LinkSpan
from wke.core.render.escape import escape_inline_markup
from wke.core.text.wikilinks import link_url, split_linked, usable_spans

_BACKTICK_RUN = re.compile(r"`+")


def code_span(tex: str) -> str:
    """Write TeX as an inline code span that no content can close early.

    Args:
        tex: the formula source, one line.

    Returns:
        str: the TeX between backtick fences one longer than its longest
        backtick run, padded with a space where it starts or ends with one.
    """
    longest = max((len(run) for run in _BACKTICK_RUN.findall(tex)), default=0)
    fence = "`" * (longest + 1)
    pad = " " if tex.startswith("`") or tex.endswith("`") else ""
    return f"{fence}{pad}{tex}{pad}{fence}"


def _prose_markup(text: str, spans: list[LinkSpan], origin: str) -> str:
    """Escape a run of text and turn the link spans inside it into Markdown links.

    Args:
        text: the run, holding no formula.
        spans: link spans in the run's own offsets; ignored without origin.
        origin: scheme and host of the wiki; "" writes no links.

    Returns:
        str: the escaped text with each span as "[span text](page URL)".
    """
    if not origin:
        return escape_inline_markup(text)
    parts: list[str] = []
    for run, title in split_linked(text, spans):
        escaped = escape_inline_markup(run)
        parts.append(escaped if title is None else f"[{escaped}]({link_url(origin, title)})")
    return "".join(parts)


def inline_markup(
    text: str, links: list[LinkSpan], formulas: list[FormulaSpan], origin: str = ""
) -> str:
    """Escape a passage, show its formulas as code and, with an origin, link it.

    Args:
        text: the passage text as shown.
        links: its link spans.
        formulas: its formula spans.
        origin: scheme and host of the wiki; "" writes no links.

    Returns:
        str: Markdown for the text; a link that crosses a formula is left
        out, the link text of the rest is the verbatim substring.
    """
    parts: list[str] = []
    at = 0
    for formula in [*usable_spans(formulas, len(text)), None]:
        end = len(text) if formula is None else formula.start
        inside = [
            span.model_copy(update={"start": span.start - at, "end": span.end - at})
            for span in links
            if span.start >= at and span.end <= end
        ]
        parts.append(_prose_markup(text[at:end], inside, origin))
        if formula is not None:
            parts.append(code_span(text[formula.start : formula.end]))
            at = formula.end
    return "".join(parts)
