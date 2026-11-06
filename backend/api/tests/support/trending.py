"""Stand-ins for the trending tests: featured feed, Pageviews, TextExtracts and wke-ml."""

from __future__ import annotations

import json
import zlib
from collections.abc import Callable
from typing import Any

import httpx

from tests.support.wikimedia import SyncHandler, WmFixtures

FeedAnswer = Callable[[httpx.Request], httpx.Response]


def feed_article(wm_fixtures: WmFixtures, index: int = 0, **overrides: Any) -> dict[str, Any]:
    """Copy one article of the recorded most-read list, with fields replaced.

    Args:
        wm_fixtures: loader for the recorded fixtures.
        index: position in the recorded list.
        **overrides: fields to replace; a None value makes the field missing
            for the parser, which reads absent and null alike.

    Returns:
        dict[str, Any]: the article entry as the featured feed carries it.
    """
    return {**wm_fixtures.json("mostread.json")["articles"][index], **overrides}


def feed_answer(wm_fixtures: WmFixtures, **mostread_overrides: Any) -> FeedAnswer:
    """Answer the featured feed with the recorded most-read object, fields replaced.

    Args:
        wm_fixtures: loader for the recorded fixtures.
        **mostread_overrides: fields of the `mostread` object to replace, for
            example `articles` or `date`.

    Returns:
        FeedAnswer: a handler returning HTTP 200 with the feed body.
    """

    def answer(_request: httpx.Request) -> httpx.Response:
        mostread = {**wm_fixtures.json("mostread.json"), **mostread_overrides}
        return httpx.Response(200, json={"tfa": {}, "mostread": mostread, "news": []})

    return answer


def trending_handler(
    wm_fixtures: WmFixtures,
    feed: FeedAnswer | None = None,
    missing_titles: frozenset[str] = frozenset(),
) -> SyncHandler:
    """Route the Wikimedia calls of a trending run to canned answers.

    Pageviews top serves the recorded list. TextExtracts invents a page id
    and revision from each title (stable across calls) except for
    `missing_titles`, which it reports as missing. Any other request fails.

    Args:
        wm_fixtures: loader for the recorded fixtures.
        feed: answer for the featured feed; defaults to the recorded list.
        missing_titles: titles, space separated, the Action API reports missing.

    Returns:
        SyncHandler: the MockTransport handler.
    """
    feed = feed or feed_answer(wm_fixtures)

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "feed/featured" in url:
            return feed(request)
        if "metrics/pageviews/top" in url:
            return httpx.Response(200, json=wm_fixtures.json("pageviews_top.json"))
        if "/w/api.php" in url:
            pages: list[dict[str, Any]] = []
            for raw in request.url.params.get("titles", "").split("|"):
                title = raw.replace("_", " ")
                if title in missing_titles:
                    pages.append({"title": title, "missing": True})
                    continue
                page_id = 1000 + zlib.crc32(title.encode()) % 1_000_000
                pages.append(
                    {
                        "pageid": page_id,
                        "title": title,
                        "lastrevid": page_id + 1,
                        "description": "a test topic",
                        "extract": f"Extract for {title}.",
                    }
                )
            return httpx.Response(200, json={"query": {"pages": pages}})
        raise AssertionError(f"unexpected request: {url}")

    return handler


def logged(handler: SyncHandler, log: list[str]) -> SyncHandler:
    """Wrap a handler so every request URL is appended to a list.

    Args:
        handler: the MockTransport handler to wrap.
        log: receives the URL of each request, in order.

    Returns:
        SyncHandler: the wrapping handler.
    """

    def wrapped(request: httpx.Request) -> httpx.Response:
        log.append(str(request.url))
        return handler(request)

    return wrapped


def analyze_edge_handler(payloads: list[dict[str, Any]] | None = None) -> SyncHandler:
    """A wke-ml /v1/analyze stub returning one edge, seed to the first related lead.

    Args:
        payloads: receives the decoded JSON body of each request.

    Returns:
        SyncHandler: the MockTransport handler.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        if payloads is not None:
            payloads.append(payload)
        related = payload.get("related_leads", [])
        edges = (
            [{"source": payload["page_id"], "target": related[0]["page_id"], "weight": 0.5}]
            if related
            else []
        )
        return httpx.Response(
            200,
            json={
                "model": "stub",
                "model_revision": "0",
                "relevance": {},
                "cluster_ids": {},
                "representatives": [],
                "edges": edges,
                "infer_seconds": 0.01,
            },
        )

    return handler
