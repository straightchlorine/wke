"""The budget line: what the pack holds of the article, in one sentence."""

from __future__ import annotations

from wke.core.models import DossierView
from wke.core.pack.owners import chunk_kind
from wke.core.render.notes import plural, structured_counts

FLAT_NOTICE = "This dossier holds the whole article; larger budgets add nothing."
SHORTENED_CLAUSE = "some openings are shortened at a sentence end"
LINKS_CLAUSE = "inline links are not counted in the budget"


def _all_ids(view: DossierView) -> set[str]:
    """Return the ids of every chunk of the article, shown or not."""
    ids = {cid for section in view.sections for cid in section.chunk_ids}
    return ids | set(view.budget.included_chunk_ids)


def _passage_counts(view: DossierView) -> tuple[int, int]:
    """Return how many prose passages the budget holds and how many the article has."""
    included = set(view.budget.included_chunk_ids)
    prose = [cid for cid in _all_ids(view) if chunk_kind(cid) == "prose"]
    return sum(1 for cid in prose if cid in included), len(prose)


def _sections_shown(view: DossierView) -> int:
    """Count the sections with at least one prose passage in the pack."""
    included = set(view.budget.included_chunk_ids)
    return sum(
        1
        for section in view.sections
        if any(cid in included and chunk_kind(cid) == "prose" for cid in section.chunk_ids)
    )


def not_included(view: DossierView) -> str | None:
    """Name the lists and tables the extraction left out of every section.

    Args:
        view: A DossierView produced by build_view.

    Returns:
        str | None: "2 lists and 1 table not included", or None when none were left out.
    """
    lists = sum(section.dropped_lists for section in view.sections)
    tables = sum(section.dropped_tables for section in view.sections)
    parts = [plural(n, noun) for n, noun in ((lists, "list"), (tables, "table")) if n]
    return " and ".join(parts) + " not included" if parts else None


def holds_whole_article(view: DossierView) -> bool:
    """Tell whether the pack leaves nothing of the article out.

    Args:
        view: A DossierView produced by build_view.

    Returns:
        bool: True when it has passages, every passage, table and list is in,
        none is cut at a sentence or row boundary and the extraction dropped
        no list or table.
    """
    _, total = _passage_counts(view)
    return (
        total > 0
        and _all_ids(view) <= set(view.budget.included_chunk_ids)
        and not view.budget.shortened_chunk_ids
        and not_included(view) is None
    )


def budget_line(view: DossierView, links: bool = False) -> str:
    """State the requested budget, the passages it holds and what is out.

    Args:
        view: A DossierView produced by build_view.
        links: whether the Markdown carries inline links.

    Returns:
        str: "Budget 8,000 tokens: 49 of 116 passages" when the budget left
        passages out, "Budget 8,000 tokens: all 49 passages" otherwise ("the
        1 passage" for a single one, "no passages" for none), then "; 4
        tables and 1 list left out at this budget" for tables and lists the
        budget dropped, "; 2 lists and 1 table not included" for those the
        extraction left out and "; inline links are not counted in the
        budget" when links is set.
    """
    included, total = _passage_counts(view)
    if total == 0:
        passages = "no passages"
    elif included < total:
        passages = f"{included} of {total} passages"
    else:
        passages = "the 1 passage" if total == 1 else f"all {total} passages"

    parts = [f"Budget {view.budget.requested:,} tokens: {passages}"]
    shown_ids = set(view.budget.included_chunk_ids)
    left_out = [cid for cid in _all_ids(view) - shown_ids if chunk_kind(cid) != "prose"]
    if left_out:
        parts.append(f"{structured_counts(left_out)} left out at this budget")
    if excluded := not_included(view):
        parts.append(excluded)
    if links:
        parts.append(LINKS_CLAUSE)
    return "; ".join(parts)


def opening_note(view: DossierView) -> str | None:
    """Say how many sections show their opening passage and how many passages are out.

    Args:
        view: A DossierView produced by build_view.

    Returns:
        str | None: "Opening passages are shown for 7 sections; 88 passages are left out
        at this budget; some openings are shortened at a sentence end."
        with a clause dropped when its count is zero; None when no section
        has a passage.
    """
    shown = _sections_shown(view)
    if not shown:
        return None

    included, total = _passage_counts(view)
    out = total - included
    parts = [f"Opening passages are shown for {plural(shown, 'section')}"]
    if out:
        verb = "is" if out == 1 else "are"
        parts.append(f"{plural(out, 'passage')} {verb} left out at this budget")
    shown_ids = set(view.budget.included_chunk_ids)
    if any(
        cid in shown_ids and chunk_kind(cid) == "prose" for cid in view.budget.shortened_chunk_ids
    ):
        parts.append(SHORTENED_CLAUSE)
    return "; ".join(parts) + "."
