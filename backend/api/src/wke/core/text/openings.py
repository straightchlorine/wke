"""How a passage opens: its content tokens, its opening key and its subject."""

from __future__ import annotations

import re

from wke.core.text.lexicon import FUNCTION_WORDS, STOPWORDS

OPENING_TOKENS = 3

_WORD_RE = re.compile(r"\w+")
_CONTENT_STOPWORDS = FUNCTION_WORDS | STOPWORDS
# Quotation marks and the dashes that introduce an epigraph.
_QUOTE_OPENERS = frozenset("\"'`\u201c\u2018\u00ab\u201e\u2013\u2014-")
# First words of a sentence whose subject is somewhere else.
_POINTER_OPENERS = frozenset(
    "he she it they this these those his her its their we i you there here".split()
)
_CONTINUATION_OPENERS = frozenset(
    (
        "later then however meanwhile subsequently afterwards afterward also thus "
        "therefore consequently moreover furthermore additionally nevertheless "
        "nonetheless but and yet still instead otherwise previously eventually "
        "finally soon next"
    ).split()
)


def content_tokens(text: str) -> list[str]:
    """Split text into lower-case words without stopwords; numbers are kept.

    Args:
        text: any text.

    Returns:
        list[str]: the tokens in order of appearance.
    """
    return [w for w in _WORD_RE.findall(text.casefold()) if w not in _CONTENT_STOPWORDS]


def opening_key(text: str, size: int = OPENING_TOKENS) -> tuple[str, ...]:
    """Return the first content tokens of a text, the key of its opening.

    Args:
        text: a paragraph.
        size: how many tokens the key holds.

    Returns:
        tuple[str, ...]: shorter than size when the text has fewer tokens.
    """
    return tuple(content_tokens(text)[:size])


def overlap_with(text: str, reference: set[str]) -> float:
    """Return the share of a text's distinct content tokens found in a reference.

    Args:
        text: the passage.
        reference: content tokens of the text it is compared with.

    Returns:
        float: 0.0 when the text has no content tokens.
    """
    mine = set(content_tokens(text))
    return len(mine & reference) / len(mine) if mine else 0.0


def has_named_subject(text: str) -> bool:
    """Tell whether a passage can start a section without the text before it.

    Args:
        text: a paragraph.

    Returns:
        bool: False when it opens with a quotation mark or epigraph dash,
        a pronoun, or a continuation such as "Later" or "However".
    """
    stripped = text.lstrip()
    if not stripped or stripped[0] in _QUOTE_OPENERS:
        return False
    match = _WORD_RE.match(stripped)
    if match is None:
        return False
    first = match.group(0).casefold()
    return first not in _POINTER_OPENERS and first not in _CONTINUATION_OPENERS
