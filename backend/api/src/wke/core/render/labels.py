"""Labels and heading levels of the Markdown rendering."""

from __future__ import annotations

from wke.core.models import Section

SUMMARY_LABEL = "Machine summary (model output)"
FACTS_LABEL = "Key facts"
MAX_HEADING_LEVEL = 6


def heading_prefix(section: Section) -> str:
    """Markdown heading marks for a section, from its depth in the article.

    Args:
        section: the section to head.

    Returns:
        str: "##" for the lead and top-level sections, "###" for their
        subsections, and so on down to six.
    """
    return "#" * min(MAX_HEADING_LEVEL, 1 + max(1, len(section.heading_path)))
