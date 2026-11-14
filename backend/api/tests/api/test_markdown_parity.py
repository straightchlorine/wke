"""The REST Markdown routes and the MCP get_dossier tool serve identical bytes."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from mcp import Client

from tests.support.apps import app_client
from tests.support.constants import FIXTURE_TITLE
from tests.support.mcp import payload_of
from wke.api.mcp_server import build_mcp_server
from wke.core.models.budgets import BUDGETS


async def _mcp_markdown(app, page_id: int, budget: int, **args: object) -> str:
    service = app.state.service
    service.request_build = AsyncMock(return_value="ready")
    service.resolve_and_admit = AsyncMock(return_value=(page_id, 0, "ready"))
    async with Client(build_mcp_server(service)) as client:
        result = await client.call_tool(
            "get_dossier", {"title": FIXTURE_TITLE, "budget": budget, **args}
        )
    return payload_of(result)["content"]


@pytest.mark.parametrize("budget", sorted(BUDGETS))
@pytest.mark.parametrize("links", [False, True])
async def test_mcp_and_rest_markdown_are_byte_identical(app, built_page, budget, links) -> None:
    flag = "true" if links else "false"
    async with app_client(app) as client:
        rest = await client.get(f"/api/v1/dossiers/{built_page}.md?budget={budget}&links={flag}")
    mcp = await _mcp_markdown(app, built_page, budget, links=links)

    assert rest.status_code == 200
    assert rest.content == mcp.encode("utf-8")


@pytest.mark.parametrize(
    "parts", ["dossier", "dossier,metadata", "dossier,sources", "dossier,metadata,sources"]
)
async def test_mcp_and_rest_markdown_are_byte_identical_per_parts(app, built_page, parts) -> None:
    async with app_client(app) as client:
        rest = await client.get(f"/api/v1/dossiers/{built_page}.md?budget=2000&parts={parts}")
    mcp = await _mcp_markdown(app, built_page, 2000, parts=parts)

    assert rest.status_code == 200
    assert rest.content == mcp.encode("utf-8")


async def test_default_markdown_has_no_inline_links_in_either_channel(app, built_page) -> None:
    async with app_client(app) as client:
        rest = await client.get(f"/api/v1/dossiers/{built_page}.md?budget=2000")
    mcp = await _mcp_markdown(app, built_page, 2000)

    assert "inline links are not counted" not in rest.text
    assert mcp == rest.text


async def test_markdown_etag_is_the_same_on_both_rest_routes(app, built_page) -> None:
    async with app_client(app) as client:
        dotted = await client.get(f"/api/v1/dossiers/{built_page}.md?budget=2000")
        negotiated = await client.get(f"/api/v1/dossiers/{built_page}?budget=2000&format=md")

    assert dotted.headers["etag"] == negotiated.headers["etag"]
    assert dotted.content == negotiated.content
