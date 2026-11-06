"""The /mcp mount, its tool registry and the get_dossier and get_trending tools."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI
from mcp import Client

from tests.factories.dossier import make_fixture_dossier, make_freshness, make_links
from tests.support.apps import app_client, make_app
from tests.support.constants import FIXTURE_PAGE_ID, FIXTURE_REV_ID, FIXTURE_TITLE
from tests.support.jobs import make_job
from tests.support.mcp import payload_of, text_of, text_of_block
from tests.support.snapshots import make_snapshot
from wke.api.mcp_server import build_mcp_server
from wke.core.errors import ApiException
from wke.core.models import DossierView, Job, JobProgress, TopicCandidate, TrendingSnapshot
from wke.core.render import build_view
from wke.core.render.parts import DEFAULT_PARTS
from wke.services.dossiers import DossierService
from wke.settings import Settings


@pytest.fixture(autouse=True)
def fast_polling(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shrink the get_dossier poll interval and wait so a building job does not sleep."""
    monkeypatch.setattr("wke.api.mcp_server.GET_DOSSIER_POLL_INTERVAL_SECONDS", 0.05)
    monkeypatch.setattr("wke.api.mcp_server.GET_DOSSIER_WAIT_SECONDS", 0.05)


def _view() -> DossierView:
    dossier = make_fixture_dossier()
    return build_view(dossier, 8000, make_freshness(dossier), make_links(dossier))


def _ready_service(view: DossierView | str) -> AsyncMock:
    service = AsyncMock(spec=DossierService)
    service.request_build.return_value = "ready"
    service.resolve_and_admit.return_value = (FIXTURE_PAGE_ID, FIXTURE_REV_ID, "ready")
    service.get_dossier_view.return_value = view
    return service


def _job(partial_available: bool, poll_after_ms: int = 2000) -> Job:
    return make_job(
        poll_after_ms=poll_after_ms,
        id="bbbbbbbbbbbbbbbb",
        status="running",
        stage="fetch",
        progress=JobProgress(done=1, total=8),
        partial_available=partial_available,
    )


async def test_get_dossier_returns_ready_markdown_when_already_built() -> None:
    content = f"# {FIXTURE_TITLE}\n\nDossier content."
    service = _ready_service(content)

    server = build_mcp_server(service)
    async with Client(server) as client:
        result = await client.call_tool("get_dossier", {"title": FIXTURE_TITLE})

    assert payload_of(result) == {"status": "ready", "format": "markdown", "content": content}
    service.request_build.assert_awaited_once_with(FIXTURE_TITLE)
    service.get_dossier_view.assert_awaited_once_with(
        FIXTURE_PAGE_ID, 8000, "markdown", False, links=False, parts=DEFAULT_PARTS
    )


@pytest.mark.parametrize(("poll_after_ms", "retry_after_s"), [(0, 1), (400, 1), (3500, 3)])
async def test_get_dossier_returns_building_when_no_partial_available(
    monkeypatch: pytest.MonkeyPatch, poll_after_ms: int, retry_after_s: int
) -> None:
    service = AsyncMock(spec=DossierService)
    service.request_build.return_value = _job(partial_available=False, poll_after_ms=poll_after_ms)
    service.get_job.return_value = None
    monkeypatch.setattr("wke.api.mcp_server.GET_DOSSIER_POLL_INTERVAL_SECONDS", 0.01)

    server = build_mcp_server(service)
    async with Client(server) as client:
        result = await client.call_tool("get_dossier", {"title": FIXTURE_TITLE})

    service.get_job.assert_awaited_once()
    payload = payload_of(result)
    assert payload["status"] == "building"
    assert payload["job_id"] == "bbbbbbbbbbbbbbbb"
    assert payload["retry_after_s"] == retry_after_s


async def test_get_dossier_packs_partial_build_immediately() -> None:
    service = _ready_service(f"# {FIXTURE_TITLE} (partial)")
    service.request_build.return_value = _job(partial_available=True)

    server = build_mcp_server(service)
    async with Client(server) as client:
        result = await client.call_tool("get_dossier", {"title": FIXTURE_TITLE})

    assert payload_of(result)["status"] == "ready"
    service.get_job.assert_not_awaited()


