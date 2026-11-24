"""The subsection-headings switch has a letter in the ETag, beside the lean one."""

from __future__ import annotations

import inspect

import pytest

from tests.support.apps import app_client
from tests.support.constants import FIXTURE_TITLE
from wke.api.routes.dossiers.body import dossier_body
from wke.api.routes.dossiers.params import view_etag
from wke.core.render import render_markdown

SWITCHES = [
    pytest.param((False, False, "-s0-l0-pd"), id="both-off-is-base"),
    pytest.param((True, False, "-s0-l0-pdl"), id="lean"),
    pytest.param((False, True, "-s0-l0-pdh"), id="headings"),
    pytest.param((True, True, "-s0-l0-pdlh"), id="lean-and-headings"),
]


@pytest.fixture
def switches(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> str:
    """Set LEAN_RESPONSE and SUBSECTION_HEADINGS before the app reads its settings."""
    lean, headings, tail = request.param
    monkeypatch.setenv("LEAN_RESPONSE", str(lean).lower())
    monkeypatch.setenv("SUBSECTION_HEADINGS", str(headings).lower())
    return tail


@pytest.mark.parametrize("switches", SWITCHES, indirect=True)
async def test_every_route_carries_the_letters_of_the_switches(switches, app, built_page) -> None:
    async with app_client(app) as client:
        json_reply = await client.get(f"/api/v1/dossiers/{built_page}")
        markdown = await client.get(f"/api/v1/dossiers/{built_page}.md")
        posted = await client.post("/api/v1/dossiers", json={"title": FIXTURE_TITLE})

    for reply in (json_reply, posted):
        assert reply.status_code == 200
        assert reply.headers["etag"].endswith(f'{switches}"')
    assert "-markdown-" in markdown.headers["etag"]
    assert markdown.headers["etag"].endswith(f'{switches}"')
    assert posted.headers["etag"] == json_reply.headers["etag"]


@pytest.mark.parametrize("switches", SWITCHES[2:], indirect=True)
async def test_a_tag_made_without_the_headings_letter_gets_a_fresh_body(
    switches, app, built_page
) -> None:
    async with app_client(app) as client:
        url = f"/api/v1/dossiers/{built_page}"
        tag = (await client.get(url)).headers["etag"]
        same = await client.get(url, headers={"If-None-Match": tag})
        stale = await client.get(url, headers={"If-None-Match": tag.replace('h"', '"')})

    assert same.status_code == 304
    assert stale.status_code == 200


def test_view_etag_takes_both_switches_as_required_arguments() -> None:
    parameters = inspect.signature(view_etag).parameters
    for name in ("lean", "subsection_headings"):
        assert parameters[name].default is inspect.Parameter.empty
        assert parameters[name].kind is inspect.Parameter.KEYWORD_ONLY


@pytest.mark.parametrize("function", [dossier_body, render_markdown, view_etag])
def test_lean_has_no_default_so_a_caller_that_forgets_it_fails(function) -> None:
    assert inspect.signature(function).parameters["lean"].default is inspect.Parameter.empty


def test_the_openapi_description_names_both_etag_letters() -> None:
    from pathlib import Path

    import yaml

    spec = yaml.safe_load((Path(__file__).parents[2] / "openapi.yaml").read_text())
    text = spec["paths"]["/api/v1/dossiers/{page_id}"]["get"]["description"]
    assert '"l" when LEAN_RESPONSE is on' in text
    assert '"h" when SUBSECTION_HEADINGS is on' in text
