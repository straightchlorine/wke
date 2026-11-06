"""Token costs of the Markdown that surrounds passages and summaries."""

from __future__ import annotations

from wke.core.text.tokens import est_tokens

SECTION_HEADING_OVERHEAD_TOKENS = 16

# markdown surrounding each item, so that it's accounted for in the budget
TAG_TOKENS = 2
SUMMARY_FRAME_TOKENS = 36


def summary_cost(text: str) -> int:
    """Estimate what a section summary costs with its label and citation tag.

    Args:
        text: the summary text.

    Returns:
        int: the text tokens plus SUMMARY_FRAME_TOKENS and TAG_TOKENS.
    """
    return est_tokens(text) + SUMMARY_FRAME_TOKENS + TAG_TOKENS
