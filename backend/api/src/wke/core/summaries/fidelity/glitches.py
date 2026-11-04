"""Sentences the model cut short or repeated."""

from __future__ import annotations

import re

from wke.core.summaries.fidelity.tokens import content
from wke.core.text.sentences import split_sentences

CONTAINED_MIN_TOKENS = 4

_LOWER_AFTER_STOP = re.compile(
    r"\b(?:such|as|and|of|the|in|to|for|with|a|an|by|or|at|from|that|which)\.\s+[a-z]"
    r"(?:\S*(?:\s+\S+){0,2})?"
)


def glitch_lower_after_period(text: str, source: str) -> str | None:
    """Find a sentence cut inside, where a period follows a function word.

    Args:
        text: the summary.
        source: unused; kept so every rule has one signature.

    Returns:
        str | None: evidence quoting the cut, or None. The model writes a space before
        the closing full stop of every sentence, so only a period glued to a
        word inside a sentence counts.
    """
    for sentence in split_sentences(text):
        match = _LOWER_AFTER_STOP.search(sentence)
        if match:
            return f"a sentence is cut inside: '{match.group(0)}'"
    return None


def glitch_contained_sentence(text: str, source: str) -> str | None:
    """Find a sentence whose content tokens recur inside a longer sentence.

    Args:
        text: the summary.
        source: unused; kept so every rule has one signature.

    Returns:
        str | None: evidence quoting the repeated sentence, or None.
    """
    sentences = split_sentences(text)
    normalised = [" ".join(content(s)) for s in sentences]
    for i, sentence in enumerate(sentences):
        if len(normalised[i].split()) < CONTAINED_MIN_TOKENS:
            continue
        for j, other in enumerate(normalised):
            if j != i and len(other) > len(normalised[i]) and f" {normalised[i]} " in f" {other} ":
                return f"a sentence is repeated inside another: '{sentence.strip()}'"
    return None
