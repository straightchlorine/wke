"""Load stored dossiers from Redis and pack them in this process.

Purpose: measure packing and rendering changes on the dossiers already stored,
without rebuilding them and without a Wikimedia call. `reparse` goes one step
further and re-runs the current parser over the Parsoid HTML cached in Redis,
carrying over the stored relevance and summaries, so tables, key facts, section
citations and the summary source check show up on old dossiers too.

Output: one <page_id>-<slug> folder per dossier in --out-dir, in the layout
pull.py writes, so the dossier-control checker runs on it.

Usage, from backend/api:

    uv run python scripts/offline_dossier.py --out-dir ../../.run/offline
    uv run python scripts/offline_dossier.py --out-dir /tmp/o --reparse

--pulled-dir is where the earlier pull.py output is read from, and defaults
to ../../.run/dossiers.

The loaders it shares with the other scripts live in `wke.offline`.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Any

import redis

from wke.core.citations import seed_pin
from wke.core.models.budgets import BUDGETS, BudgetTokens
from wke.offline.reparse import reparse, view_and_markdown
from wke.offline.store import (
    connect,
    load_dossier,
    load_html,
    load_pulled,
    load_pulled_html,
    stored_page_ids,
)


def _slug(title: str) -> str:
    """Lower-case a title into a folder-safe slug.

    Args:
        title: article title.

    Returns:
        str: ASCII letters, digits and hyphens only.
    """
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "dossier"


def write_offline_folders(
    client: redis.Redis,
    out_dir: str,
    pulled_dir: str = "../../.run/dossiers",
    budgets: tuple[BudgetTokens, ...] = BUDGETS,
    do_reparse: bool = False,
) -> list[str]:
    """Write rest-<budget>.json and .md per stored dossier in the pull.py layout.

    The manifest and the source HTML of an earlier pull of the same dossier
    are copied next to the files, so the dossier-control checker can run on
    the folder. A dossier without an earlier pull gets a minimal manifest and
    the source HTML from the Redis cache when it is warm. A pulled dossier
    that Redis no longer holds is rebuilt from its rest-32000.json.

    Args:
        client: Redis client.
        out_dir: folder that receives one <page_id>-<slug> folder per dossier.
        pulled_dir: folder holding the pull.py output to take manifests from.
        budgets: token budgets to pack and render.
        do_reparse: re-run the current parser over the cached HTML first.

    Returns:
        list[str]: the folders written.
    """
    written: list[str] = []
    pulled = Path(pulled_dir)
    pulled_ids = sorted(
        int(f.name.split("-", 1)[0]) for f in pulled.glob("*-*") if f.name[0].isdigit()
    )
    for page_id in sorted({*stored_page_ids(client), *pulled_ids}):
        dossier = load_dossier(client, page_id) or load_pulled(pulled_dir, page_id)
        if dossier is None:
            continue
        earlier = next(iter(pulled.glob(f"{page_id}-*")), None)
        if do_reparse:
            html = load_html(client, seed_pin(dossier).rev_id) or load_pulled_html(
                earlier, seed_pin(dossier).rev_id
            )
            if html is not None:
                dossier = reparse(dossier, html)
        title = dossier.topic.title
        rev_id = seed_pin(dossier).rev_id
        slug = earlier.name.split("-", 1)[1] if earlier else _slug(title)
        folder = Path(out_dir) / f"{page_id}-{slug}"
        folder.mkdir(parents=True, exist_ok=True)
        manifest: dict[str, Any] = {
            "page_id": page_id,
            "title": title,
            "slug": slug,
            "rev_id": rev_id,
            "budgets": list(budgets),
            "notes": [],
            "files": {},
        }
        if earlier is None:
            html = load_html(client, rev_id)
            if html is not None:
                (folder / f"source-{rev_id}.html").write_text(html, encoding="utf-8")
        elif (earlier / "manifest.json").exists():
            manifest = json.loads((earlier / "manifest.json").read_text())
            manifest["budgets"] = list(budgets)
            manifest["files"] = {}
            for source in earlier.glob("source-*.html"):
                shutil.copy(source, folder / source.name)
        for budget in budgets:
            view, markdown = view_and_markdown(dossier, budget)
            for name, text in (
                (f"rest-{budget}.json", view.model_dump_json()),
                (f"rest-{budget}.md", markdown),
            ):
                data = text.encode("utf-8")
                (folder / name).write_bytes(data)
                manifest["files"][name] = {"bytes": len(data), "status": 200}
        (folder / "manifest.json").write_text(
            json.dumps(manifest, indent=1, ensure_ascii=True) + "\n"
        )
        written.append(str(folder))
    return written


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--out-dir", required=True, help="write per-dossier folders here")
    parser.add_argument(
        "--pulled-dir", default="../../.run/dossiers", help="earlier pull.py output"
    )
    parser.add_argument("--reparse", action="store_true", help="re-run the current parser")
    args = parser.parse_args()
    for path in write_offline_folders(
        connect(), args.out_dir, pulled_dir=args.pulled_dir, do_reparse=args.reparse
    ):
        print(path)
