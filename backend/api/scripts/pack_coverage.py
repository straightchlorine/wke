"""Show how the most important sections of stored dossiers reach a small pack.

Purpose: for each named topic, rank the non-lead prose sections with the
packer's importance score, take the top k that the pipeline would summarise
(k = clamp(round(prose tokens / 2000), 3, settings.summary_sections), 8 by
default), pack the stored dossier at a budget in-process and say whether each
of them arrives as a passage, as a model summary standing in for it, or not at
all. Reads Redis only (at --redis-url); no API call, no model call, no
rebuild.

A stored dossier has summaries only for the sections the old rule picked
(three, by passage count), so the "summary" column undercounts what a rebuilt
dossier would show.

Usage, from backend/api:

    uv run python scripts/pack_coverage.py --titles "Ted Kaczynski,Lizzie Borden,Madonna"
    uv run python scripts/pack_coverage.py --titles "Lizzie Borden" --budget 8000 --reparse
    uv run python scripts/pack_coverage.py --titles "Pac (wrestler)" --ranking

--ranking prints every non-lead section with its rank, its importance and how
it reaches the pack at the budget, so a ranking can be read in one table.
--pulled-dir reads a topic Redis does not hold from a pull.py folder.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import redis

from wke.core import pack
from wke.core.citations import seed_pin
from wke.core.models import Dossier
from wke.core.models.budgets import BUDGETS, BudgetTokens
from wke.jobs.build.select import select_summary_sections
from wke.offline.reparse import reparse
from wke.offline.store import (
    DEFAULT_REDIS,
    connect,
    load_dossier,
    load_html,
    load_pulled,
    stored_page_ids,
)
from wke.settings import settings


def _args() -> argparse.Namespace:
    """Parse the command line.

    Returns:
        argparse.Namespace: the parsed command line.
    """
    parser = argparse.ArgumentParser(description="Section coverage of a pack.")
    parser.add_argument("--titles", required=True, help="comma-separated article titles")
    parser.add_argument("--budget", type=int, default=2000, choices=BUDGETS)
    parser.add_argument("--reparse", action="store_true", help="re-parse cached Parsoid HTML")
    parser.add_argument("--redis-url", default=DEFAULT_REDIS)
    parser.add_argument("--ranking", action="store_true", help="list every ranked section")
    parser.add_argument("--pulled-dir", default="", help="pull.py folder for topics not in Redis")
    return parser.parse_args()


def find_dossier(client: redis.Redis, title: str, pulled_dir: str = "") -> Dossier | None:
    """Find a dossier by article title in Redis, else in a pull.py folder.

    Args:
        client: Redis client.
        title: article title, case-insensitive.
        pulled_dir: pull.py output folder to fall back to; empty for none.

    Returns:
        Dossier | None: the stored dossier, or None.
    """
    for page_id in stored_page_ids(client):
        dossier = load_dossier(client, page_id)
        if dossier is not None and dossier.topic.title.lower() == title.lower():
            return dossier
    if pulled_dir:
        for folder in sorted(Path(pulled_dir).glob("*-*")):
            dossier = load_pulled(pulled_dir, int(folder.name.split("-", 1)[0]))
            if dossier is not None and dossier.topic.title.lower() == title.lower():
                return dossier
    return None


def classify(
    dossier: Dossier, budget: BudgetTokens, everything: bool = False
) -> list[tuple[str, str, float]]:
    """Say how each top-k section reaches the pack.

    Args:
        dossier: the dossier to pack.
        budget: token budget.
        everything: list every ranked section, not only the top k.

    Returns:
        list[tuple]: (section label, "passage" | "summary" | "none", importance)
        for the top-k sections (all ranked sections with everything), most
        important first.
    """
    packed = pack.pack(dossier, budget)
    included = set(packed.budget.included_chunk_ids)
    scores = pack.section_importance(dossier.sections, dossier.chunks)
    ids = select_summary_sections(dossier.sections, dossier.chunks, settings.summary_sections)
    if everything:
        ids = [s.id for s in pack.ranked_sections(dossier.sections, dossier.chunks)]
    by_id = {s.id: s for s in dossier.sections}
    rows: list[tuple[str, str, float]] = []
    for sid in ids:
        section = by_id[sid]
        if any(cid in included for cid in section.chunk_ids):
            how = "passage"
        elif sid in packed.included_summary_section_ids:
            how = "summary"
        else:
            how = "none"
        rows.append((section.label, how, scores[sid]))
    return rows


def main() -> None:
    """Print the coverage table for each title."""
    args = _args()
    client = connect(args.redis_url)
    for title in [t.strip() for t in args.titles.split(",") if t.strip()]:
        dossier = find_dossier(client, title, args.pulled_dir)
        if dossier is None:
            print(f"{title}: not stored")
            continue
        if args.reparse:
            html = load_html(client, seed_pin(dossier).rev_id)
            if html is not None:
                dossier = reparse(dossier, html)
            else:
                print(f"{title}: HTML cache cold, using the stored dossier")
        rows = classify(dossier, args.budget, args.ranking)
        tally = {
            k: sum(1 for _, how, _ in rows if how == k) for k in ("passage", "summary", "none")
        }
        print(f"{title} at {args.budget}: top {len(rows)} sections -> {tally}")
        for rank, (label, how, score) in enumerate(rows, 1):
            print(f"  {rank:>2} {how:<8} {score:.2f}  {label}")


if __name__ == "__main__":
    main()
