"""Hand-rolled /llms.txt (llmstxt.org convention), cached 5 min in-process.

Explains how to get a dossier for any topic, then lists the ready
most-read topics so those links resolve 200. Omits the trending section
while no snapshot exists; never lists every stored dossier (the sitemap
does that).
"""

from __future__ import annotations

import time
from datetime import UTC, date, datetime, timedelta

from wke.core.errors import ApiException
from wke.core.models.budgets import BUDGETS, DEFAULT_BUDGET
from wke.core.render import escape_inline_markup
from wke.core.viewcache import current_generation
from wke.services.dossiers import DossierService

CACHE_TTL_SECONDS = 300

# (monotonic time, view generation, body) per base URL; a build bumps the
# generation so a new dossier is listed at once.
_cache: dict[str, tuple[float, int, str]] = {}


def most_read_heading(iso_date: str | date, now: datetime | None = None) -> str:
    """Name the most-read day plainly; say "yesterday" only when it is.

    Args:
        iso_date: The snapshot's day as YYYY-MM-DD (UTC) or a date.
        now: The current time, injectable for tests; defaults to UTC now.

    Returns:
        str: the heading text without the leading "## ".
    """
    moment = now or datetime.now(UTC)
    day = iso_date if isinstance(iso_date, str) else iso_date.isoformat()
    if day == (moment.date() - timedelta(days=1)).isoformat():
        return f"Most read on Wikipedia yesterday ({iso_date} UTC)"
    return f"Most read on Wikipedia on {iso_date} (UTC)"


def _instruction_lines(base: str) -> list[str]:
    """Write the plain-language steps for getting a dossier for any topic.

    Args:
        base: the scheme and host every link is rooted at.

    Returns:
        list[str]: Markdown lines from the "## Get a dossier" heading through
        the citation convention, each section ending in a blank line.
    """
    budgets = ", ".join(str(b) for b in BUDGETS)
    return [
        "## Get a dossier for any topic",
        "",
        "Any Wikipedia article can have a dossier. Find the page id, then read "
        "the dossier; if it is not built yet the API builds it and you read it "
        "again when the job is done.",
        "",
        f"1. Search: `GET {base}/api/v1/search?q={{title}}` returns candidates "
        "with `page_id` and `dossier_state`.",
        f"2. Build if needed: `POST {base}/api/v1/dossiers` with "
        '`{"title": "..."}` answers 202 with a job; poll '
        f"`GET {base}/api/v1/jobs/{{job_id}}` until it is done.",
        f"3. Read: `GET {base}/api/v1/dossiers/{{page_id}}.md?budget={DEFAULT_BUDGET}` "
        "for Markdown, or `GET "
        f"{base}/api/v1/dossiers/{{page_id}}?budget={DEFAULT_BUDGET}&format=json` for JSON. "
        "Add `summaries=false` to leave the model-written summaries out and "
        "spend the budget on source text.",
        "",
        "## Parts",
        "",
        "`parts` picks what a response carries, as a comma list of `dossier`, "
        "`metadata` and `sources`. The default is `dossier`: the sections and "
        "passages only, with no `[cN]` markers, no Sources list, no revision "
        "pin and no note on what was left out. Add `metadata` for the title, "
        "the revision pin, the budget line and the truncation note "
        "(`parts=dossier,metadata`); add `sources` for the `[cN]` citations "
        "and the Sources list (`parts=dossier,metadata,sources`). The "
        "CC BY-SA licence line is always last.",
        "",
        'JSON is `{"schema_version": "2", "license_notice": ..., '
        '"dossier": {sections, chunks, graph}, "metadata": ..., '
        '"sources": ...}`; parts you did not ask for are absent. The '
        "earlier flat JSON shape is no longer served. `WKE-Dossier-Tokens` "
        "and `WKE-Total-Tokens` response headers give the counted and the "
        "delivered size.",
        "",
        "## Budgets",
        "",
        f"`budget` is a token count: {budgets} (about 2k, 8k and 32k). The "
        f"default is {DEFAULT_BUDGET}. A larger budget keeps more sections "
        "and more passages. The budget counts the dossier part only (headings, "
        "passages, summaries and `[cN]` tags); metadata and Sources come on "
        "top, and the dossier part never exceeds the budget you ask for.",
        "",
        "## MCP",
        "",
        f"Server URL: {base}/mcp (streamable HTTP, no auth).",
        "",
        "- `search_topics(query, limit=8)`: candidate articles with build state.",
        f'- `get_dossier(title, budget={DEFAULT_BUDGET}, format="markdown", parts="dossier")`: '
        "builds the dossier if missing and returns it, or a `building` status "
        "with `job_id` and `retry_after_s` to call again.",
        "- `get_trending(limit=10)`: yesterday's most-read topics.",
        "",
        "```json",
        '{"mcpServers": {"wke": {"url": "' + base + '/mcp"}}}',
        "```",
        "",
        "## Citations",
        "",
        "Quoted text is Wikipedia content (CC BY-SA 4.0), pinned to one "
        "revision. Cite a passage by the exact section URL of its `[cN]` marker, "
        "as `[Title, section](permalink)`: ask for `parts=dossier,metadata,sources`; "
        "the default response has no markers, no Sources list and no revision pin. "
        "Summaries are model output and labelled as such; never cite them as "
        "Wikipedia text.",
        "",
        f"OpenAPI: {base}/openapi.json",
        "",
    ]


