"""Number extraction shared by the summary checks."""

from __future__ import annotations

import re

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def number_tokens(text: str) -> list[str]:
    """List the numbers of a text without thousands commas.

    Args:
        text: any text.

    Returns:
        list[str]: the numbers in order of appearance.
    """
    return [m.replace(",", "") for m in _NUMBER.findall(text)]
