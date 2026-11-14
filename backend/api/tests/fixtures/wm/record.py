"""Record Wikimedia and Wikifeeds fixtures for the wke-api test suite.

Fetches a fixed set of live responses for the "Jesus" article and
writes them, together with a META.json manifest, into this directory.
Run from this directory as:

    uv run python record.py

Writes resolve.json, parsoid.html, revision.json, morelike.json,
search.json, mostread.json, pageviews_top.json and META.json to the
current directory. Every request parameter is a fixed constant.
"""

from __future__ import annotations

import datetime
import json
import time
from typing import Any

import httpx
from selectolax.lexbor import LexborHTMLParser

TITLE = "Jesus"
ACTION_API = "https://en.wikipedia.org/w/api.php"
PARSOID_REVISION_BASE = "https://en.wikipedia.org/w/rest.php/v1/revision"
WIKIFEEDS_FEATURED_BASE = "https://en.wikipedia.org/api/rest_v1/feed/featured"
PAGEVIEWS_TOP_BASE = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/top/en.wikipedia/all-access"
)

USER_AGENT = f"wke/0.1.0 (https://github.com/straightchlorine/wke) httpx/{httpx.__version__}"
PACE_SECONDS = 1.5
DEFAULT_RETRY_AFTER_SECONDS = 5

# None keeps every section; an int keeps only that many leading sections.
SECTIONS_TO_KEEP = None
TODAY_UTC = datetime.date(2026, 9, 28)
MAX_PAGEVIEWS_BACKSTEPS = 1


def build_client() -> httpx.Client:
    """Build the single httpx client used for every request.

    Returns:
        httpx.Client: client with the project UA, gzip accepted, a 30 s
        timeout and redirects disabled.
    """
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Encoding": "gzip",
    }
    return httpx.Client(timeout=30, follow_redirects=False, headers=headers)


def needs_retry(response: httpx.Response) -> bool:
    """Decide whether a response should be retried once.

    Args:
        response: httpx.Response to inspect.

    Returns:
        bool: True on HTTP 429, or HTTP 200 carrying a maxlag or
        ratelimited error body.
    """
    if response.status_code == 429:
        return True
    content_type = response.headers.get("content-type", "")
    if response.status_code == 200 and "json" in content_type:
        try:
            body = response.json()
        except ValueError:
            return False
        if isinstance(body, dict):
            error = body.get("error")
            if isinstance(error, dict) and error.get("code") in ("maxlag", "ratelimited"):
                return True
    return False


def retry_after_seconds(response: httpx.Response) -> int:
    """Read the Retry-After header, defaulting when absent or malformed.

    Args:
        response: httpx.Response carrying an optional Retry-After header.

    Returns:
        int: seconds to wait before the single retry.
    """
    value = response.headers.get("retry-after")
    if value is None:
        return DEFAULT_RETRY_AFTER_SECONDS
    try:
        return int(value)
    except ValueError:
        return DEFAULT_RETRY_AFTER_SECONDS


def get(client: httpx.Client, url: str, params: dict[str, str] | None = None) -> httpx.Response:
    """Issue one GET, retrying exactly once on rate limit or maxlag.

    Args:
        client: shared httpx.Client.
        url: request URL.
        params: optional query parameters.

    Returns:
        httpx.Response: the final response, after at most one retry.
    """
    response = client.get(url, params=params)
    if needs_retry(response):
        time.sleep(retry_after_seconds(response))
        response = client.get(url, params=params)
    return response


def dump_json(data: Any, path: str) -> int:
    """Write JSON deterministically and as pure ASCII.

    Args:
        data: JSON-serializable object.
        path: destination file path.

    Returns:
        int: number of bytes written.
    """
    text = json.dumps(data, ensure_ascii=True, indent=1, sort_keys=True) + "\n"
    payload = text.encode("ascii")
    with open(path, "wb") as handle:
        handle.write(payload)
    return len(payload)


def record_resolve(client: httpx.Client, meta: dict[str, Any]) -> dict[str, Any]:
    """Record the stage 0 Action API resolve call.

    Args:
        client: shared httpx.Client.
        meta: META.json dict, updated in place with this fixture's entry.

    Returns:
        dict: the parsed resolve.json body.
    """
    params = {
        "action": "query",
        "titles": TITLE,
        "format": "json",
        "formatversion": "2",
        "redirects": "1",
        "prop": "info|pageprops|description|links|revisions",
        "pllimit": "10",
        "plnamespace": "0",
        "rvprop": "timestamp",
        "maxlag": "5",
    }
    response = get(client, ACTION_API, params=params)
    body = response.json()
    written_bytes = dump_json(body, "resolve.json")
    meta["fixtures"]["resolve.json"] = {
        "url": str(response.url),
        "status": response.status_code,
        "bytes": written_bytes,
    }
    return body


