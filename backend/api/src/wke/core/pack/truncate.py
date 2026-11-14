"""Cut a passage back to whole sentences that fit a token budget."""

from __future__ import annotations

from wke.core.text.sentences import split_sentences
from wke.core.text.tokens import CHARS_PER_TOKEN


def truncate_lead(text: str, budget_tokens: int) -> str:
    """Cut a lead passage back to whole sentences that fit a token budget.

    Args:
        text: The full lead passage.
        budget_tokens: Tokens available for it (may be <= 0).

    Returns:
        The longest run of whole leading sentences within budget_tokens,
        never fewer than the first sentence, so the text starts and ends at
        sentence boundaries.
    """
    max_chars = max(budget_tokens, 0) * CHARS_PER_TOKEN
    sentences = split_sentences(text)
    out = ""
    for sentence in sentences:
        candidate = f"{out} {sentence}" if out else sentence
        if out and len(candidate) > max_chars:
            break
        out = candidate
    return out
