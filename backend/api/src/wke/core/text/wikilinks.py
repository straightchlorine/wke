"""Split a passage at its link spans and name the Wikipedia page each one points to."""

from __future__ import annotations

from urllib.parse import quote, urlsplit

from wke.core.models import LinkSpan, TextSpan

# Characters of a page title kept as they are in the URL path. Parentheses
# are not among them: they would end the Markdown link early.
_TITLE_SAFE = "_,:;@!$&'*+=~/"


def wiki_origin(url: object) -> str:
    """Return the scheme and host of a Wikipedia page URL.

    Args:
        url: any URL of the wiki the dossier was built from.

    Returns:
        str: "https://en.wikipedia.org" for an English article URL.
    """
    parts = urlsplit(str(url))
    return f"{parts.scheme}://{parts.netloc}"


def link_url(origin: str, title: str) -> str:
    """Build the URL of a linked page.

    Args:
        origin: scheme and host of the wiki.
        title: the page title of the span.

    Returns:
        str: the /wiki/ URL with the title percent-encoded.
    """
    return f"{origin}/wiki/{quote(title.replace(' ', '_'), safe=_TITLE_SAFE)}"


def usable_spans[S: TextSpan](spans: list[S], length: int) -> list[S]:
    """Keep the spans that lie inside a text and do not overlap an earlier one.

    Args:
        spans: link or formula spans of a passage.
        length: length of the text shown, which may be a cut of the passage.

    Returns:
        list[S]: in text order.
    """
    kept: list[S] = []
    for span in sorted(spans, key=lambda s: s.start):
        if span.end <= length and (not kept or span.start >= kept[-1].end):
            kept.append(span)
    return kept


def split_linked(text: str, spans: list[LinkSpan]) -> list[tuple[str, str | None]]:
    """Cut a text into plain runs and linked runs.

    Args:
        text: the passage text as shown.
        spans: its link spans.

    Returns:
        list[tuple[str, str | None]]: (run, title) pairs that join back to
        the text; title is None for a plain run.
    """
    runs: list[tuple[str, str | None]] = []
    at = 0
    for span in usable_spans(spans, len(text)):
        if span.start > at:
            runs.append((text[at : span.start], None))
        runs.append((text[span.start : span.end], span.title))
        at = span.end
    if at < len(text):
        runs.append((text[at:], None))
    return runs
