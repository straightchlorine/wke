"""TABLE_REPACK: the ETag letter, and one chosen pack behind every format."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from mcp import Client

from tests.factories.repack import make_repack_dossier
from tests.support.apps import app_client
from tests.support.mcp import payload_of
from tests.support.services import make_service, seed_dossier
from wke.api.etag import etag_is_lean
from wke.api.mcp_server import build_mcp_server
from wke.core import render
from wke.core.citations import seed_pin
from wke.core.render.parts import DEFAULT_PARTS

DOSSIER = make_repack_dossier("table", 4)
PAGE_ID = DOSSIER.topic.page_id


@pytest.fixture
def table_repack(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> str:
    """Set TABLE_REPACK from the param before the app is built; return the tag's tail."""
    on, tail = request.param
    monkeypatch.setenv("TABLE_REPACK", str(on).lower())
    return tail


@pytest.mark.parametrize(
    "table_repack",
    [pytest.param((True, "lht"), id="on"), pytest.param((False, "lh"), id="off")],
    indirect=True,
)
@pytest.mark.parametrize("budget", [2000, 8000, 32000])
async def test_the_tag_ends_in_t_when_the_setting_is_on_at_every_budget(
    table_repack, budget, app, built_page
) -> None:
    async with app_client(app) as client:
        reply = await client.get(f"/api/v1/dossiers/{built_page}", params={"budget": budget})

    assert reply.status_code == 200
    assert reply.headers["etag"].endswith(f'-pd{table_repack}"')


@pytest.mark.parametrize("table_repack", [(True, "lht")], indirect=True)
async def test_a_tag_made_without_the_letter_gets_a_fresh_body(
    table_repack, app, built_page
) -> None:
    async with app_client(app) as client:
        url = f"/api/v1/dossiers/{built_page}"
        tag = (await client.get(url)).headers["etag"]
        same = await client.get(url, headers={"If-None-Match": tag})
        stale = await client.get(url, headers={"If-None-Match": tag.replace('t"', '"')})

    assert same.status_code == 304
    assert stale.status_code == 200
    assert stale.headers["etag"] == tag


@pytest.mark.parametrize("table_repack", [(True, "lht")], indirect=True)
async def test_the_ready_post_carries_the_same_tag_as_the_get(
    table_repack, app, built_page
) -> None:
    from tests.support.constants import FIXTURE_TITLE

    async with app_client(app) as client:
        fetched = await client.get(f"/api/v1/dossiers/{built_page}")
        posted = await client.post("/api/v1/dossiers", json={"title": FIXTURE_TITLE})

    assert posted.headers["etag"] == fetched.headers["etag"]
    assert posted.headers["etag"].endswith('-pdlht"')


@pytest.mark.parametrize(
    ("tag", "lean"),
    [
        ('"1-pv-2000-json-complete-0-s0-l0-pdlht"', True),
        ('"1-pv-2000-json-complete-0-s0-l0-pdht"', False),
    ],
)
def test_the_letter_after_the_headings_one_does_not_hide_the_lean_letter(
    tag: str, lean: bool
) -> None:
    assert etag_is_lean(tag) is lean
    assert etag_is_lean(tag[:-2] + '-r1"') is lean


async def test_json_markdown_and_the_mcp_tool_show_the_same_chunks(redis_client) -> None:
    await seed_dossier(redis_client, DOSSIER)
    service = make_service(redis_client, table_repack=True)
    plain = make_service(redis_client, table_repack=False)

    view = await service.get_dossier_view(PAGE_ID, 2000, "json", False)
    markdown = await service.get_dossier_view(PAGE_ID, 2000, "markdown", False)
    unchanged = await plain.get_dossier_view(PAGE_ID, 2000, "json", False)
    assert [c.id for c in view.chunks] != [c.id for c in unchanged.chunks]
    assert "T:table0" in [c.id for c in view.chunks]
    assert markdown == render.render_markdown(view, False, False, DEFAULT_PARTS, lean=True)
    assert "| 2003 |" in markdown

    service.resolve_and_admit = AsyncMock(  # type: ignore[method-assign]
        return_value=(PAGE_ID, seed_pin(DOSSIER).rev_id, "ready")
    )
    async with Client(build_mcp_server(service)) as client:
        as_markdown = await client.call_tool("get_dossier", {"title": "t", "budget": 2000})
        as_json = await client.call_tool(
            "get_dossier", {"title": "t", "budget": 2000, "format": "json"}
        )
    assert payload_of(as_markdown)["content"] == markdown
    chunks = payload_of(as_json)["dossier"]["chunks"]
    assert [c["id"] for c in chunks] == [c.id for c in view.chunks]


async def test_the_setting_off_serves_the_plain_pack(redis_client) -> None:
    await seed_dossier(redis_client, DOSSIER)
    service = make_service(redis_client, table_repack=False)

    view = await service.get_dossier_view(PAGE_ID, 2000, "json", False)
    plain = render.build_view(DOSSIER, 2000, view.freshness, view.links, lean=True)

    assert service.table_repack is False
    assert view.model_dump_json() == plain.model_dump_json()
