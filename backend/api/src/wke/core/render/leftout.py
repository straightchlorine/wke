"""The Left out line: which sections the Markdown does not show, and why."""

from __future__ import annotations

from wke.core.models import Section
from wke.core.pack.layout import SectionLayout
from wke.core.render.escape import escape_inline_markup
from wke.core.render.notes import plural

MAX_NAMED_SECTIONS = 8


def _group(sections: list[Section], reason: str, room: int) -> tuple[str, int]:
    """Describe one group of left-out sections, naming the first ones that fit the room.

    Args:
        sections: the group, in document order.
        reason: why they are left out.
        room: how many titles may still be named.

    Returns:
        tuple[str, int]: the text of the group and the room left after it.
    """
    head = f"{plural(len(sections), 'section')} {reason}"
    named = sections[:room]
    if not named:
        return head, 0
    titles = ", ".join(escape_inline_markup(s.label) for s in named)
    more = len(sections) - len(named)
    if more:
        titles += f" and {plural(more, 'more section')}"
    return f"{head}: {titles}", max(room - len(sections), 0)


def left_out_header(layout: SectionLayout) -> str | None:
    """Name the sections the Markdown leaves out, and why, on one line.

    Args:
        layout: the section layout for the rendered budget.

    Returns:
        str | None: "Left out: ..." with one group per reason (no prose in the
        article, or no passage fitting the budget), each with its count and
        the titles of its first sections in document order; at most
        MAX_NAMED_SECTIONS titles in all, the rest as "and N more sections".
        None when nothing is left out.
    """
    groups: list[str] = []
    room = MAX_NAMED_SECTIONS
    for sections, reason in (
        (layout.no_prose, "without prose"),
        (layout.budget_empty, "left out at this budget"),
    ):
        if sections:
            text, room = _group(sections, reason, room)
            groups.append(text)
    return "Left out: " + "; ".join(groups) if groups else None
