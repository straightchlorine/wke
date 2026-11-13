"""Text normalisation applied to every prose, list and table string."""

from __future__ import annotations

import re
import unicodedata

WHITESPACE = re.compile(r"\s+")
# Code points clean_text deletes, as a str.translate table: zero-width characters,
# the soft hyphen, DEL and the C0 controls except tab, LF, VT, FF and CR.
INVISIBLE = dict.fromkeys(
    [*range(0x200B, 0x2010), 0x2060, 0xFEFF, 0x00AD, *range(0x00, 0x09), *range(0x0E, 0x20), 0x7F]
)


def clean_text(raw: str) -> str:
    """NFC-normalize, drop invisible and control characters, collapse whitespace.

    Zero-width characters, the soft hyphen and C0 controls are removed.
    Every prose, list and table text goes through this.

    Args:
        raw: decoded element text.

    Returns:
        str: the cleaned single-line text.
    """
    normalized = unicodedata.normalize("NFC", raw.translate(INVISIBLE))
    return WHITESPACE.sub(" ", normalized).strip()
