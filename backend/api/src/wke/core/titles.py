"""Title validation and normalization.

MediaWiki titles: underscores are spaces, the first letter is always
capitalized, and a fixed set of characters can never appear in a title
(they are wikitext or URL syntax). Every title that reaches a Wikimedia
call or a cache key has gone through `normalize_title`.
"""

from __future__ import annotations

import re
import unicodedata

from wke.core.errors import ApiException

TITLE_PATTERN = re.compile(r"^[^#<>\[\]|{}\x00-\x1f\x7f]+$")
MIN_TITLE_LENGTH = 1
MAX_TITLE_LENGTH = 255


def normalize_title(raw: str) -> str:
    """Validate and normalize a title for Wikimedia calls and cache keys.

    Args:
        raw: title as typed by a user or passed by an MCP client.

    Returns:
        str: NFC-normalized title, underscores replaced with spaces,
        first letter uppercased.

    Raises:
        ApiException: 422 validation_error if the title is empty, too
            long, or contains a disallowed character.
    """
    normalized = unicodedata.normalize("NFC", raw).replace("_", " ").strip()
    if not (MIN_TITLE_LENGTH <= len(normalized) <= MAX_TITLE_LENGTH):
        raise ApiException(
            422,
            "validation_error",
            detail=f"title must be {MIN_TITLE_LENGTH}-{MAX_TITLE_LENGTH} characters.",
        )
    if not TITLE_PATTERN.match(normalized):
        raise ApiException(422, "validation_error", detail="title contains a disallowed character.")
    return normalized[0].upper() + normalized[1:]
