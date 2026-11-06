"""Checks on the citation markers of the rendered Markdown."""

from __future__ import annotations

import re

from wke.core.models import DossierView
from wke.core.validate.report import ValidationReport

MARKER_LINE = re.compile(r"^\[(c\d+|\?)\]$")


def summary_markers(markdown: str) -> list[str]:
    """Return the citation marker that follows each summary block, in order.

    Args:
        markdown: the rendered Markdown.

    Returns:
        list[str]: one marker id per summary block; "" for a block that the
        next heading, model line or bold label reaches before any marker.
    """
    lines = markdown.splitlines()
    found: list[str] = []
    for index, line in enumerate(lines):
        if not line.startswith("**Machine summary"):
            continue

        for follower in lines[index + 1 :]:
            match = MARKER_LINE.match(follower)
            if match:
                found.append(match.group(1))
                break
            if follower.startswith(("Model:", "#", "**")):
                found.append("")
                break

    return found


def check_markers(view: DossierView, markdown: str, report: ValidationReport) -> None:
    """Check that every marker names a citation and each summary cites its section.

    Args:
        view: the view the Markdown was rendered from.
        markdown: the rendered Markdown.
        report: receives the counts and failures.
    """
    citations = {c.id: c for c in view.citations}
    markers = [m.group(1) for ln in markdown.splitlines() if (m := MARKER_LINE.match(ln))]
    for marker in markers:
        report.counts["markers"] += 1
        if marker not in citations:
            report.fail("unresolved_markers", marker)

    expected_after = [s.citation_id or "" for s in view.sections if s.summary is not None]
    found_after = summary_markers(markdown)
    if len(found_after) != len(expected_after):
        report.fail(
            "wrong_summary_marker",
            f"{len(found_after)} summaries in the Markdown, {len(expected_after)} in the view",
        )

    for found, wanted in zip(found_after, expected_after, strict=False):
        if found != wanted:
            report.fail("wrong_summary_marker", f"{found!r} after summary, wanted {wanted!r}")
