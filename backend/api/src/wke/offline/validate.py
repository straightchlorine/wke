"""Run the dossier validator over every stored dossier."""

from __future__ import annotations

from typing import TypedDict

import redis

from wke.core.citations import seed_pin
from wke.core.models.budgets import BUDGETS, BudgetTokens
from wke.core.validate import ValidationReport, heading_map, validate_view
from wke.offline.reparse import reparse, view_and_markdown
from wke.offline.store import load_dossier, load_html, stored_page_ids


class StoredValidation(TypedDict):
    """The summary validate_stored returns."""

    dossiers_checked: int
    skipped_cold_html: int
    totals: dict[str, int]
    problem_count: int
    problems: list[str]


def validate_stored(
    client: redis.Redis,
    budgets: tuple[BudgetTokens, ...] = BUDGETS,
    do_reparse: bool = False,
    page_ids: list[int] | None = None,
) -> StoredValidation:
    """Run the dossier validator over every stored dossier at each budget.

    Heading ids come from the Parsoid HTML cached in Redis; a revision whose
    HTML cache is cold counts as skipped, and nothing is fetched.

    Args:
        client: Redis client.
        budgets: token budgets to pack and render.
        do_reparse: validate the dossier as the current parser would build it
            (needs the cached HTML) instead of as stored.
        page_ids: page ids to check; every stored dossier when None or empty.

    Returns:
        StoredValidation: totals per check across all dossiers and budgets, the
        number of dossiers checked and skipped by reparse, and up to 30 problem
        lines.
    """
    totals: dict[str, int] = {}
    problems: list[str] = []
    checked = reparse_skipped = 0
    html_cache: dict[int, dict[str, str] | None] = {}

    def headings(rev_id: int) -> dict[str, str] | None:
        if rev_id not in html_cache:
            html = load_html(client, rev_id)
            html_cache[rev_id] = heading_map(html) if html else None
        return html_cache[rev_id]

    for page_id in page_ids or stored_page_ids(client):
        dossier = load_dossier(client, page_id)
        if dossier is None:
            continue
        if do_reparse:
            html = load_html(client, seed_pin(dossier).rev_id)
            if html is None:
                reparse_skipped += 1
                continue
            dossier = reparse(dossier, html)
        checked += 1
        for budget in budgets:
            view, markdown = view_and_markdown(dossier, budget)
            report: ValidationReport = validate_view(view, markdown, headings)
            for kind, count in report.counts.items():
                totals[kind] = totals.get(kind, 0) + count
            problems.extend(f"{page_id}@{budget} {line}" for line in report.problems)
    return {
        "dossiers_checked": checked,
        "skipped_cold_html": reparse_skipped,
        "totals": dict(sorted(totals.items())),
        "problem_count": len(problems),
        "problems": problems[:30],
    }
