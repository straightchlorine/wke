"""Hex digests used inside Redis key names."""

from __future__ import annotations

import hashlib


def sha1_hex(value: str) -> str:
    """Hash a string with SHA-1.

    Args:
        value: the text to hash.

    Returns:
        str: the hex digest.
    """
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def sha256_hex(value: str) -> str:
    """Hash a string with SHA-256.

    Args:
        value: the text to hash.

    Returns:
        str: the hex digest.
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
