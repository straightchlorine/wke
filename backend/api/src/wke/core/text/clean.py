"""Text normalisation applied to every prose, list and table string."""

from __future__ import annotations

import re
import unicodedata

WHITESPACE = re.compile(r"\s+")
INVISIBLE = re.compile("[\u200b-\u200f\u2060\ufeff\u00ad\x00-\x08\x0e-\x1f\x7f]")


def clean_text(raw: str) -> str:
    """NFC-normalize, drop invisible and control characters, collapse whitespace.

    Zero-width characters, the soft hyphen and C0 controls are removed.
    Every prose, list and table text goes through this.

    Args:
        raw: decoded element text.

    Returns:
        str: the cleaned single-line text.
    """
    normalized = unicodedata.normalize("NFC", INVISIBLE.sub("", raw))
    return WHITESPACE.sub(" ", normalized).strip()