def extract_lastrevid(resolve_body: dict[str, Any]) -> int:
    """Pull lastrevid out of the resolve.json body.

    Args:
        resolve_body: parsed resolve.json content.

    Returns:
        int: the lastrevid of the resolved page.
    """
    page = resolve_body["query"]["pages"][0]
    return page["lastrevid"]


def trim_parsoid_html(html_text: str) -> str:
    """Trim Parsoid HTML to head, body attributes and the first sections.

    Keeps the document's <head> untouched, keeps the <body> tag's own
    attributes, and keeps only the first SECTIONS_TO_KEEP top-level
    <section data-mw-section-id> elements directly under <body>; every
    other direct child of <body> is dropped.

    Args:
        html_text: raw Parsoid HTML document.

    Returns:
        str: the trimmed HTML document.

    Raises:
        ValueError: if the document has no <body> element or does not serialise.
    """
    tree = LexborHTMLParser(html_text)
    body = tree.body
    if body is None:
        raise ValueError("parsoid response has no <body>")
    children = list(body.iter())
    sections = [
        child
        for child in children
        if child.tag == "section" and child.attributes.get("data-mw-section-id") is not None
    ]
    keep = sections[:SECTIONS_TO_KEEP]
    for child in children:
        if child not in keep:
            child.decompose()
    html = tree.html
    if html is None:
        raise ValueError("parsoid response did not serialise")
    return html


def record_parsoid(client: httpx.Client, meta: dict[str, Any], lastrevid: int) -> None:
    """Record the stage 2 Parsoid HTML fetch, trimmed to SECTIONS_TO_KEEP (all when None).

    Args:
        client: shared httpx.Client.
        meta: META.json dict, updated in place with this fixture's entry.
        lastrevid: revision id resolved in stage 0.
    """
    url = f"{PARSOID_REVISION_BASE}/{lastrevid}/html"
    response = get(client, url, params=None)
    content_revision_id = response.headers.get("content-revision-id")
    original_bytes = len(response.content)
    trimmed_html = trim_parsoid_html(response.text)
    ascii_bytes = trimmed_html.encode("ascii", "xmlcharrefreplace")
    with open("parsoid.html", "wb") as handle:
        handle.write(ascii_bytes)
    meta["fixtures"]["parsoid.html"] = {
        "url": str(response.url),
        "status": response.status_code,
        "bytes": len(ascii_bytes),
        "requested_rev_id": lastrevid,
        "content_revision_id": content_revision_id,
        "sections_kept": SECTIONS_TO_KEEP,
        "original_bytes": original_bytes,
    }


def record_revision(client: httpx.Client, meta: dict[str, Any], lastrevid: int) -> None:
    """Record the stage 2 revision-timestamp lookup for the pinned revision.

    Args:
        client: shared httpx.Client.
        meta: META.json dict, updated in place with this fixture's entry.
        lastrevid: revision id resolved in stage 0.
    """
    params = {
        "action": "query",
        "revids": str(lastrevid),
        "prop": "revisions",
        "rvprop": "timestamp",
        "format": "json",
        "formatversion": "2",
        "maxlag": "5",
    }
    response = get(client, ACTION_API, params=params)
    body = response.json()
    written_bytes = dump_json(body, "revision.json")
    meta["fixtures"]["revision.json"] = {
        "url": str(response.url),
        "status": response.status_code,
        "bytes": written_bytes,
    }


def record_morelike(client: httpx.Client, meta: dict[str, Any]) -> None:
    """Record the stage 4 "morelike" related-articles call.

    Args:
        client: shared httpx.Client.
        meta: META.json dict, updated in place with this fixture's entry.
    """
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": f"morelike:{TITLE}",
        "gsrlimit": "8",
        "gsrnamespace": "0",
        "prop": "extracts|info|revisions",
        "exintro": "1",
        "explaintext": "1",
        "exlimit": "8",
        "rvprop": "timestamp",
        "maxlag": "5",
        "format": "json",
        "formatversion": "2",
    }
    response = get(client, ACTION_API, params=params)
    body = response.json()
    written_bytes = dump_json(body, "morelike.json")
    meta["fixtures"]["morelike.json"] = {
        "url": str(response.url),
        "status": response.status_code,
        "bytes": written_bytes,
    }


