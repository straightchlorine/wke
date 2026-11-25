"""The ETag ends in "l" for LEAN_RESPONSE and "h" for SUBSECTION_HEADINGS when each is on."""

from __future__ import annotations

import pytest

from tests.support.apps import app_client
from tests.support.constants import FIXTURE_TITLE

SWITCHES = [
    pytest.param((False, False, "-s0-l0-pd"), id="both-off-is-plain"),
    pytest.param((True, False, "-s0-l0-pdl"), id="lean"),
    pytest.param((False, True, "-s0-l0-pdh"), id="headings"),
    pytest.param((True, True, "-s0-l0-pdlh"), id="lean-and-headings"),
]


@pytest.fixture
def switches(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> str:
    """Set LEAN_RESPONSE and SUBSECTION_HEADINGS from the param before the app is built."""
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
