"""Token estimate shared by the parser, the packer and the build pipeline."""

from __future__ import annotations

import math

CHARS_PER_TOKEN = 4


def est_tokens(text: str) -> int:
    """Estimate the token count of text at CHARS_PER_TOKEN characters per token.

    Args:
        text: any string.

    Returns:
        int: the character count divided by CHARS_PER_TOKEN, rounded up.
    """
    return math.ceil(len(text) / CHARS_PER_TOKEN)
