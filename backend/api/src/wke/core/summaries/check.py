"""Source check for a model summary: show it only when the text is safe to show.

A summary is withheld, never edited. It must stop at a sentence end, send the
reader nowhere but to its citation, and introduce no capitalised name or
number that is absent from the passages the model read.

It must also pass the rules of summaries.fidelity: no number on the wrong event,
no swapped roles, no quotation stated as fact, no sentence cut or repeated,
no text the source does not back.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from wke.core.summaries.fidelity.rules import hard_failures
from wke.core.text.lexicon import FUNCTION_WORDS
from wke.core.text.navigation import points_elsewhere
from wke.core.text.numbers import number_tokens
from wke.core.text.sentences import ends_at_sentence_end, split_sentences

_WORD = re.compile(r"[^\W\d_][\w'\u2019\-]*")

_POSSESSIVE = re.compile(r"(?:'s|\u2019s|'|\u2019)$")


def _norm_word(word: str) -> str:
    """Lowercase a word and strip a trailing possessive.

    Args:
        word: a word of a summary or source.

    Returns:
        str: the normalised word.
    """
    return _POSSESSIVE.sub("", word.lower())


def _source_words(text: str) -> set[str]:
    """Collect the normalised words of the source.

    Args:
        text: the passages the model read.

    Returns:
        set[str]: the normalised words.
    """
    return {_norm_word(word) for word in _WORD.findall(text)}


def _names(text: str, title: str) -> bool:
    """Tell whether a text names a title as whole words, ignoring case.

    Args:
        text: any text.
        title: an article title.

    Returns:
        bool: True when the title occurs with no word character on either side.
    """
    return re.search(rf"(?<!\w){re.escape(title)}(?!\w)", text, re.IGNORECASE) is not None


def unsupported_names(summary: str, source: str) -> list[str]:
    """List the capitalised words of a summary that the source never uses.

    Args:
        summary: the summary text.
        source: the passages the model read.

    Returns:
        list[str]: the words, in text order; a function word that opens a
        sentence is not a name.
    """
    source_words = _source_words(source)
    missing: list[str] = []
    for sentence in split_sentences(summary):
        for index, word in enumerate(_WORD.findall(sentence)):
            if len(word) < 2 or not word[0].isupper():
                continue
            norm = _norm_word(word)
            if index == 0 and norm in FUNCTION_WORDS:
                continue
            if norm not in source_words:
                missing.append(word)
    return missing


def unsupported_numbers(summary: str, source: str, heading: str = "") -> list[str]:
    """List the numbers of a summary that neither the source nor the heading has.

    Args:
        summary: the summary text.
        source: the passages the model read.
        heading: the section heading; years in it are allowed.

    Returns:
        list[str]: the numbers, sorted.
    """
    return sorted(
        set(number_tokens(summary)) - set(number_tokens(source)) - set(number_tokens(heading))
    )


def check_summary(
    text: str,
    source: str,
    heading: str = "",
    truncated: bool = False,
    foreign_titles: Iterable[str] = (),
) -> str | None:
    """Decide whether a model summary may be shown.

    Args:
        text: the summary exactly as the model returned it.
        source: the passages the model was given, joined.
        heading: the section heading; years in it are allowed in the summary.
        truncated: whether wke-ml reported the output as cut off.
        foreign_titles: titles of other articles; the summary may not name
            one that the source does not.

    Returns:
        str | None: the reason to withhold the summary, or None when it
        passes.
    """
    if truncated:
        return "the model output was cut off"
    if not ends_at_sentence_end(text):
        return "the text does not end at a sentence end"
    if points_elsewhere(text):
        return "the text points to another page"
    for title in foreign_titles:
        title = title.strip()
        if title and _names(text, title) and not _names(source, title):
            return "the text names an article that is not in the source"
    names = unsupported_names(text, source)
    if names:
        return f"the name {names[0]!r} is not in the source passages"
    numbers = unsupported_numbers(text, source, heading)
    if numbers:
        return f"the number {numbers[0]!r} is not in the source passages"
    for _rule, evidence in hard_failures(text, source, heading):
        return evidence
    return None
