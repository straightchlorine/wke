"""/llms.txt always renders, even cold.

A missing trending snapshot must omit the "Most read" section, not
answer the whole document with a 503.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock

from tests.support.apps import app_client
from tests.support.snapshots import make_snapshot
from wke.api.llmstxt import most_read_heading, render_llms_txt
from wke.core import keys
from wke.core.errors import ApiException
from wke.core.models import DossierState, TrendingSnapshot, TrendingTopic
from wke.core.viewcache import invalidate_views


def _topic(page_id: int, title: str, state: DossierState) -> TrendingTopic:
    return TrendingTopic(
        page_id=page_id,
        title=title,
        description="a test topic",
        rank=1,
        views=100,
        rev_id=1,
        dossier_state=state,
    )


async def test_llms_txt_cold_document() -> None:
    """With no trending snapshot the document still renders, with no Most read section.

    Links use the configured public scheme (http here), never a hardcoded https, so
    they agree with `links.self` built from the same PUBLIC_SCHEME and PUBLIC_HOST.
    """
    service = AsyncMock()
    service.base_url = "http://localhost:8010"
    service.get_trending.side_effect = ApiException(503, "upstream_unavailable")

    body = await render_llms_txt(service)

    assert "# Wikipedia Knowledge Explorer" in body
    assert (
        "> Cited context from Wikipedia, for people and for LLMs. Every passage is cited "
        "to an exact revision; every summary is labelled as model output."
    ) in body.splitlines()
    assert "## Most read" not in body
    assert "http://localhost:8010/openapi.json" in body
    assert "https://localhost:8010" not in body
    assert "## Optional" in body
    assert "- For machines: http://localhost:8010/machines" in body
    assert "- Source repository: https://github.com/straightchlorine/wke" in body
    assert "codeberg" not in body.lower()
    assert "/docs/decisions" not in body
    assert "/about" not in body


async def test_llms_txt_lists_only_ready_topics() -> None:
    service = AsyncMock()
    service.base_url = "https://ready.example.test"
    service.get_trending.return_value = TrendingSnapshot(
        date=date(2026, 9, 27),
        source="wikifeeds_mostread",
        generated_at=datetime.now(UTC),
        topics=[
            _topic(1, "Ready Topic", "ready"),
            _topic(2, "Building Topic", "building"),
        ],
        edges=[],
    )

    body = await render_llms_txt(service)

    assert "Ready Topic" in body
    assert "Building Topic" not in body


async def test_llms_txt_explains_how_to_get_any_topic() -> None:
    service = AsyncMock()
    service.base_url = "http://localhost:8010"
    service.get_trending.side_effect = ApiException(503, "upstream_unavailable")

    body = await render_llms_txt(service)

    for expected in (
        "GET http://localhost:8010/api/v1/search?q={title}",
        "POST http://localhost:8010/api/v1/dossiers",
        "/api/v1/jobs/{job_id}",
        "/api/v1/dossiers/{page_id}.md?budget=8000",
        "summaries=false",
        "2000, 8000, 32000",
        "http://localhost:8010/mcp",
        "`search_topics(query, limit=8)`",
        '`get_dossier(title, budget=8000, format="markdown", parts="dossier")`',
        "parts=dossier,metadata",
        "parts=dossier,metadata,sources",
        '"schema_version": "2"',
        "counts the dossier part only",
        "the exact section URL of its `[cN]` marker",
        "`get_trending(limit=10)`",
        "## Citations",
    ):
        assert expected in body
    assert body.index("## Get a dossier for any topic") < body.index("## Optional")


async def test_llms_txt_lists_the_trending_set_not_every_dossier(app, built_page) -> None:
    invalidate_views()
    async with app_client(app) as client:
        response = await client.get("/llms.txt")

    assert response.status_code == 200
    assert "## Other dossiers" not in response.text
    assert f"/api/v1/dossiers/{built_page}.md" not in response.text


async def test_llms_txt_etag_follows_the_trending_set(app, built_page, fake_redis) -> None:
    snapshot = make_snapshot(page_id=built_page)
    await fake_redis.set(keys.TRENDING_LATEST, json.dumps(snapshot))
    async with app_client(app) as client:
        before = await client.get("/llms.txt")
        await fake_redis.delete(keys.TRENDING_LATEST)
        invalidate_views()
        after = await client.get("/llms.txt", headers={"If-None-Match": before.headers["etag"]})

    assert "## Most read" in before.text
    assert after.status_code == 200
    assert after.headers["etag"] != before.headers["etag"]


def test_most_read_heading_says_yesterday_only_when_true() -> None:
    now = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)
    assert (
        most_read_heading("2026-09-28", now) == "Most read on Wikipedia yesterday (2026-09-28 UTC)"
    )
    assert most_read_heading("2026-09-27", now) == "Most read on Wikipedia on 2026-09-27 (UTC)"
    assert most_read_heading(date(2026, 9, 28), now).startswith("Most read on Wikipedia yesterday")
