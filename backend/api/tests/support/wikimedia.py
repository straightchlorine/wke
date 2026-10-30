"""Recorded Wikimedia fixtures and the mock transport that serves them."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from tests.support.constants import (
    DISAMBIGUATION_TITLE,
    FIXTURE_TITLE,
    MISSING_TITLE,
    NEW_TITLE,
    NEW_TITLE_PAGE_ID,
    NEW_TITLE_REV_ID,
    REQUIRED_ENV,
)
from wke.clients.wikimedia import WikimediaClient

Handler = Callable[[httpx.Request], httpx.Response]


class WmFixtures:
    """Loads recorded Wikimedia fixtures from tests/fixtures/wm/."""

    def __init__(self, directory: Path) -> None:
        self._dir = directory
        with (directory / "META.json").open(encoding="utf-8") as handle:
            self.meta = json.load(handle)

    def json(self, name: str) -> Any:
        """Load a recorded JSON fixture by file name."""
        with (self._dir / name).open(encoding="utf-8") as handle:
            return json.load(handle)

    def search_json(self) -> Any:
        """Recorded search.json reshaped as a `generator=search` response."""
        recorded = self.json("search.json")["query"]
        entries = recorded["search"]
        pages = [
            {"pageid": e["pageid"], "ns": e["ns"], "title": e["title"], "index": i + 1}
            for i, e in enumerate(entries)
        ]
        query: dict[str, Any] = {"pages": pages}
        if "searchinfo" in recorded:
            query["searchinfo"] = recorded["searchinfo"]
        return {"batchcomplete": True, "query": query}

    def synthetic(self, name: str) -> Any:
        """Load a hand-written fixture from tests/fixtures/synthetic/."""
        with (self._dir.parent / "synthetic" / name).open(encoding="utf-8") as handle:
            return json.load(handle)

    def text(self, name: str) -> str:
        """Load a recorded text fixture by file name."""
        return (self._dir / name).read_text(encoding="utf-8")

    @property
    def revision_id(self) -> int:
        """The revision the recorded Parsoid HTML was fetched at."""
        return self.meta["fixtures"]["parsoid.html"]["requested_rev_id"]


async def no_sleep(_seconds: float) -> None:
    """Stand-in for asyncio.sleep so budget waits cost no time."""
    return None


def wikimedia_handler(wm_fixtures: WmFixtures) -> Handler:
    """Build a MockTransport handler over the recorded article fixtures.

    Besides FIXTURE_TITLE it resolves MISSING_TITLE as missing, DISAMBIGUATION_TITLE
    as a disambiguation page and NEW_TITLE as an article with no dossier yet
    (resolve only; its revision has no recorded HTML).

    Args:
        wm_fixtures: the recorded fixtures to serve.

    Returns:
        Handler: maps a request to its recorded response, 404 when unmatched.
    """

    def handle(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/html") and "/revision/" in path:
            return httpx.Response(
                200,
                text=wm_fixtures.text("parsoid.html"),
                headers={"content-revision-id": str(wm_fixtures.revision_id)},
            )
        params = dict(request.url.params)
        if params.get("generator") == "search":
            if params.get("gsrsearch", "").startswith("morelike:"):
                return httpx.Response(200, json=wm_fixtures.json("morelike.json"))

            # The disambiguation candidate path (DossierService.search),
            # same generator=search call as GET /api/v1/search.
            return httpx.Response(200, json=wm_fixtures.search_json())

        if params.get("action") == "query" and "revids" in params:
            return httpx.Response(200, json=wm_fixtures.json("revision.json"))
        if params.get("action") == "query" and "titles" in params:
            title = params["titles"]
            if title == FIXTURE_TITLE:
                return httpx.Response(200, json=wm_fixtures.json("resolve.json"))
            if title == MISSING_TITLE:
                body = {"query": {"pages": [{"ns": 0, "title": title, "missing": True}]}}
                return httpx.Response(200, json=body)
            if title == DISAMBIGUATION_TITLE:
                body = {
                    "query": {
                        "pages": [
                            {
                                "pageid": 999,
                                "ns": 0,
                                "title": title,
                                "lastrevid": 1,
                                "pageprops": {"disambiguation": ""},
                                "links": [
                                    {"ns": 0, "title": "Mercury (planet)"},
                                    {"ns": 0, "title": "Mercury (element)"},
                                ],
                            }
                        ]
                    }
                }
                return httpx.Response(200, json=body)
            if title == NEW_TITLE:
                body = {
                    "query": {
                        "pages": [
                            {
                                "pageid": NEW_TITLE_PAGE_ID,
                                "ns": 0,
                                "title": title,
                                "lastrevid": NEW_TITLE_REV_ID,
                                "pageprops": {},
                                "links": [],
                            }
                        ]
                    }
                }
                return httpx.Response(200, json=body)
        return httpx.Response(404)

    return handle


def make_wikimedia_client(redis_client, handler: Handler) -> WikimediaClient:
    """Build a WikimediaClient over a mock transport, with sleeps skipped.

    Args:
        redis_client: the RedisClient holding the request budget and caches.
        handler: the MockTransport handler that answers every request.

    Returns:
        WikimediaClient: pointed at the REQUIRED_ENV Action API and REST URLs.
    """
    return WikimediaClient(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        redis_client,
        REQUIRED_ENV["WIKIPEDIA_API_URL"],
        REQUIRED_ENV["WIKIPEDIA_REST_URL"],
        budget_per_minute=150,
        sleep=no_sleep,
    )
