"""Tokenising and stemming shared by the fidelity rules."""

from __future__ import annotations

import re

from wke.core.text.lexicon import STOPWORDS

_TOKEN = re.compile(r"\d[\d,]*(?:\.\d+)?|[^\W_]+(?:['\u2019\-][^\W_]+)*")

_POSSESSIVE = re.compile(r"(?:'s|\u2019s)$")


def stem(word: str) -> str:
    """Reduce a word to a crude stem so inflections compare equal.

    Args:
        word: a lowercase word.

    Returns:
        str: the word without a common English suffix.
    """
    for suffix in ("ing", "ed", "es", "s", "ly"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def tokens(text: str) -> list[str]:
    """Split text into lowercase words and numbers, possessives removed.

    Args:
        text: any text.

    Returns:
        list[str]: the tokens in order; numbers lose their thousands commas.
    """
    out: list[str] = []
    for raw in _TOKEN.findall(text):
        token = _POSSESSIVE.sub("", raw.lower())
        out.append(token.replace(",", "") if token[0].isdigit() else token)
    return out


def content(text: str) -> list[str]:
    """Return the stemmed content tokens of a text, stopwords removed.

    Args:
        text: any text.

    Returns:
        list[str]: stemmed tokens that are not stopwords, in order.
    """
    return [stem(t) for t in tokens(text) if t not in STOPWORDS]


def words(text: str) -> list[str]:
    """Return the tokens of a text that are not numbers.

    Args:
        text: any text.

    Returns:
        list[str]: lowercase word tokens in order.
    """
    return [t for t in tokens(text) if not t[0].isdigit()]