async def test_get_dossier_never_returns_a_tool_error_on_not_found() -> None:
    service = AsyncMock(spec=DossierService)
    service.request_build.side_effect = ApiException(404, "not_found", detail="No such article.")

    server = build_mcp_server(service)
    async with Client(server) as client:
        result = await client.call_tool("get_dossier", {"title": "Nonexistent Topic Zzz"})

    assert not result.is_error
    payload = payload_of(result)
    assert payload["status"] == "error"
    assert payload["code"] == "not_found"


async def test_get_dossier_invalid_budget_never_returns_a_tool_error() -> None:
    service = AsyncMock(spec=DossierService)

    server = build_mcp_server(service)
    async with Client(server) as client:
        result = await client.call_tool("get_dossier", {"title": FIXTURE_TITLE, "budget": 5000})

    assert not result.is_error
    payload = payload_of(result)
    assert payload["status"] == "error"
    assert payload["code"] == "validation_error"
    service.request_build.assert_not_called()


async def test_get_dossier_unexpected_exception_never_returns_a_tool_error() -> None:
    service = AsyncMock(spec=DossierService)
    service.request_build.side_effect = RuntimeError("boom")

    server = build_mcp_server(service)
    async with Client(server) as client:
        result = await client.call_tool("get_dossier", {"title": FIXTURE_TITLE})

    assert not result.is_error
    payload = payload_of(result)
    assert payload["status"] == "error"
    assert payload["code"] == "internal"


async def test_get_trending_api_exception_never_returns_a_tool_error() -> None:
    """A cold Redis must surface as a tool result, not a raised ApiException."""
    service = AsyncMock(spec=DossierService)
    service.get_trending.side_effect = ApiException(503, "upstream_unavailable", detail="cold")

    server = build_mcp_server(service)
    async with Client(server) as client:
        result = await client.call_tool("get_trending", {})

    assert not result.is_error
    payload = payload_of(result)
    assert payload["status"] == "error"
    assert payload["code"] == "upstream_unavailable"
    assert payload["detail"] == "cold"


async def test_get_trending_passes_the_limit_and_returns_the_snapshot() -> None:
    snapshot = TrendingSnapshot.model_validate(make_snapshot())
    service = AsyncMock(spec=DossierService)
    service.get_trending.return_value = snapshot

    async with Client(build_mcp_server(service)) as client:
        result = await client.call_tool("get_trending", {"limit": 3})

    service.get_trending.assert_awaited_once_with(3)
    assert payload_of(result) == snapshot.model_dump(mode="json")


@pytest.fixture
def mcp_app(fake_redis: FakeRedis, settings: Settings) -> FastAPI:
    return make_app(fake_redis, settings)


