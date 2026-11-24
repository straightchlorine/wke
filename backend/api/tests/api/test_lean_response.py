"""The lean response: no Key facts block, and left-out lines only with metadata."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from mcp import Client

from tests.factories.dossier import make_fixture_dossier
from tests.support.apps import app_client
from tests.support.constants import PIPELINE_VERSION
from tests.support.services import make_service, seed_dossier
from wke.api.app import create_app
from wke.api.mcp_server import build_mcp_server
from wke.core import keys, render
from wke.core.citations import seed_pin
from wke.core.errors import ApiException
from wke.core.models import Dossier
from wke.core.render.parts import ALL_PARTS, DEFAULT_PARTS, Part, parse_parts
from wke.services.dossiers import DossierService
from wke.settings import Settings

FACTS_LABEL = "**Key facts**"
NOTICE = "_1 table of this section is left out at this budget._"
FULL = "dossier,metadata,sources"


def _with_heavy_table(dossier: Dossier) -> Dossier:
    """Add a table too big for 2000 tokens to section s3."""
    heavy = dossier.chunks[-1].model_copy(
        update={
            "text": "x" * 8100,
            "est_tokens": 2025,
            "kind": "table",
            "id": f"{dossier.chunks[-1].id}:legacy:table0",
        }
    )
    sections = [
        s.model_copy(update={"chunk_ids": [*s.chunk_ids, heavy.id]}) if s.id == "s3" else s
        for s in dossier.sections
    ]
    return dossier.model_copy(update={"sections": sections, "chunks": [*dossier.chunks, heavy]})


DOSSIER = _with_heavy_table(make_fixture_dossier())
PAGE_ID = DOSSIER.topic.page_id


@pytest.fixture
def legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set LEAN_RESPONSE=false before the app reads its settings."""
    monkeypatch.setenv("LEAN_RESPONSE", "false")


async def _get(client, path: str, **params: str):
    return await client.get(
        f"/api/v1/dossiers/{PAGE_ID}{path}", params={"budget": "2000", **params}
    )


