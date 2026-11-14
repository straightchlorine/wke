"""The hard fidelity rules and the generator that runs them."""

from __future__ import annotations

from collections.abc import Callable, Iterator

from wke.core.summaries.fidelity.glitches import (
    glitch_contained_sentence,
    glitch_lower_after_period,
)
from wke.core.summaries.fidelity.numbers import number_context
from wke.core.summaries.fidelity.quotes import quote_lifted
from wke.core.summaries.fidelity.roles import roles
from wke.core.summaries.fidelity.runs import novel_phrase_dense

Rule = Callable[[str, str], str | None]

# Rules whose flags were all real defects on the labelled summaries;
# gate withholds a summary on any of them. Keys are the rule ids the script prints.
HARD_RULES: tuple[tuple[str, Rule], ...] = (
    ("novel_phrase.dense", novel_phrase_dense),
    ("roles", roles),
    ("quote_lifted", quote_lifted),
    ("glitch.lower_after_period", glitch_lower_after_period),
    ("glitch.contained_sentence", glitch_contained_sentence),
)


def hard_failures(text: str, source: str, heading: str = "") -> Iterator[tuple[str, str]]:
    """Run every hard rule, lazily, so a caller may stop at the first.

    Args:
        text: the summary.
        source: the passages the model read.
        heading: the section heading, whose numbers the summary may use.

    Yields:
        tuple[str, str]: (rule id, evidence) for each rule that fails,
        number_context first.
    """
    evidence = number_context(text, source, heading)
    if evidence:
        yield "number_context", evidence
    for key, rule in HARD_RULES:
        evidence = rule(text, source)
        if evidence:
            yield key, evidence
