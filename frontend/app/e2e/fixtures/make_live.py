"""Builds e2e/fixtures/live.json from a real recorded recentchange stream.

Reads backend/api/tests/fixtures/wm/recentchange.sse (a recording of
stream.wikimedia.org/v2/stream/recentchange) and keeps the first 60 events
with wiki == enwiki, namespace == 0 and type edit or new. Each event gets
the page id of the trending.json topic with the same title, or null, and
an actor kind of bot, anonymous or registered; usernames and edit
comments are not copied. The counters block mixes values computed from
the kept events with fixed ones (dossiers_built_today is always 30).

Run with plain python3 (stdlib only, no ML dependency):

    python3 e2e/fixtures/make_live.py
"""

import json
import re
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
SSE_SOURCE = REPO_ROOT / "backend" / "api" / "tests" / "fixtures" / "wm" / "recentchange.sse"
TRENDING = Path(__file__).resolve().parent / "trending.json"
OUT = Path(__file__).resolve().parent / "live.json"

MAX_EVENTS = 60
IP_RE = re.compile(r"^(\d{1,3}\.){3}\d{1,3}$|^[0-9A-Fa-f:]+:[0-9A-Fa-f:]+$")


def user_kind(event: dict) -> str:
    """Classifies an edit's actor without keeping the actor's identity.

    Args:
        event: One parsed recentchange event.

    Returns:
        "bot", "anonymous" (IP-shaped username, so no account), or
        "registered".
    """
    if event.get("bot"):
        return "bot"
    user = event.get("user", "")
    if IP_RE.match(user):
        return "anonymous"
    return "registered"


def parse_sse(path: Path) -> list[dict]:
    """Parses an SSE recording into its `data:` JSON payloads.

    Args:
        path: Path to the recorded .sse file.

    Returns:
        One dict per `data:` line, in file order.
    """
    events = []
    for block in path.read_text(encoding="utf-8").split("\n\n"):
        for line in block.split("\n"):
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: ") :]))
    return events


def main() -> None:
    page_ids_by_title = {}
    index_date = None
    if TRENDING.exists():
        snapshot = json.loads(TRENDING.read_text(encoding="ascii"))
        index_date = snapshot["date"]
        for topic in snapshot["topics"]:
            page_ids_by_title[topic["title"]] = topic["page_id"]

    raw_events = parse_sse(SSE_SOURCE)

    kept = []
    for e in raw_events:
        if e.get("wiki") != "enwiki":
            continue
        if e.get("namespace") != 0:
            continue
        if e.get("type") not in ("edit", "new"):
            continue
        kept.append(e)
        if len(kept) >= MAX_EVENTS:
            break

    edits = []
    for cursor, e in enumerate(kept, start=1):
        revision = e.get("revision", {})
        length = e.get("length", {})
        rev_old = revision.get("old")
        len_old = length.get("old")
        len_new = length.get("new")
        byte_delta = len_new - len_old if len_old is not None and len_new is not None else None
        ts = datetime.fromtimestamp(e["timestamp"], tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        edits.append(
            {
                "cursor": cursor,
                "page_id": page_ids_by_title.get(e["title"]),
                "title": e["title"],
                "rev_new": revision["new"],
                "rev_old": rev_old,
                "ts": ts,
                "user_kind": user_kind(e),
                "byte_delta": byte_delta,
                "diff_url": e.get("notify_url"),
            }
        )

    server_time = edits[-1]["ts"] if edits else datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    tracked = sum(1 for edit in edits if edit["page_id"] is not None)

    live = {
        "stream": "connected",
        "server_time": server_time,
        "cursor": len(edits),
        "last_event_at": edits[-1]["ts"] if edits else None,
        "edits": edits,
        "counters": {
            "enwiki_edits_last_hour": len(edits),
            "tracked_edits_last_hour": tracked,
            "window_complete": False,
            "window_since": edits[0]["ts"] if edits else None,
            "dossiers_built_today": 30,
            "topics_tracked": len(page_ids_by_title),
            "index_date": index_date,
            "next_refresh": None,
        },
    }

    OUT.write_text(json.dumps(live, indent=2, ensure_ascii=True) + "\n", encoding="ascii")
    print(f"wrote {OUT} with {len(edits)} events, {tracked} matching tracked topics")


if __name__ == "__main__":
    main()
