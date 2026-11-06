"""Acceptance validator: run every check on one packed dossier view."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from wke.core.models import DossierView
from wke.core.validate.chunks import check_chunks
from wke.core.validate.citations import check_citations
from wke.core.validate.markdown import check_markers
from wke.core.validate.report import ValidationReport
from wke.core.validate.summaries import check_summaries


def validate_view(
    view: DossierView,
    markdown: str | None = None,
    headings: Callable[[int], Mapping[str, str] | None] | None = None,
) -> ValidationReport:
    """Validate one packed dossier view and, when given, its Markdown.

    Args:
        view: the view as served at one budget.
        markdown: the Markdown rendered from the same view; marker checks
            run only when given.
        headings: rev id -> heading id/text map of that revision's Parsoid
            HTML, or None when the HTML is not cached. Anchor checks are
            counted as skipped when this is not given or returns None.

    Returns:
        ValidationReport: counts per check and one line per failure.
    """
    report = ValidationReport()
    check_chunks(view, report)
    check_summaries(view, report)
    if markdown is not None:
        check_markers(view, markdown, report)
    check_citations(view, headings, report)
    return report
