"""Who did what to whom: a summary may not swap the roles of the source."""

from __future__ import annotations

import re

from wke.core.text.lexicon import LEAD_FUNCTION
from wke.core.text.sentences import split_sentences

VERBS = (
    "selected chose defeated beat sued married hired founded killed arrested convicted "
    "succeeded replaced announced awarded"
).split()

_NAME_WORD = r"[A-Z][\w.'\u2019\-]*"

_NAME = rf"{_NAME_WORD}(?:\s+(?:(?:of|de|van|von|bin|al)\s+)?{_NAME_WORD})*"

_ROLE = re.compile(
    rf"(?P<a>{_NAME})\s+(?:(?:also|then|had|later)\s+)?(?P<v>{'|'.join(VERBS)})\s+(?P<b>{_NAME})"
)


def _name_head(name: str) -> str:
    """Return the last word of a name, which identifies it in a sentence.

    Args:
        name: a capitalised name.

    Returns:
        str: its last word.
    """
    return name.split()[-1].strip(".'\u2019").lower()


def _positions(sentence: str, head: str) -> list[tuple[int, int]]:
    """Find where a name head occurs in a sentence.

    Args:
        sentence: a sentence.
        head: the head word of a name.

    Returns:
        list[tuple[int, int]]: the (start, end) spans.
    """
    return [m.span() for m in re.finditer(rf"\b{re.escape(head)}\b", sentence, re.IGNORECASE)]


def _pair_in_source(a: str, b: str, source_sentences: list[str]) -> bool:
    """Tell whether a source sentence has a before b, or the passive b ... by a.

    Args:
        a: the name before the verb in the summary.
        b: the name after the verb.
        source_sentences: the source split into sentences.

    Returns:
        bool: True when some source sentence has the pair in that role order.
    """
    head_a, head_b = _name_head(a), _name_head(b)
    for sentence in source_sentences:
        for sa in _positions(sentence, head_a):
            for sb in _positions(sentence, head_b):
                if sa[1] <= sb[0] and not re.search(r"\bby\b", sentence[sa[1] : sb[0]]):
                    return True
                if sb[1] <= sa[0] and re.search(r"\bby\b", sentence[sb[1] : sa[0]]):
                    return True
    return False


def roles(text: str, source: str) -> str | None:
    """Check each "<Name> <verb> <Name>" pattern against an ordered pair in the source.

    Args:
        text: the summary.
        source: the passages the model read.

    Returns:
        str | None: evidence for the first pattern whose ordered pair of names (active,
        or passive with "by") occurs in no source sentence, or None.
    """
    source_sentences = split_sentences(source)
    for sentence in split_sentences(text):
        for match in _ROLE.finditer(sentence):
            lead = match.group("a").split()

            while len(lead) > 1 and lead[0].lower() in LEAD_FUNCTION:
                lead = lead[1:]

            name_a, name_b = " ".join(lead), match.group("b")
            if not _pair_in_source(name_a, name_b, source_sentences):
                return (
                    f"a sentence says '{name_a} {match.group('v')} {name_b}' "
                    "but the source never has them in that order"
                )
    return None
