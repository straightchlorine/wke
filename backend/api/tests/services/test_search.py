"""Title matching and the did-you-mean rule, and the dossier state of each search result."""

from __future__ import annotations

import json

import pytest

from tests.factories.dossier import make_fixture_dossier
from tests.support.services import make_service, renamed, seed_dossier
from wke.clients.redis import RedisClient
from wke.core import keys
from wke.services.search import did_you_mean, title_covers_query


@pytest.mark.parametrize(
    ("query", "title", "covers"),
    [
        ("Grace Ho", "Grace Hopper", True),
        ("Grace Hoper", "Grace Hopper", False),
        ("hopper grace", "Grace Hopper", True),
        ("grace_hopper", "Grace Hopper", True),
    ],
)
def test_title_covers_query(query: str, title: str, covers: bool) -> None:
    assert title_covers_query(query, title) is covers


@pytest.mark.parametrize(
    ("query", "titles", "api_suggestion", "expected"),
    [
        ("grace_hopper", ["Grace Hopper"], None, None),
        ("Grace Hopper", ["Grace Hopper"], "Gracie Hopper", None),
        ("Grace Hoper", ["Grace Hopper", "Hopper"], None, "Grace Hopper"),
        ("grace ho", ["Grace Hopper"], None, None),
        ("Grace Hopper (computer)", ["Grace Hopper"], None, None),
        ("Gracee Hopper", ["Grace Hopper"], "grace hopper", "Grace Hopper"),
        ("Grac Hoppr", ["Hopper"], "Grace Hopper", "Grace Hopper"),
        ("Grace Hopper", ["Hopper"], "grace  hopper", None),
        ("Grace Hoper", [], "Grace Hoper", None),
        ("Grace Hopper", ["Hopper", ""], None, None),
    ],
    ids=[
        "result-is-the-query",
        "result-is-the-query-despite-api-suggestion",
        "close-spelling",
        "query-cut-short",
        "far-from-any-title",
        "api-suggestion-maps-to-a-title",
        "api-suggestion-as-given",
        "suggestion-equals-query",
        "suggestion-equals-query-no-titles",
        "blank-title-ignored",
    ],
)
def test_did_you_mean(
    query: str, titles: list[str], api_suggestion: str | None, expected: str | None
) -> None:
    assert did_you_mean(query, titles, api_suggestion) == expected


async def test_search_reports_each_result_dossier_state(redis_client: RedisClient) -> None:
    service = make_service(redis_client)
    ready = make_fixture_dossier()
    partial = renamed(
        ready.model_copy(update={"build": ready.build.model_copy(update={"state": "partial"})}),
        2,
        "Partial",
    )
    other_version = renamed(ready, 3, "Other version")
    await seed_dossier(redis_client, ready)
    await seed_dossier(redis_client, partial)
    await seed_dossier(redis_client, other_version, pipeline_version="older-pv")
    await redis_client.set(keys.ptr(4), "null")
    await redis_client.set(keys.ptr(5), json.dumps({"rev_id": 1}))
    await redis_client.set(keys.dossier(5, 1, "test-pv"), "[]")
    entries = [
        {"pageid": ready.topic.page_id, "title": "Ready"},
        {"pageid": 2, "title": "Partial"},
        {"pageid": 3, "title": "Other version"},
        {"pageid": 4, "title": "Null pointer"},
        {"pageid": 5, "title": "Unreadable dossier"},
        {"pageid": 6, "title": "Never built"},
        {"title": "No page id"},
    ]
    await redis_client.set(
        keys.wm_search("grace", 10), json.dumps({"results": entries, "suggestion": None})
    )

    candidates = await service.search("grace", limit=99)

    assert [(c.title, c.dossier_state) for c in candidates] == [
        ("Ready", "ready"),
        ("Partial", "partial"),
        ("Other version", "none"),
        ("Null pointer", "none"),
        ("Unreadable dossier", "none"),
        ("Never built", "none"),
    ]


async def test_search_with_suggestion_skips_the_fuzzy_call_when_a_result_covers_the_query(
    redis_client: RedisClient,
) -> None:
    service = make_service(redis_client)
    await redis_client.set(
        keys.wm_search("grace ho", 8),
        json.dumps({"results": [{"pageid": 9, "title": "Grace Hopper"}], "suggestion": None}),
    )

    candidates, suggestion = await service.search_with_suggestion("grace ho")

    assert [c.title for c in candidates] == ["Grace Hopper"]
    assert suggestion is None