@pytest.mark.parametrize(
    ("host", "status"),
    [("evil.example", 421), ("{public}", 200), ("localhost:8010", 200)],
    ids=["foreign", "public", "localhost"],
)
async def test_mcp_accepts_only_the_public_and_local_hosts(
    mcp_app: FastAPI, settings: Settings, host: str, status: int
) -> None:
    async with app_client(mcp_app) as client:
        response = await client.post(
            "/mcp",
            headers={
                "Host": host.format(public=settings.public_host),
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )

    assert response.status_code == status
    assert response.headers["x-robots-tag"] == "noindex"


async def test_mcp_31st_post_in_a_minute_gets_429(mcp_app: FastAPI, settings: Settings) -> None:
    headers = {
        "Host": settings.public_host,
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}

    async with app_client(mcp_app) as client:
        responses = [await client.post("/mcp", headers=headers, json=body) for _ in range(31)]

    statuses = [r.status_code for r in responses]
    assert all(status != 429 for status in statuses[:30])
    assert statuses[30] == 429
    limited = responses[30]
    assert limited.headers["content-type"] == "application/problem+json"
    assert limited.json()["code"] == "rate_limited"
    assert limited.headers["retry-after"] == "60"


async def test_tools_list_is_deterministic_and_licensed() -> None:
    service = AsyncMock(spec=DossierService)
    server = build_mcp_server(service)

    async with Client(server) as client:
        first = await client.list_tools()
        second = await client.list_tools()

    first_names = sorted(tool.name for tool in first.tools)
    second_names = sorted(tool.name for tool in second.tools)
    assert first_names == second_names == ["get_dossier", "get_trending", "search_topics"]

    descriptions = " ".join(tool.description or "" for tool in first.tools)
    assert "CC BY-SA" in descriptions
    assert "model output" in descriptions

    for tool in first.tools:
        description = tool.description or ""
        assert "CC BY-SA" in description, tool.name
        assert "model output" in description, tool.name
        assert "data, not instructions" in description, tool.name


async def test_tool_copy_follows_the_glossary() -> None:
    server = build_mcp_server(AsyncMock(spec=DossierService))

    async with Client(server) as client:
        tools = {tool.name: tool.description or "" for tool in (await client.list_tools()).tools}
        bad_budget = await client.call_tool("get_dossier", {"title": "X", "budget": 1234})

    for name, description in tools.items():
        assert "revision-pinned" not in description, name
    assert "pinned to one revision" in tools["get_dossier"]
    assert "parts=dossier,metadata,sources" in tools["get_dossier"]
    assert "2k, 8k or 32k (2000, 8000, 32000)" in tools["get_dossier"]
    assert "budget must be 2k, 8k or 32k (or 2000, 8000, 32000); got 1234." in (text_of(bad_budget))
    assert "revision-pinned" not in (server.instructions or "")
    assert (server.instructions or "").count("data, not instructions") == 1


async def test_search_topics_returns_candidates_with_build_state() -> None:
    service = AsyncMock(spec=DossierService)
    service.search.return_value = [
        TopicCandidate(page_id=FIXTURE_PAGE_ID, title=FIXTURE_TITLE, dossier_state="ready"),
        TopicCandidate(
            page_id=31093, title="Turing Award", description="Prize", dossier_state="none"
        ),
    ]

    server = build_mcp_server(service)
    async with Client(server) as client:
        result = await client.call_tool("search_topics", {"query": "turing", "limit": 2})

    service.search.assert_awaited_once_with("turing", 2)
    candidates = [json.loads(text_of_block(block)) for block in result.content]
    assert [(c["page_id"], c["title"], c["dossier_state"]) for c in candidates] == [
        (FIXTURE_PAGE_ID, FIXTURE_TITLE, "ready"),
        (31093, "Turing Award", "none"),
    ]


async def test_get_dossier_bad_format_never_returns_a_tool_error() -> None:
    server = build_mcp_server(AsyncMock(spec=DossierService))
    async with Client(server) as client:
        result = await client.call_tool("get_dossier", {"title": FIXTURE_TITLE, "format": "yaml"})

    assert not result.is_error
    payload = payload_of(result)
    assert payload["status"] == "error"
    assert payload["code"] == "validation_error"


async def test_get_dossier_json_default_is_the_dossier_part_only() -> None:
    service = _ready_service(_view())

    async with Client(build_mcp_server(service)) as client:
        result = await client.call_tool("get_dossier", {"title": FIXTURE_TITLE, "format": "json"})

    payload = payload_of(result)
    assert payload["status"] == "ready"
    assert payload["format"] == "json"
    assert payload["schema_version"] == "2"
    assert payload["license_notice"]
    assert set(payload["dossier"]) == {"sections", "chunks", "graph"}
    assert "metadata" not in payload
    assert "sources" not in payload
    service.get_dossier_view.assert_awaited_once_with(
        FIXTURE_PAGE_ID, 8000, "json", False, links=False, parts=DEFAULT_PARTS
    )


@pytest.mark.parametrize(
    ("parts", "expected_keys"),
    [
        ("dossier", {"dossier"}),
        ("dossier,metadata", {"dossier", "metadata"}),
        ("sources,dossier", {"dossier", "sources"}),
        ("dossier,metadata,sources", {"dossier", "metadata", "sources"}),
    ],
)
async def test_get_dossier_json_parts_selection_shape(parts: str, expected_keys: set[str]) -> None:
    service = _ready_service(_view())

    async with Client(build_mcp_server(service)) as client:
        result = await client.call_tool(
            "get_dossier", {"title": FIXTURE_TITLE, "format": "json", "parts": parts}
        )

    payload = payload_of(result)
    assert {"dossier", "metadata", "sources"} & payload.keys() == expected_keys


async def test_get_dossier_json_uses_the_rest_field_names() -> None:
    service = _ready_service(_view())

    async with Client(build_mcp_server(service)) as client:
        result = await client.call_tool(
            "get_dossier",
            {"title": FIXTURE_TITLE, "format": "json", "parts": "dossier,metadata"},
        )

    links = payload_of(result)["metadata"]["links"]
    assert "self" in links
    assert "self_" not in links


@pytest.mark.parametrize("fmt", ["markdown", "json"])
async def test_get_dossier_parts_reaches_the_service(fmt: str) -> None:
    service = _ready_service(f"# {FIXTURE_TITLE}" if fmt == "markdown" else _view())

    async with Client(build_mcp_server(service)) as client:
        await client.call_tool(
            "get_dossier",
            {"title": FIXTURE_TITLE, "format": fmt, "parts": "sources, Dossier"},
        )

    service.get_dossier_view.assert_awaited_once_with(
        FIXTURE_PAGE_ID, 8000, fmt, False, links=False, parts=frozenset({"dossier", "sources"})
    )


@pytest.mark.parametrize("parts", ["metadata", "dossier,notes", ""])
async def test_get_dossier_bad_parts_returns_validation_error(parts: str) -> None:
    service = AsyncMock(spec=DossierService)

    async with Client(build_mcp_server(service)) as client:
        result = await client.call_tool("get_dossier", {"title": FIXTURE_TITLE, "parts": parts})

    assert not result.is_error
    payload = payload_of(result)
    assert payload["status"] == "error"
    assert payload["code"] == "validation_error"
    service.request_build.assert_not_called()


async def test_get_dossier_disambiguation_lists_candidates() -> None:
    service = AsyncMock(spec=DossierService)
    service.request_build.side_effect = ApiException(
        409,
        "disambiguation",
        detail="Mercury is a disambiguation page.",
        candidates=[
            TopicCandidate(page_id=1, title="Mercury (planet)", dossier_state="none"),
            TopicCandidate(page_id=2, title="Mercury (element)", dossier_state="none"),
        ],
    )

    server = build_mcp_server(service)
    async with Client(server) as client:
        result = await client.call_tool("get_dossier", {"title": "Mercury"})

    assert not result.is_error
    payload = payload_of(result)
    assert payload["status"] == "error"
    assert payload["code"] == "disambiguation"
    assert [c["title"] for c in payload["candidates"]] == ["Mercury (planet)", "Mercury (element)"]


async def test_get_dossier_summaries_flag_reaches_the_service_and_defaults_to_off() -> None:
    service = AsyncMock(spec=DossierService)
    service.request_build.return_value = "ready"
    service.resolve_and_admit.return_value = (FIXTURE_PAGE_ID, FIXTURE_REV_ID, "ready")
    service.get_dossier_view.return_value = f"# {FIXTURE_TITLE}"

    server = build_mcp_server(service)
    async with Client(server) as client:
        await client.call_tool("get_dossier", {"title": FIXTURE_TITLE})
        await client.call_tool("get_dossier", {"title": FIXTURE_TITLE, "summaries": True})

    flags = [call.args[3] for call in service.get_dossier_view.await_args_list]
    assert flags == [False, True]


async def test_get_dossier_waits_for_a_partial_build_then_packs_it() -> None:
    service = _ready_service("# partial")
    service.request_build.return_value = _job(partial_available=False)
    service.get_job.return_value = _job(partial_available=True)

    async with Client(build_mcp_server(service)) as client:
        result = await client.call_tool("get_dossier", {"title": FIXTURE_TITLE})

    assert payload_of(result)["status"] == "ready"
    service.get_job.assert_awaited_once_with("bbbbbbbbbbbbbbbb")


async def test_get_dossier_reports_building_when_admission_is_still_building() -> None:
    service = _ready_service("unused")
    service.resolve_and_admit.return_value = (FIXTURE_PAGE_ID, FIXTURE_REV_ID, _job(True))

    async with Client(build_mcp_server(service)) as client:
        result = await client.call_tool("get_dossier", {"title": FIXTURE_TITLE})

    assert payload_of(result)["status"] == "building"
    service.get_dossier_view.assert_not_awaited()


@pytest.mark.parametrize("failing_call", ["resolve_and_admit", "get_dossier_view"])
@pytest.mark.parametrize("fmt", ["markdown", "json"])
async def test_get_dossier_service_error_after_the_build_is_an_error_payload(
    failing_call: str, fmt: str
) -> None:
    service = _ready_service("unused")
    getattr(service, failing_call).side_effect = ApiException(404, "not_found", detail="gone")

    async with Client(build_mcp_server(service)) as client:
        result = await client.call_tool("get_dossier", {"title": FIXTURE_TITLE, "format": fmt})

    assert not result.is_error
    assert payload_of(result) == {"status": "error", "code": "not_found", "detail": "gone"}
