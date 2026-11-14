"""Builds e2e/fixtures/dossiers.json from the "ready" topics of trending.json.

page_id, title and rev_id are copied from trending.json. Every other field
is made up and varies by row so the dossiers index shows each state:
pinned_at and built_at are fixed 2026-09-27 times, every fifth row is
"unknown" with no edits, the others are "fresh" or "stale" by
edits_since_pin, and largest_budget_filled and sections cycle through
fixed values.

Run with plain python3 (stdlib only), after make_trending.py:

    python3 e2e/fixtures/make_dossiers.py
"""

import json
from pathlib import Path

TRENDING = Path(__file__).resolve().parent / "trending.json"
OUT = Path(__file__).resolve().parent / "dossiers.json"

BUDGETS = [2000, 8000, 32000]


def main() -> None:
    snapshot = json.loads(TRENDING.read_text(encoding="ascii"))
    ready = [t for t in snapshot["topics"] if t["dossier_state"] == "ready"]

    items = []
    for i, topic in enumerate(ready):
        minute = i % 10
        second = (i * 7) % 60
        pinned_at = f"2026-09-27T03:0{minute}:{second:02d}Z"
        built_at = f"2026-09-27T03:0{minute}:{(second + 4) % 60:02d}Z"
        if i % 5 == 4:
            freshness_state = "unknown"
            edits_since_pin = 0
        else:
            edits_since_pin = i % 4
            freshness_state = "fresh" if edits_since_pin == 0 else "stale"
        items.append(
            {
                "page_id": topic["page_id"],
                "title": topic["title"],
                "rev_id": topic["rev_id"],
                "pinned_at": pinned_at,
                "freshness_state": freshness_state,
                "edits_since_pin": edits_since_pin,
                "largest_budget_filled": BUDGETS[i % 3],
                "sections": 5 + (i % 8),
                "built_at": built_at,
            }
        )

    body = {"items": items, "next_cursor": None}
    OUT.write_text(json.dumps(body, indent=2, ensure_ascii=True) + "\n", encoding="ascii")
    print(f"wrote {OUT} with {len(items)} dossiers")


if __name__ == "__main__":
    main()
