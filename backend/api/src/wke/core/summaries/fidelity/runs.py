"""Runs of content tokens a summary shares with its source."""

from __future__ import annotations

from wke.core.summaries.fidelity.tokens import content
from wke.core.text.sentences import split_sentences

PHRASE_RUN = 3

PHRASE_SKIPS = 1

PHRASE_DENSE_SHARE = 0.5

PHRASE_DENSE_MIN_WINDOWS = 6


def _ngrams_with_skips(seq: list[str], size: int, skips: int) -> set[tuple[str, ...]]:
    """Collect the runs of `size` tokens of seq with at most `skips` tokens skipped in all.

    Args:
        seq: content tokens of one sentence.
        size: tokens per run.
        skips: tokens a run may skip in all.

    Returns:
        set[tuple[str, ...]]: the runs.
    """
    grams: set[tuple[str, ...]] = set()

    def extend(prefix: tuple[str, ...], last: int, left: int) -> None:
        """Grow a run by one token, skipping at most the tokens left.

        Args:
            prefix: the run so far.
            last: index of its last token in seq.
            left: skips still allowed.
        """
        if len(prefix) == size:
            grams.add(prefix)
            return
        for nxt in range(last + 1, min(last + 2 + left, len(seq))):
            extend(prefix + (seq[nxt],), nxt, left - (nxt - last - 1))

    for start in range(len(seq)):
        extend((seq[start],), start, skips)
    return grams


def missing_runs(
    sentences: list[str], source_sentences: list[str]
) -> tuple[int, int, list[tuple[str, tuple[str, ...]]]]:
    """Find runs of content tokens that no source sentence has.

    Args:
        sentences: the summary split into sentences.
        source_sentences: the source split into sentences.

    Returns:
        tuple[int, int, list[tuple[str, tuple[str, ...]]]]: the number of
        runs of PHRASE_RUN content tokens in the summary, how many of them no
        source sentence has, and the first absent run of each sentence with
        that sentence. A source run may skip PHRASE_SKIPS tokens.
    """
    grams: set[tuple[str, ...]] = set()
    for source in source_sentences:
        grams |= _ngrams_with_skips(content(source), PHRASE_RUN, PHRASE_SKIPS)
    windows = missing = 0
    absent: list[tuple[str, tuple[str, ...]]] = []
    for sentence in sentences:
        seq = content(sentence)
        reported = False
        for i in range(len(seq) - PHRASE_RUN + 1):
            gram = tuple(seq[i : i + PHRASE_RUN])
            windows += 1
            if gram not in grams:
                missing += 1
                if not reported:
                    reported = True
                    absent.append((sentence, gram))
    return windows, missing, absent


def novel_phrase_dense(text: str, source: str) -> str | None:
    """Find a summary most of whose content runs the source never has.

    Args:
        text: the summary.
        source: the passages the model read.

    Returns:
        str | None: evidence, or None.
    """
    windows, missing, _ = missing_runs(split_sentences(text), split_sentences(source))
    if windows >= PHRASE_DENSE_MIN_WINDOWS and missing / windows >= PHRASE_DENSE_SHARE:
        return f"{missing} of {windows} short phrases of the text appear nowhere in the source"
    return None