def _dossier_line(base: str, title: str, page_id: int, description: str | None) -> str:
    """Format one dossier list entry.

    Args:
        base: the scheme and host every link is rooted at.
        title: article title.
        page_id: Wikipedia page id.
        description: short article description, if any.

    Returns:
        str: a Markdown list item linking the dossier's .md route.
    """
    return (
        f"- [{title}]({base}/api/v1/dossiers/{page_id}.md?budget={DEFAULT_BUDGET}): "
        f"{escape_inline_markup(description or '')}"
    )


async def render_llms_txt(service: DossierService, limit: int = 40) -> str:
    """Render (or return the cached) /llms.txt body.

    Args:
        service: shared DossierService instance; its `base_url` (built
            from PUBLIC_SCHEME and PUBLIC_HOST) roots every link here, the
            same base every dossier's `links.self` is rooted at.
        limit: max topics to list.

    Returns:
        str: the Markdown body, per llmstxt.org.
    """
    base = service.base_url
    cached = _cache.get(base)
    now = time.monotonic()
    generation = current_generation()
    if cached is not None and cached[1] == generation and now - cached[0] < CACHE_TTL_SECONDS:
        return cached[2]

    lines = [
        "# Wikipedia Knowledge Explorer",
        "",
        "> Cited context from Wikipedia, for people and for LLMs. "
        "Every passage is cited to an exact revision; every summary is "
        "labelled as model output.",
        "",
        *_instruction_lines(base),
    ]

    try:
        snapshot = await service.get_trending(limit)
    except (NotImplementedError, ApiException):
        # Cold Redis, or no trending snapshot yet (before the first
        # wke-trending run): omit the "Most read" section rather than
        # answering the whole document with an error.
        snapshot = None

    listed_page_ids: set[int] = set()
    if snapshot is not None:
        ready_topics = [t for t in snapshot.topics if t.dossier_state == "ready"][:limit]
        lines.append(f"## {most_read_heading(snapshot.date)}")
        lines.append("")
        for topic in ready_topics:
            lines.append(_dossier_line(base, topic.title, topic.page_id, topic.description))
            listed_page_ids.add(topic.page_id)
        lines.append("")

    lines.extend(
        [
            "## Optional",
            "",
            "- For machines: " + base + "/machines",
            "- Source repository: https://github.com/straightchlorine/wke",
            "",
        ]
    )

    body = "\n".join(lines)
    _cache[base] = (now, generation, body)
    return body
