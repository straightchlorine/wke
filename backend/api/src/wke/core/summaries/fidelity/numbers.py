"""Numbers of a summary that must come from the source."""

from __future__ import annotations

from wke.core.summaries.fidelity.tokens import content, words
from wke.core.text.numbers import number_tokens
from wke.core.text.sentences import split_sentences

NUMBER_SHARED_WORDS = 2


def number_context(text: str, source: str, heading: str = "") -> str | None:
    """Check that each number sits with the same words as in the source.

    Args:
        text: the summary.
        source: the passages the model read.
        heading: the section heading; numbers in it are skipped.

    Returns:
        str | None: evidence for the first number that occurs in the source but in no
        source sentence sharing NUMBER_SHARED_WORDS content words with the
        summary sentence, or None.
    """
    source_sentences = split_sentences(source)
    source_numbers = [set(number_tokens(s)) for s in source_sentences]
    source_words = [set(content(" ".join(words(s)))) for s in source_sentences]
    heading_numbers = set(number_tokens(heading))

    for sentence in split_sentences(text):
        sentence_words = set(content(" ".join(words(sentence))))
        need = min(NUMBER_SHARED_WORDS, len(sentence_words))

        for number in dict.fromkeys(number_tokens(sentence)):
            if number in heading_numbers:
                continue

            holders = [i for i, nums in enumerate(source_numbers) if number in nums]
            if holders and max(len(sentence_words & source_words[i]) for i in holders) < need:
                return (
                    f"the number {number} is attached to words that do not go with it in the source"
                )
    return None
