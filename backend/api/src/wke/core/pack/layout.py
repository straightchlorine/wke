"""Which sections the Markdown emits at one budget, and why others are left out."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from wke.core.models import Section


@dataclass(frozen=True)
class SectionLayout:
    """Which sections the Markdown emits at one budget, and why others are not.

    Attributes:
        kept_ids: Ids of the sections that get a heading.
        no_prose: Left-out sections the build found no content in, in
            document order.
        budget_empty: Left-out sections with content of which nothing
            (no passage, table or summary) fit the budget, in document order.
    """

    kept_ids: frozenset[str]
    no_prose: list[Section]
    budget_empty: list[Section]


def section_layout(
    sections: list[Section],
    included_chunk_ids: Iterable[str],
    summary_section_ids: Iterable[str] = (),
) -> SectionLayout:
    """Decide which sections are emitted for a set of included passages.

    Args:
        sections: all sections in document order.
        included_chunk_ids: ids of the chunks the budget kept.
        summary_section_ids: ids of the sections whose summary is shown.

    Returns:
        A SectionLayout. A section with an included chunk or summary is
        kept. One without is kept only when a descendant (a following
        section nested under its heading_path) has some, so the descendant
        keeps its place in the outline; otherwise it is left out, as
        "no_prose" when the build found no content in it and as
        "budget_empty" when the budget dropped all of it.
    """
    included = set(included_chunk_ids)
    summarised = set(summary_section_ids)
    has_content = [
        section.id in summarised or any(cid in included for cid in section.chunk_ids)
        for section in sections
    ]
    kept: set[str] = set()
    no_prose: list[Section] = []
    budget_empty: list[Section] = []
    for index, section in enumerate(sections):
        keep = has_content[index]
        path = section.heading_path
        depth = len(path)

        if not keep and depth:
            for offset, later in enumerate(sections[index + 1 :], start=index + 1):
                if later.heading_path[:depth] != path or len(later.heading_path) <= depth:
                    break
                if has_content[offset]:
                    keep = True
                    break

        if keep:
            kept.add(section.id)
        elif not section.chunk_ids:
            no_prose.append(section)
        else:
            budget_empty.append(section)

    return SectionLayout(frozenset(kept), no_prose, budget_empty)
