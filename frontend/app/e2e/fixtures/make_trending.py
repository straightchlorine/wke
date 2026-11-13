"""Builds e2e/fixtures/trending.json from a real recorded Wikimedia feed.

Reads backend/api/tests/fixtures/wm/mostread.json, a recording of the
featured-feed "most read" endpoint. Keeps the articles in namespace 0 and
drops Main_Page, "-", titles starting with List_of_ or Deaths_in_, and
titles with a namespace prefix such as Special: or File:. It then keeps
the first 40 by rank, marks the first 30 "ready" and the rest "partial",
"building" and "none" in turn, embeds the first 280 characters of each
lead with sentence-transformers/all-MiniLM-L6-v2, and keeps each node's
two nearest neighbours at cosine similarity 0.35 or more as undirected
edges (at most 80, weights rounded to 3 decimals).

Run from backend/ml so the model's already-installed venv is used:

    cd backend/ml && uv run python \
        ../../frontend/app/e2e/fixtures/make_trending.py

Raises:
    SystemExit: if the source fixture is missing or has fewer than 40
        articles left after filtering.
"""

import json
from pathlib import Path

from sentence_transformers import SentenceTransformer

REPO_ROOT = Path(__file__).resolve().parents[4]
SOURCE = REPO_ROOT / "backend" / "api" / "tests" / "fixtures" / "wm" / "mostread.json"
OUT = Path(__file__).resolve().parent / "trending.json"

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_REVISION = "1110a243"

NAMESPACE_PREFIXES = (
    "Special:",
    "Wikipedia:",
    "File:",
    "Portal:",
    "Help:",
    "Template:",
    "Category:",
    "Talk:",
    "User:",
    "Draft:",
    "Module:",
)


def is_filtered(canonical: str) -> bool:
    """Applies the trending job's step-2 filter to one canonical title.

    Args:
        canonical: The article's canonical (underscored) title.

    Returns:
        True if the article should be dropped from the trending set.
    """
    if canonical in ("Main_Page", "-"):
        return True
    if canonical.startswith("List_of_") or canonical.startswith("Deaths_in_"):
        return True
    return any(canonical.startswith(p) for p in NAMESPACE_PREFIXES)


def main() -> None:
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    articles = sorted(data["articles"], key=lambda a: a["rank"])

    kept = []
    for a in articles:
        titles = a.get("titles", {})
        canonical = titles.get("canonical", a.get("title", ""))
        if a.get("namespace", {}).get("id") != 0:
            continue
        if is_filtered(canonical):
            continue
        kept.append(a)

    if len(kept) < 40:
        raise SystemExit(f"only {len(kept)} articles left after filtering, need 40")

    kept = kept[:40]

    leads = [a.get("extract", "")[:280] for a in kept]

    model = SentenceTransformer(MODEL_NAME, revision=MODEL_REVISION)
    embeddings = model.encode(leads, normalize_embeddings=True)

    n = len(kept)
    page_ids = [a["pageid"] for a in kept]
    edge_set: dict[tuple[int, int], float] = {}
    for i in range(n):
        sims = []
        for j in range(n):
            if i == j:
                continue
            sim = float(embeddings[i] @ embeddings[j])
            sims.append((sim, j))
        sims.sort(key=lambda x: x[0], reverse=True)
        for sim, j in sims[:2]:
            if sim < 0.35:
                continue
            key = (min(i, j), max(i, j))
            weight = round(sim, 3)
            if key not in edge_set or weight > edge_set[key]:
                edge_set[key] = weight

    # GraphEdge.source/target use page ids (not positional indices into `topics`)
    edges = sorted(
        (
            {"source": page_ids[i], "target": page_ids[j], "weight": w}
            for (i, j), w in edge_set.items()
        ),
        key=lambda e: e["weight"],
        reverse=True,
    )[:80]

    topics = []
    for idx, a in enumerate(kept):
        titles = a.get("titles", {})
        title = titles.get("normalized") or a.get("normalizedtitle") or a.get("title")
        if idx < 30:
            state = "ready"
        else:
            state = ["partial", "building", "none"][(idx - 30) % 3]
        topics.append(
            {
                # Re-ranked 1..40 after namespace/list filters
                "rank": idx + 1,
                "page_id": a["pageid"],
                "title": title,
                "description": a.get("description"),
                "views": a["views"],
                "rev_id": int(a["revision"]),
                "lead_excerpt": a.get("extract", "")[:280],
                "dossier_state": state,
                "edits_last_hour": 0,
            }
        )

    source_date = data["date"].rstrip("Z")

    snapshot = {
        "schema_version": "1",
        "date": source_date,
        "source": "wikifeeds_mostread",
        "source_url": (
            f"https://en.wikipedia.org/api/rest_v1/feed/featured/{source_date.replace('-', '/')}"
        ),
        "generated_at": f"{source_date}T03:00:00Z",
        "next_refresh": None,
        "topics": topics,
        "edges": edges,
    }

    OUT.write_text(json.dumps(snapshot, indent=2, ensure_ascii=True) + "\n", encoding="ascii")
    print(f"wrote {OUT} with {len(topics)} topics and {len(edges)} edges")


if __name__ == "__main__":
    main()