def test_the_setting_is_on_by_default_and_reads_the_environment(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    assert settings.lean_response is True
    monkeypatch.setenv("LEAN_RESPONSE", "false")
    assert Settings.model_validate({}).lean_response is False


@pytest.mark.parametrize("path", [".md", ""])
async def test_the_default_response_has_no_facts_and_no_left_out_line(
    app, redis_client, path
) -> None:
    await seed_dossier(redis_client, DOSSIER)
    async with app_client(app) as client:
        reply = await _get(client, path, **({} if path else {"format": "md"}))

    assert reply.status_code == 200
    assert FACTS_LABEL not in reply.text
    assert "Born:" not in reply.text
    assert "of this section" not in reply.text


async def test_the_default_json_has_no_facts_chunk_and_the_left_out_data(app, redis_client) -> None:
    await seed_dossier(redis_client, DOSSIER)
    async with app_client(app) as client:
        body = (await _get(client, "", parts="dossier,metadata")).json()

    chunks = body["dossier"]["chunks"]
    assert "facts" not in {chunk["kind"] for chunk in chunks}
    assert any(
        cid.endswith(":legacy:table0")
        for s in body["dossier"]["sections"]
        for cid in s["chunk_ids"]
    )
    assert not any(c["id"].endswith(":legacy:table0") for c in chunks)
    assert body["metadata"]["budget"]["omitted_chunks"] >= 1


@pytest.mark.parametrize("selection", ["dossier", "dossier,metadata", "dossier,sources", FULL])
async def test_no_selection_brings_the_key_facts_back(app, redis_client, selection) -> None:
    await seed_dossier(redis_client, DOSSIER)
    async with app_client(app) as client:
        markdown = await _get(client, ".md", parts=selection)
        body = (await _get(client, "", parts=selection)).json()

    assert FACTS_LABEL not in markdown.text and "Born:" not in markdown.text
    assert "facts" not in {c["kind"] for c in body["dossier"]["chunks"]}
    listed = [cid for s in body["dossier"]["sections"] for cid in s["chunk_ids"]]
    assert not any(cid.endswith(":facts") for cid in listed)
    if "metadata" in body:
        assert not any(
            cid.endswith(":facts") for cid in body["metadata"]["budget"]["included_chunk_ids"]
        )


@pytest.mark.parametrize("raw", ["dossier,facts", "facts", "facts,dossier,metadata"])
async def test_facts_is_not_a_part(app, redis_client, raw) -> None:
    await seed_dossier(redis_client, DOSSIER)
    async with app_client(app) as client:
        reply = await _get(client, "", parts=raw)

    assert reply.status_code == 422
    assert "use dossier, metadata, sources" in reply.json()["detail"]
    assert "facts" not in reply.json()["detail"].split(";")[1]


async def test_reading_a_dossier_leaves_the_stored_facts_chunk_alone(app, redis_client) -> None:
    await seed_dossier(redis_client, DOSSIER)
    async with app_client(app) as client:
        await _get(client, "", parts=FULL)
    stored = Dossier.model_validate_json(
        await redis_client.get(keys.dossier(PAGE_ID, seed_pin(DOSSIER).rev_id, PIPELINE_VERSION))
    )

    assert stored == DOSSIER
    assert any(c.kind == "facts" for c in stored.chunks)


async def test_metadata_carries_the_left_out_line(app, redis_client) -> None:
    await seed_dossier(redis_client, DOSSIER)
    async with app_client(app) as client:
        reply = await _get(client, ".md", parts="dossier,metadata")

    assert NOTICE in reply.text
    assert FACTS_LABEL not in reply.text


async def test_the_setting_off_serves_the_base_response(legacy, app, redis_client) -> None:
    await seed_dossier(redis_client, DOSSIER)
    async with app_client(app) as client:
        reply = await _get(client, ".md")
        json_reply = await _get(client, "")
        service = app.state.service
        view = await service.get_dossier_view(PAGE_ID, 2000, "json", False, parts=DEFAULT_PARTS)

    assert service.lean_response is False
    assert reply.text == render.render_markdown(view, False, False, DEFAULT_PARTS, lean=False)
    assert FACTS_LABEL in reply.text and NOTICE in reply.text
    assert any(c["kind"] == "facts" for c in json_reply.json()["dossier"]["chunks"])
    assert reply.headers["etag"].endswith('-pdh"')  # lean off: no "l"; headings on by default: "h"


async def test_the_lean_etag_never_equals_the_base_one(app, redis_client) -> None:
    await seed_dossier(redis_client, DOSSIER)
    async with app_client(app) as client:
        reply = await _get(client, "")

    assert reply.headers["etag"].endswith('-pdlh"')


@pytest.mark.parametrize("parts", [DEFAULT_PARTS, frozenset({"dossier", "metadata"}), ALL_PARTS])
@pytest.mark.parametrize("budget", [2000, 8000])
async def test_the_service_with_the_setting_off_renders_as_the_base_code(
    redis_client, parts: frozenset[Part], budget
) -> None:
    await seed_dossier(redis_client, DOSSIER)
    service = make_service(redis_client, lean_response=False)

    markdown = await service.get_dossier_view(PAGE_ID, budget, "markdown", True, parts=parts)
    view = await service.get_dossier_view(PAGE_ID, budget, "json", True, parts=parts)
    base = render.build_view(DOSSIER, budget, view.freshness, view.links, include_summaries=True)

    assert markdown == render.render_markdown(base, True, False, parts, lean=False)
    assert view.model_dump_json() == base.model_dump_json()


def test_parse_parts_names_the_valid_parts_for_facts() -> None:
    with pytest.raises(ApiException) as caught:
        parse_parts("dossier,facts")
    assert caught.value.status_code == 422
    assert caught.value.detail == "unknown part 'facts'; use dossier, metadata, sources"


async def test_the_tool_and_route_descriptions_name_every_part() -> None:
    server = build_mcp_server(AsyncMock(spec=DossierService))
    async with Client(server) as client:
        tools = {t.name: t.description or "" for t in (await client.list_tools()).tools}
    for line in ("dossier (the default)", "metadata adds", "sources adds"):
        assert line in tools["get_dossier"]

    parameters = create_app().openapi()["paths"]["/api/v1/dossiers/{page_id}"]["get"]["parameters"]
    text = next(p["description"] for p in parameters if p["name"] == "parts")
    lines = text.splitlines()
    for part in ("dossier (default)", "metadata:", "sources:"):
        assert sum(line.startswith(part) for line in lines) == 1
