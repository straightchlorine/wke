"""Record a recentchange SSE fixture for the wke-watcher test suite.

Streams live events from the Wikimedia EventStreams recentchange feed and
writes the first 200 dispatched SSE events (in SSE framing: `event:`, `id:`,
`data:` lines, blank-line separated) to recentchange.sse in this directory.
Each `data:` payload has its personal data replaced (`scrub_event`) and is
re-serialised with `ensure_ascii=True`, so the fixture file is pure ASCII.
Run from this directory as:

    uv run python record_sse.py

Writes recentchange.sse to the current directory.
Every request parameter is a fixed constant.
"""

from __future__ import annotations

import ipaddress
import json
from typing import Any

import httpx

STREAM_URL = "https://stream.wikimedia.org/v2/stream/recentchange"
USER_AGENT = f"wke/0.1.0 (https://github.com/straightchlorine/wke) httpx/{httpx.__version__}"
EVENT_COUNT = 200
OUTPUT_PATH = "recentchange.sse"

# Fields that only repeat the title or carry log parameters; the watcher reads none.
DROPPED_FIELDS = ("title_url", "notify_url", "log_params")
SUMMARY_FIELDS = ("comment", "parsedcomment", "log_action_comment")
SUMMARY_PLACEHOLDER = "Example edit summary"
USER_NAMESPACES = (2, 3)


def placeholder_user(user: str, index: int) -> str:
    """Build a stand-in for a username that keeps its kind.

    Args:
        user: the real username.
        index: 1-based position of the user in first-seen order.

    Returns:
        str: a documentation-range IP address for an IP, a `~` name for a
        temporary account, else "Example user N".
    """
    try:
        address = ipaddress.ip_address(user)
    except ValueError:
        return f"~2026-00000-{index:02d}" if user.startswith("~") else f"Example user {index}"
    if address.version == 4:
        return f"192.0.2.{index % 254 + 1}"
    return f"2001:db8::{index:x}"


def scrub_event(payload: dict[str, Any], aliases: dict[str, str]) -> dict[str, Any]:
    """Replace the personal data of one event, keeping what the watcher reads.

    Usernames become stable placeholders of the same kind, so the watcher's IP
    check classifies them as before; user-page titles take the same placeholder;
    a non-empty edit summary becomes a fixed text, so a test can still see the
    watcher drop it; title copies and log parameters are removed.

    Args:
        payload: the parsed event, modified in place.
        aliases: real username to placeholder, shared across one recording.

    Returns:
        dict[str, Any]: the scrubbed event.
    """

    def alias(user: str) -> str:
        if user not in aliases:
            aliases[user] = placeholder_user(user, len(aliases) + 1)
        return aliases[user]

    for field in DROPPED_FIELDS:
        payload.pop(field, None)
    meta = payload.get("meta")
    if isinstance(meta, dict):
        meta.pop("uri", None)
    for field in SUMMARY_FIELDS:
        if payload.get(field):
            payload[field] = SUMMARY_PLACEHOLDER
    user = payload.get("user")
    if isinstance(user, str):
        payload["user"] = alias(user)
    title = payload.get("title")
    if payload.get("namespace") in USER_NAMESPACES and isinstance(title, str) and ":" in title:
        prefix, rest = title.split(":", 1)
        payload["title"] = f"{prefix}:{alias(rest.split('/', 1)[0])}"
    return payload


def main() -> None:
    """Stream live events and write the first EVENT_COUNT, scrubbed, to disk."""
    headers = {"User-Agent": USER_AGENT, "Accept": "text/event-stream"}
    written = 0
    lines: list[str] = []
    aliases: dict[str, str] = {}
    with httpx.stream("GET", STREAM_URL, headers=headers, timeout=60.0) as response:
        response.raise_for_status()
        event_type = "message"
        event_id = None
        data_lines: list[str] = []
        for raw_line in response.iter_lines():
            line = raw_line.rstrip("\r")
            if line == "":
                if data_lines:
                    payload = scrub_event(json.loads("\n".join(data_lines)), aliases)
                    ascii_payload = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
                    lines.append(f"event: {event_type}")
                    if event_id is not None:
                        lines.append(f"id: {event_id}")
                    lines.append(f"data: {ascii_payload}")
                    lines.append("")
                    written += 1
                data_lines = []
                event_type = "message"
                event_id = None
                if written >= EVENT_COUNT:
                    break
                continue
            if line.startswith(":"):
                continue
            field, _, value = line.partition(":")
            if value.startswith(" "):
                value = value[1:]
            if field == "data":
                data_lines.append(value)
            elif field == "event":
                event_type = value
            elif field == "id":
                event_id = value
    with open(OUTPUT_PATH, "w", encoding="ascii") as handle:
        handle.write("\n".join(lines) + "\n")
    print(f"wrote {written} events to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
