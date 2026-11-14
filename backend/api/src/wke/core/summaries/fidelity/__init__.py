"""Deterministic fidelity rules for a model summary against its source.

Each rule takes the summary text and the source text and returns the first
piece of evidence that the summary is wrong, or None. The gate in
summaries.check withholds a summary on any of them; scripts/eval/fidelity_check.py
runs the same functions, so the two cannot disagree.
"""

from wke.core.summaries.fidelity.rules import hard_failures
from wke.core.summaries.fidelity.runs import missing_runs
from wke.core.summaries.fidelity.tokens import content, tokens, words

__all__ = ["content", "hard_failures", "missing_runs", "tokens", "words"]
