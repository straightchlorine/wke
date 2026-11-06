"""Checks on the machine summaries of a view."""

from __future__ import annotations

from wke.core.models import DossierView
from wke.core.text.navigation import points_elsewhere
from wke.core.text.sentences import ends_at_sentence_end
from wke.core.validate.report import ValidationReport


def check_summaries(view: DossierView, report: ValidationReport) -> None:
    """Check that each summary ends at a sentence end, points nowhere and cites its section.

    Args:
        view: the view as served at one budget.
        report: receives the counts and failures.
    """
    for section in view.sections:
        summary = section.summary
        if summary is None:
            continue

        report.counts["summaries"] += 1
        if not ends_at_sentence_end(summary.text):
            report.fail("fragment_summaries", f"{section.id}: {summary.text[-60:]!r}")
        if points_elsewhere(summary.text):
            report.fail("navigation_summaries", f"{section.id}: {summary.text[:60]!r}")
        if not section.citation_id or summary.citation_id != section.citation_id:
            report.fail("wrong_summary_citation", f"{section.id}: {summary.citation_id}")
