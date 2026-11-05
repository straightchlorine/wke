"""Remove the pronunciation of the title (IPA, respelling and audio) from the lead paragraph."""

from __future__ import annotations

import re

from selectolax.lexbor import LexborHTMLParser, LexborNode

IPA_SELECTOR = ".IPA"
# The label the IPA template prints before the transcription ("pronounced").
IPA_LABEL_SELECTOR = ".IPA-label"
# The respelling template links to the key page and wraps the text in an
# element titled as a pronunciation respelling.
RESPELLING_LINK_SELECTOR = 'a[href$="Help:Pronunciation_respelling_key"]'
RESPELLING_TEXT_SELECTOR = 'i[title$="pronunciation respelling"]'
# The audio player the Phonos extension renders beside the pronunciation.
AUDIO_SELECTOR = ".ext-phonos"
PRONUNCIATION_SELECTORS = (
    IPA_SELECTOR,
    IPA_LABEL_SELECTOR,
    AUDIO_SELECTOR,
    RESPELLING_LINK_SELECTOR,
    RESPELLING_TEXT_SELECTOR,
)

# The title and its first parenthetical; the title part holds no bracket, so
# only a parenthetical within the first 200 characters matches.
_FIRST_PARENTHETICAL = re.compile(r"^(?P<head>[^()]{0,200}?)(?P<space>\s*)\((?P<inner>[^()]*)\)")
# A ";" or "," followed by a space or the bracket; "23,000" holds no separator.
_PART_SEPARATOR = re.compile(r"\s*([;,])(?:\s+|$)")
# The link and formula marks of the prose reader; ignored when a part is judged.
_MARKS = re.compile("[\ue000-\uf8ff\U000f0000\U000f0001]")
# A part with nothing left to say once the pronunciation went: empty, a bare
# "/.../" transcription, a language label ("Italian:", "Serbo-Croatian:",
# "Ancient Greek:") or the "or" that joined two pronunciations.
_EMPTY_PART = re.compile(r"^(?:|/[^/]*/|(?:[A-Z][\w'-]*\s)*[A-Z][\w'-]*:|or)$")


def has_pronunciation(element: LexborNode | LexborHTMLParser) -> bool:
    """Tell whether an element holds an IPA, respelling or audio span.

    Args:
        element: a paragraph element or a parsed document.

    Returns:
        bool: True when any pronunciation span is inside.
    """
    return any(element.css_first(selector) is not None for selector in PRONUNCIATION_SELECTORS)


def drop_pronunciation_spans(element: LexborNode | LexborHTMLParser) -> None:
    """Remove the IPA, respelling and audio spans of an element.

    Args:
        element: the lead's `<p>` element or a parsed document; modified in place.
    """
    for selector in PRONUNCIATION_SELECTORS:
        for span in element.css(selector):
            span.decompose()


def tidy_pronunciation(text: str) -> str:
    """Remove what a dropped pronunciation leaves in a lead paragraph's first parenthetical.

    The parenthetical (within the first 200 characters) is read as parts
    between ";" and ",". A part with nothing left to say is removed with its
    separator; between two kept parts the stronger separator stays (";" over
    ","). With no part left, the brackets go too. A parenthetical with nothing
    to remove reads exactly as before.

    Args:
        text: cleaned lead paragraph text, pronunciation spans already removed.

    Returns:
        str: the text with "Foo (/fu:/; Italian: ; born 1900)" read as "Foo
        (born 1900)" and "Foo ( ) is" as "Foo is".
    """
    match = _FIRST_PARENTHETICAL.match(text)
    if match is None:
        return text
    pieces = _PART_SEPARATOR.split(match.group("inner").strip())
    inner = ""
    gap = ""
    for index in range(0, len(pieces), 2):
        if index:
            separator = pieces[index - 1]
            gap = ";" if ";" in (gap, separator) else gap or separator
        part = pieces[index]
        if _EMPTY_PART.match(_MARKS.sub("", part)):
            continue
        inner = f"{inner}{gap} {part}" if inner else part
        gap = ""
    rest = text[match.end() :]
    if not inner:
        return match.group("head") + rest
    return f"{match.group('head')}{match.group('space')}({inner}){rest}"
