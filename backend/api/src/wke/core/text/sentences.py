"""Sentence splitting and the sentence-end check shared by the parser, packer and checks."""

from __future__ import annotations

import re

SENTENCE_END = re.compile(r"[.!?][\"')\]\u201d\u2019]*\s+")
SENTENCE_FINAL = re.compile(r"[.!?\u2026][\"')\]\u201d\u2019]*$")

# Characters that may open a sentence before its first letter.
SENTENCE_OPENERS = "\"'([\u201c\u2018"
_OPENER_SET = frozenset(SENTENCE_OPENERS)

_NON_TERMINAL_WORDS = frozenset(
    (
        "i.e",
        "e.g",
        "cf",
        "c",
        "ca",
        "No",
        "vs",
        "Mr",
        "Mrs",
        "Ms",
        "Dr",
        "St",
        "Jr",
        "Sr",
        "Inc",
        "Co",
        "Ltd",
        "U.S",
        "U.K",
    )
)

_INITIALS = re.compile(r"^(?:[A-Z]\.)*[A-Z]$")


def ends_at_sentence_end(text: str) -> bool:
    """Tell whether text stops at the end of a sentence.

    Args:
        text: a passage or summary.

    Returns:
        bool: True when the last character is a full stop, question mark,
        exclamation mark or ellipsis, possibly followed by closing quotes
        or brackets, ignoring trailing whitespace.
    """
    return bool(SENTENCE_FINAL.search(text.rstrip()))


def _is_real_end(text: str, match: re.Match[str]) -> bool:
    """Decide whether a candidate boundary is a true sentence end.

    Args:
        text: the full text being split.
        match: a SENTENCE_END match inside text.

    Returns:
        bool: False when the next character cannot open a sentence or the
        word before a period is an initial or a known abbreviation.
    """
    if match.end() >= len(text):
        return True
    following = text[match.end()]
    if not (following.isupper() or following.isdigit() or following in _OPENER_SET):
        return False
    if text[match.start()] != ".":
        return True
    words = text[: match.start()].rsplit(None, 1)
    word = words[-1].lstrip(SENTENCE_OPENERS) if words else ""
    return not (_INITIALS.match(word) or word in _NON_TERMINAL_WORDS)


def split_sentences(text: str) -> list[str]:
    """Split text into sentences at real sentence ends only.

    A missed split only makes a piece longer, while a wrong split cuts a
    sentence, so the rule errs on the side of not splitting.

    Args:
        text: single-line text with collapsed whitespace.

    Returns:
        list[str]: the sentences in order, whose space-joined form equals
        text. Empty for empty input.
    """
    sentences: list[str] = []
    start = 0
    for match in SENTENCE_END.finditer(text):
        if _is_real_end(text, match):
            sentences.append(text[start : match.start() + len(match.group().rstrip())])
            start = match.end()
    tail = text[start:]
    if tail:
        sentences.append(tail)
    return sentences
