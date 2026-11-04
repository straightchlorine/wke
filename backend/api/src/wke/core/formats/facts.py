"""Text of a facts chunk."""

from __future__ import annotations


def facts_text(facts: list[tuple[str, str]]) -> str:
    """Render infobox facts as one "Label: value" line per row.

    Args:
        facts: (label, value) pairs.

    Returns:
        str: the lines joined with newlines.
    """
    return "\n".join(f"{label}: {value}" for label, value in facts)
