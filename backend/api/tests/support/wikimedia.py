"""Recorded Wikimedia fixtures and the mock transport that serves them."""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable, Coroutine
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
from wke.clients.redis import RedisClient
from wke.clients.user_agent import build_user_agent
from wke.clients.wikimedia import WikimediaClient

SyncHandler = Callable[[httpx.Request], httpx.Response]
AsyncHandler = Callable[[httpx.Request], Coroutine[None, None, httpx.Response]]
# What httpx.MockTransport accepts: a plain or an async handler.
Handler = SyncHandler | AsyncHandler


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


def wikimedia_handler(wm_fixtures: WmFixtures) -> SyncHandler:
    """Build a MockTransport handler over the recorded article fixtures.

    Besides FIXTURE_TITLE it resolves MISSING_TITLE as missing, DISAMBIGUATION_TITLE
    as a disambiguation page and NEW_TITLE as an article with no dossier yet
    (resolve only; its revision has no recorded HTML).

    Args:
        wm_fixtures: the recorded fixtures to serve.

    Returns:
        SyncHandler: maps a request to its recorded response, 404 when unmatched.
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
            return httpx.Response(200, json=wm_fixtures.json("search.json"))

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


class FakeClock:
    """A clock that stands still until a test advances it."""

    def __init__(self, start: float = 0.0) -> None:
        self.value = start

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        """Move the clock forward.

        Args:
            seconds: how far to move it.
        """
        self.value += seconds


def make_wikimedia_client(
    redis_client: RedisClient,
    handler: Handler,
    *,
    clock: Callable[[], float] = time.monotonic,
    wall_clock: Callable[[], float] = time.time,
    sleep: Callable[[float], Awaitable[None]] = no_sleep,
    budget_per_minute: int = 150,
) -> WikimediaClient:
    """Build a WikimediaClient over a mock transport, sending the real User-Agent.

    Args:
        redis_client: the RedisClient holding the request budget and caches.
        handler: the MockTransport handler that answers every request.
        clock: the monotonic clock for lock deadlines and pacing.
        wall_clock: the wall clock that picks the budget minute.
        sleep: the client's sleep; skipped by default, pass `asyncio.sleep`
            where concurrent callers must take turns.
        budget_per_minute: the shared per-minute call budget.

    Returns:
        WikimediaClient: pointed at the REQUIRED_ENV Action API and REST URLs.
    """
    http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), headers={"User-Agent": build_user_agent()}
    )
    return WikimediaClient(
        http,
        redis_client,
        REQUIRED_ENV["WIKIPEDIA_API_URL"],
        REQUIRED_ENV["WIKIPEDIA_REST_URL"],
        budget_per_minute=budget_per_minute,
        clock=clock,
        wall_clock=wall_clock,
        sleep=sleep,
    )
