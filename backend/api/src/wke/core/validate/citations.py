"""Checks on the citation URLs and anchors of a view."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from urllib.parse import quote

from wke.core.citations import FRAGMENT_SAFE
from wke.core.models import DossierView
from wke.core.validate.report import ValidationReport


def check_citations(
    view: DossierView,
    headings: Callable[[int], Mapping[str, str] | None] | None,
    report: ValidationReport,
) -> None:
    """Check that citation URLs and anchors name real headings of the pinned revision.

    A seed citation's URL is its permalink, plus the anchor when it has one.

    Args:
        view: the view as served at one budget.
        headings: rev id -> heading id/text map of that revision's Parsoid
            HTML, or None when the HTML is not cached. Anchor checks are
            counted as skipped when this is not given or returns None.
        report: receives the counts and failures.
    """
    citations = {c.id: c for c in view.citations}
    revision_headings: dict[int, Mapping[str, str] | None] = {}
    for citation in view.citations:
        if citation.role != "seed":
            continue

        wanted_url = str(citation.pin.permalink)
        if citation.anchor:
            wanted_url += f"#{quote(citation.anchor, safe=FRAGMENT_SAFE)}"

        if str(citation.url) != wanted_url:
            report.fail("bad_citation_url", f"{citation.id}: {citation.url}")

        if not citation.anchor:
            continue

        rev = citation.pin.rev_id
        if rev not in revision_headings:
            revision_headings[rev] = headings(rev) if headings else None

        known = revision_headings[rev]
        if known is None:
            report.counts["anchors_skipped"] += 1
            continue

        report.counts["anchors_checked"] += 1
        if citation.anchor not in known:
            report.fail("bad_anchor", f"{citation.id}: #{citation.anchor}")

    if headings:
        for section in view.sections:
            citation = citations.get(section.citation_id or "")
            if citation is None or not citation.anchor or not section.heading_path:
                continue

            known = revision_headings.get(citation.pin.rev_id)
            # anchor missing from the revision is a bad_anchor.
            if (
                known
                and citation.anchor in known
                and known[citation.anchor] != section.heading_path[-1]
            ):
                report.fail("anchor_names_other_section", f"{section.id}: #{citation.anchor}")
