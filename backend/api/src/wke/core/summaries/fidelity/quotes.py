"""Quotations a summary states as fact."""

from __future__ import annotations

import re

from wke.core.summaries.fidelity.tokens import words
from wke.core.text.lexicon import STOPWORDS
from wke.core.text.sentences import split_sentences

QUOTE_RUN = 5

QUOTE_MIN_WORDS = 8

QUOTE_MIN_CONTENT = 3

_CURLY = re.compile(r"\u201c([^\u201c\u201d]*)\u201d")

_STRAIGHT = re.compile(r'"([^"]*)"')

_SPEECH = re.compile(
    r"\b(?:said|says|saying|stated|states|wrote|writes|according|told|declared|claimed|"
    r"claims|revealed|reveals|described|argued|argues|added|noted|explained|"
    r"announced|called|criticised|criticized|asserted|testified|denied|admitted)\b",
    re.IGNORECASE,
)

_FIRST_PERSON = re.compile(
    r"(?<!War )(?<!Part )(?<!Phase )(?<!Type )(?<!Division )(?<!Class )(?<!Charles )"
    r"\bI(?:'m|'ve|'ll|'d)?\s+[a-z]"
)


def _unquoted(text: str) -> str:
    """Remove quoted spans from a text.

    Args:
        text: any text.

    Returns:
        str: the text without curly or straight quotations.
    """
    return _STRAIGHT.sub(" ", _CURLY.sub(" ", text))


def _quote_spans(source: str, source_sentences: list[str]) -> list[str]:
    """Collect the quoted spans of the source.

    Args:
        source: the passages the model read.
        source_sentences: the source split into sentences.

    Returns:
        list[str]: the quoted spans.
    """
    spans = _CURLY.findall(source) + _STRAIGHT.findall(_CURLY.sub(" ", source))
    spans += [s for s in source_sentences if _FIRST_PERSON.search(s)]
    return [s for s in spans if len(words(s)) >= QUOTE_MIN_WORDS]


def quote_lifted(text: str, source: str) -> str | None:
    """Find quoted or first-person source words stated as fact.

    Args:
        text: the summary.
        source: the passages the model read.

    Returns:
        str | None: evidence for the first summary sentence, outside its own quotation
        marks and without a speech verb, that shares QUOTE_RUN consecutive
        words with a quotation or first-person sentence of the source, or
        None.
    """
    grams: set[tuple[str, ...]] = set()
    for span in _quote_spans(source, split_sentences(source)):
        span_words = words(span)
        grams |= {
            tuple(span_words[i : i + QUOTE_RUN])
            for i in range(len(span_words) - QUOTE_RUN + 1)
            if sum(w not in STOPWORDS for w in span_words[i : i + QUOTE_RUN]) >= QUOTE_MIN_CONTENT
        }

    for sentence in split_sentences(text):
        if _SPEECH.search(sentence):
            continue
        sentence_words = words(_unquoted(sentence))

        for i in range(len(sentence_words) - QUOTE_RUN + 1):
            gram = tuple(sentence_words[i : i + QUOTE_RUN])
            if gram in grams:
                return f"a quotation from the source is stated as fact: '{' '.join(gram)}'"

    return None
