"""GET /api/v1/search and POST suggestion and disambiguation handling."""

from __future__ import annotations

from collections.abc import Callable
from operator import itemgetter
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from tests.support.apps import app_client, make_app
from tests.support.constants import DISAMBIGUATION_TITLE, FIXTURE_TITLE


@pytest.fixture
def app(fake_redis, settings, wm_fixtures, ml_client_ok) -> FastAPI:
    def handle(request: httpx.Request) -> httpx.Response:
        if dict(request.url.params).get("generator") == "search":
            return httpx.Response(200, json=wm_fixtures.json("search.json"))
        return httpx.Response(404)

    wm_http = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    return make_app(
        fake_redis, settings, wikimedia_http=wm_http, ml_http=ml_client_ok._http, start_worker=True
    )


async def test_search_returns_candidates(app: FastAPI, wm_fixtures) -> None:
    async with app_client(app) as client:
        response = await client.get("/api/v1/search", params={"q": FIXTURE_TITLE})

    assert response.status_code == 200
    body = response.json()
    assert body["query"] == FIXTURE_TITLE
    pages = sorted(wm_fixtures.json("search.json")["query"]["pages"], key=itemgetter("index"))
    assert [(r["page_id"], r["title"]) for r in body["results"]] == [
        (page["pageid"], page["title"])
        for page in pages
        if "disambiguation" not in page.get("pageprops", {})
    ]
    assert all(result["dossier_state"] == "none" for result in body["results"])


@pytest.mark.parametrize(("limit", "status"), [(1, 200), (10, 200), (0, 422), (11, 422), (20, 422)])
async def test_search_limit_is_between_one_and_ten(app: FastAPI, limit: int, status: int) -> None:
    async with app_client(app) as client:
        response = await client.get("/api/v1/search", params={"q": FIXTURE_TITLE, "limit": limit})

    assert response.status_code == status
    if status == 422:
        assert response.json()["code"] == "validation_error"


def _search_body(titles: list[str], suggestion: str | None = None) -> dict[str, Any]:
    query: dict[str, Any] = {
        "pages": [
            {"ns": 0, "pageid": 100 + i, "title": t, "index": i + 1} for i, t in enumerate(titles)
        ]
    }
    if suggestion is not None:
        query["searchinfo"] = {"totalhits": len(titles), "suggestion": suggestion}
    return {"batchcomplete": True, "query": query}


Handler = Callable[[dict[str, str]], httpx.Response]


def _make_app(
    fake_redis, settings, ml_client_ok, handler: Handler
) -> tuple[FastAPI, list[dict[str, str]]]:
    calls: list[dict[str, str]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        calls.append(params)
        return handler(params)

    app = make_app(
        fake_redis,
        settings,
        wikimedia_http=httpx.AsyncClient(transport=httpx.MockTransport(handle)),
        ml_http=ml_client_ok._http,
    )
    return app, calls


async def test_typo_gets_a_nearby_title_from_the_fuzzy_search(
    fake_redis, settings, ml_client_ok
) -> None:
    """Plain search for "Grace Hoper" finds nothing close; the fuzzy call does."""

    def handler(params: dict[str, str]) -> httpx.Response:
        if params["gsrsearch"] == "Grace~ Hoper~":
            return httpx.Response(200, json=_search_body(["Grace Hopper", "Grace Hoops"]))
        return httpx.Response(
            200, json=_search_body(["Mckenna Grace", "Hope Gap", "Chloe Grace Moretz"])
        )

    app, calls = _make_app(fake_redis, settings, ml_client_ok, handler)
    async with app_client(app) as client:
        response = await client.get("/api/v1/search", params={"q": "Grace Hoper"})

    assert response.status_code == 200
    assert response.json()["did_you_mean"] == "Grace Hopper"
    assert len(calls) == 2
    assert all(call["gsrinfo"] == "suggestion" for call in calls)


async def test_api_suggestion_is_mapped_to_a_real_title_in_one_call(
    fake_redis, settings, ml_client_ok
) -> None:
    def handler(params: dict[str, str]) -> httpx.Response:
        return httpx.Response(
            200, json=_search_body(["Grace Hopper", "Hopper (microarchitecture)"], "grace hopper")
        )

    app, calls = _make_app(fake_redis, settings, ml_client_ok, handler)
    async with app_client(app) as client:
        response = await client.get("/api/v1/search", params={"q": "Grase Hopper"})

    assert response.json()["did_you_mean"] == "Grace Hopper"
    assert len(calls) == 1


async def test_exact_and_partial_queries_get_no_suggestion_and_one_call(
    fake_redis, settings, ml_client_ok, wm_fixtures
) -> None:
    def handler(params: dict[str, str]) -> httpx.Response:
        body = wm_fixtures.json("search.json")
        if params["gsrsearch"] != FIXTURE_TITLE:
            # A recorded suggestion, if any, belongs to the exact-title query only.
            body["query"].pop("searchinfo", None)
        return httpx.Response(200, json=body)

    app, calls = _make_app(fake_redis, settings, ml_client_ok, handler)
    async with app_client(app) as client:
        exact = await client.get("/api/v1/search", params={"q": FIXTURE_TITLE})
        partial = await client.get("/api/v1/search", params={"q": FIXTURE_TITLE[:3]})

    assert exact.json()["did_you_mean"] is None
    assert partial.json()["did_you_mean"] is None
    assert len(calls) == 2


async def test_disambiguation_candidates_exclude_the_queried_title(
    fake_redis, settings, ml_client_ok
) -> None:
    def handler(params: dict[str, str]) -> httpx.Response:
        if params.get("generator") == "search":
            return httpx.Response(
                200,
                json=_search_body([DISAMBIGUATION_TITLE, "Mercury (planet)", "Mercury (element)"]),
            )
        page = {
            "pageid": 999,
            "ns": 0,
            "title": DISAMBIGUATION_TITLE,
            "lastrevid": 1,
            "pageprops": {"disambiguation": ""},
        }
        return httpx.Response(200, json={"query": {"pages": [page]}})

    app, _calls = _make_app(fake_redis, settings, ml_client_ok, handler)
    async with app_client(app) as client:
        response = await client.post("/api/v1/dossiers", json={"title": DISAMBIGUATION_TITLE})

    assert response.status_code == 409
    titles = [c["title"] for c in response.json()["candidates"]]
    assert titles == ["Mercury (planet)", "Mercury (element)"]


async def test_disambiguation_pages_are_not_offered_and_suggestion_is_kept(
    fake_redis, settings, ml_client_ok, wm_fixtures
) -> None:
    body = wm_fixtures.synthetic("search_generator.json")

    def handler(_params: dict[str, str]) -> httpx.Response:
        return httpx.Response(200, json=body)

    app, calls = _make_app(fake_redis, settings, ml_client_ok, handler)
    async with app_client(app) as client:
        response = await client.get("/api/v1/search", params={"q": "Lord"})

    assert response.status_code == 200
    titles = [c["title"] for c in response.json()["results"]]
    assert titles == ["Lord", "Lord Howe Island", "Lord Byron"]
    assert len(calls) == 1
    assert calls[0]["prop"] == "pageprops"
    assert calls[0]["ppprop"] == "disambiguation"
