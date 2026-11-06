"""A run of prose text together with the link and formula spans it carries."""

from __future__ import annotations

import re
from dataclasses import dataclass

from wke.core.models import FormulaSpan, LinkSpan, TextSpan
from wke.core.text.lexicon import FUNCTION_WORDS
from wke.core.text.sentences import SENTENCE_FINAL, split_sentences

JOINER = " "

_FIRST_WORD = re.compile(r"[^\W\d_]+")


def _shifted[S: TextSpan](span: S, by: int) -> S:
    """Move a span by a number of code points.

    Args:
        span: a link or formula span.
        by: code points to add to both offsets; negative moves it left.

    Returns:
        S: a copy of the span at its new offsets.
    """
    return span.model_copy(update={"start": span.start + by, "end": span.end + by})


@dataclass(frozen=True)
class Passage:
    """Prose text and the link and formula spans on it, offsets in code points."""

    text: str
    links: tuple[LinkSpan, ...] = ()
    formulas: tuple[FormulaSpan, ...] = ()

    def slice(self, start: int, end: int) -> Passage:
        """Cut a part of the passage and keep the spans that lie wholly inside.

        Args:
            start: first code point kept.
            end: code point after the last one kept.

        Returns:
            Passage: the part, with spans shifted to its own offsets.
        """
        links = tuple(_shifted(s, -start) for s in self.links if s.start >= start and s.end <= end)
        formulas = tuple(
            _shifted(s, -start) for s in self.formulas if s.start >= start and s.end <= end
        )
        return Passage(self.text[start:end], links, formulas)

    def ends_sentence(self) -> bool:
        """Tell whether the passage stops at the end of a sentence.

        A formula at the very end counts: a display equation closes its
        sentence whether or not its TeX carries the full stop.

        Returns:
            bool: True for a sentence-final mark at the end, or a formula
            span that reaches the end of the text.
        """
        if SENTENCE_FINAL.search(self.text):
            return True
        return any(span.end == len(self.text) for span in self.formulas)

    def starts_mid_sentence(self) -> bool:
        """Tell whether the passage opens inside a sentence.

        Returns:
            bool: True when its first word is a lowercase function word, as in
            "where c is the hypotenuse" after an equation.
        """
        match = _FIRST_WORD.match(self.text)
        return bool(match and match.group().islower() and match.group() in FUNCTION_WORDS)

    def sentences(self) -> list[Passage]:
        """Split the passage at real sentence ends.

        Returns:
            list[Passage]: the sentences in order, each with its own spans.
        """
        parts: list[Passage] = []
        cursor = 0
        for sentence in split_sentences(self.text):
            start = self.text.index(sentence, cursor)
            cursor = start + len(sentence)
            parts.append(self.slice(start, cursor))
        return parts


def join_passages(parts: list[Passage]) -> Passage:
    """Join passages with one space and shift their spans to the joined text.

    Args:
        parts: the passages in reading order.

    Returns:
        Passage: the joined text with every span of every part.
    """
    links: list[LinkSpan] = []
    formulas: list[FormulaSpan] = []
    offset = 0
    for part in parts:
        links.extend(_shifted(s, offset) for s in part.links)
        formulas.extend(_shifted(s, offset) for s in part.formulas)
        offset += len(part.text) + len(JOINER)
    return Passage(JOINER.join(p.text for p in parts), tuple(links), tuple(formulas))