def record_search(client: httpx.Client, meta: dict[str, Any]) -> None:
    """Record the topic search, as `WikimediaClient.search_with_suggestion` sends it.

    One `generator=search` call for TITLE: 8 results, the API's spelling
    suggestion, and each page's disambiguation flag.

    Args:
        client: shared httpx.Client.
        meta: META.json dict, updated in place with this fixture's entry.
    """
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": TITLE,
        "gsrlimit": "8",
        "gsrnamespace": "0",
        "gsrinfo": "suggestion",
        "prop": "pageprops",
        "ppprop": "disambiguation",
        "format": "json",
        "formatversion": "2",
        "maxlag": "5",
    }
    response = get(client, ACTION_API, params=params)
    body = response.json()
    written_bytes = dump_json(body, "search.json")
    meta["fixtures"]["search.json"] = {
        "url": str(response.url),
        "status": response.status_code,
        "bytes": written_bytes,
    }


def record_mostread(client: httpx.Client, meta: dict[str, Any]) -> None:
    """Record the Wikifeeds "mostread" object from the feed of the day before TODAY_UTC.

    The feed published for day D carries the most-read list of day D-1, so this
    list covers two days before TODAY_UTC, the same day as pageviews_top.json.

    Args:
        client: shared httpx.Client.
        meta: META.json dict, updated in place with this fixture's entry.
    """
    day = TODAY_UTC - datetime.timedelta(days=1)
    url = f"{WIKIFEEDS_FEATURED_BASE}/{day.year:04d}/{day.month:02d}/{day.day:02d}"
    response = get(client, url, params=None)
    body = response.json()
    mostread = body["mostread"]
    written_bytes = dump_json(mostread, "mostread.json")
    meta["fixtures"]["mostread.json"] = {
        "url": str(response.url),
        "status": response.status_code,
        "bytes": written_bytes,
        "date": day.isoformat(),
        "mostread_date": mostread.get("date"),
    }


def _pageviews_url(day: datetime.date) -> str:
    """Build the Pageviews top-articles URL for one UTC day.

    Args:
        day: the day whose top articles to fetch.

    Returns:
        str: the request URL.
    """
    return f"{PAGEVIEWS_TOP_BASE}/{day.year:04d}/{day.month:02d}/{day.day:02d}"


def record_pageviews_top(client: httpx.Client, meta: dict[str, Any]) -> None:
    """Record the Pageviews top-articles call for two days before TODAY_UTC.

    Steps back one more UTC day, at most MAX_PAGEVIEWS_BACKSTEPS times, while it 404s.

    Args:
        client: shared httpx.Client.
        meta: META.json dict, updated in place with this fixture's entry.
    """
    attempt_day = TODAY_UTC - datetime.timedelta(days=2)
    response = get(client, _pageviews_url(attempt_day))
    for _ in range(MAX_PAGEVIEWS_BACKSTEPS):
        if response.status_code != 404:
            break
        time.sleep(PACE_SECONDS)
        attempt_day -= datetime.timedelta(days=1)
        response = get(client, _pageviews_url(attempt_day))
    body = response.json()
    written_bytes = dump_json(body, "pageviews_top.json")
    meta["fixtures"]["pageviews_top.json"] = {
        "url": str(response.url),
        "status": response.status_code,
        "bytes": written_bytes,
        "date": attempt_day.isoformat(),
    }


def main() -> None:
    """Record all seven Wikimedia fixtures plus META.json."""
    meta = {
        "recorded_at": datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z"),
        "user_agent": USER_AGENT,
        "fixtures": {},
    }
    client = build_client()
    try:
        resolve_body = record_resolve(client, meta)
        time.sleep(PACE_SECONDS)

        lastrevid = extract_lastrevid(resolve_body)
        record_parsoid(client, meta, lastrevid)
        time.sleep(PACE_SECONDS)

        record_revision(client, meta, lastrevid)
        time.sleep(PACE_SECONDS)

        record_morelike(client, meta)
        time.sleep(PACE_SECONDS)

        record_search(client, meta)
        time.sleep(PACE_SECONDS)

        record_mostread(client, meta)
        time.sleep(PACE_SECONDS)

        record_pageviews_top(client, meta)
    finally:
        client.close()

    dump_json(meta, "META.json")


if __name__ == "__main__":
    main()
