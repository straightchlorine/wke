"""wke.api.etag unit tests, and conditional GET on every route that serves an ETag."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI

from tests.support.apps import app_client
from tests.support.constants import FIXTURE_REV_ID
from tests.support.http import assert_conditional_get
from tests.support.snapshots import make_snapshot
from wke.api import etag
from wke.core import keys

_BASE: dict[str, Any] = {
    "rev_id": 1200000,
    "pipeline_version": "test-pv",
    "budget": 8000,
    "fmt": "json",
}


def test_etag_format() -> None:
    assert etag.compute_etag(**_BASE) == '"1200000-test-pv-8000-json-complete-0-s0-l0-pd"'
    full = etag.compute_etag(
        1200000,
        "test-pv",
        8000,
        "markdown",
        build_state="partial",
        summaries_done=3,
        summaries=True,
        links=True,
        parts_code="pdms",
    )
    assert full == '"1200000-test-pv-8000-markdown-partial-3-s1-l1-pdms"'


@pytest.mark.parametrize(
    "change",
    [
        {"rev_id": 1200001},
        {"pipeline_version": "other-pv"},
        {"budget": 2000},
        {"fmt": "markdown"},
        {"build_state": "partial"},
        {"summaries_done": 1},
        {"summaries": True},
        {"links": True},
        {"parts_code": "pds"},
    ],
    ids=lambda change: next(iter(change)),
)
def test_every_input_changes_the_etag(change: dict[str, Any]) -> None:
    assert etag.compute_etag(**{**_BASE, **change}) != etag.compute_etag(**_BASE)


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        pytest.param('"v1"', True, id="exact"),
        pytest.param("*", True, id="wildcard"),
        pytest.param('"other", "v1"', True, id="in-list"),
        pytest.param('  "other" ,"v1" ', True, id="list-with-padding"),
        pytest.param('"stale"', False, id="miss"),
        pytest.param('"v1-extra"', False, id="prefix-is-not-a-match"),
        pytest.param("", False, id="empty"),
        pytest.param(None, False, id="absent"),
    ],
)
def test_if_none_match(header: str | None, expected: bool) -> None:
    assert etag.is_not_modified('"v1"', header) is expected


def test_cache_control_latest_vs_revision() -> None:
    assert etag.cache_control_for("latest") == "public, max-age=60"
    assert etag.cache_control_for("revision") == "public, max-age=31536000, immutable"


def test_body_etag_is_a_quoted_hash_of_the_encoded_body() -> None:
    value = etag.body_etag("body", "utf-8")

    assert value.startswith('"') and value.endswith('"')
    assert len(value) == 34
    assert value == etag.body_etag("body", "utf-8")
    assert value != etag.body_etag("body ", "utf-8")
    assert etag.body_etag("caf\u00e9", "utf-8") != etag.body_etag("caf\u00e9", "latin-1")


_LATEST = "public, max-age=60"
_IMMUTABLE = "public, max-age=31536000, immutable"


@pytest.mark.parametrize(
    ("url", "cache_control", "variant"),
    [
        pytest.param("/api/v1/dossiers/{page}", _LATEST, None, id="dossier"),
        pytest.param("/api/v1/dossiers/{page}.md", _LATEST, "?budget=2k", id="markdown"),
        pytest.param(
            f"/api/v1/dossiers/{{page}}/rev/{FIXTURE_REV_ID}",
            _IMMUTABLE,
            "?format=md",
            id="revision",
        ),
        pytest.param(
            "/api/v1/dossiers/{page}?parts=dossier,sources", _LATEST, "&budget=2k", id="parts"
        ),
        pytest.param("/api/v1/dossiers", "public, max-age=10", "?q=nonexistent+xyz", id="list"),
        pytest.param("/api/v1/trending", _LATEST, None, id="trending"),
        pytest.param("/llms.txt", "public, max-age=300", None, id="llms"),
        pytest.param("/sitemap.xml", "public, max-age=300", None, id="sitemap"),
    ],
)
async def test_conditional_get_is_304(
    app: FastAPI,
    built_page: int,
    fake_redis: FakeRedis,
    url: str,
    cache_control: str,
    variant: str | None,
) -> None:
    await fake_redis.set(keys.TRENDING_LATEST, json.dumps(make_snapshot()))
    url = url.format(page=built_page)

    async with app_client(app) as client:
        first = await assert_conditional_get(client, url, cache_control)
        if variant is not None:
            other = await client.get(url + variant)
            assert other.headers["etag"] != first.headers["etag"]


async def test_md_route_etag_differs_from_json_route(app: FastAPI, built_page: int) -> None:
    async with app_client(app) as client:
        as_json = await client.get(f"/api/v1/dossiers/{built_page}", params={"budget": "8000"})
        as_md = await client.get(f"/api/v1/dossiers/{built_page}.md", params={"budget": "8000"})

    assert as_json.headers["etag"] != as_md.headers["etag"]
