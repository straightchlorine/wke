"""The `parts` selection on every route that returns a dossier: shape, ETag, headers, budget."""

from __future__ import annotations

import json

import pytest

from tests.support.apps import app_client
from tests.support.constants import FIXTURE_REV_ID, FIXTURE_TITLE
from wke.core.render.markdown import SOURCES_HEADING, render_markdown
from wke.core.render.parts import parse_parts
from wke.core.text.tokens import est_tokens
from wke.jobs.build.constants import LICENSE_NOTICE

SELECTIONS = ["dossier", "dossier,metadata", "dossier,sources", "dossier,metadata,sources"]
FULL = "dossier,metadata,sources"

_JSON_ROUTES = [
    pytest.param("/api/v1/dossiers/{page}", {}, id="main"),
    pytest.param(f"/api/v1/dossiers/{{page}}/rev/{FIXTURE_REV_ID}", {}, id="rev"),
]
_MARKDOWN_ROUTES = [
    pytest.param("/api/v1/dossiers/{page}.md", {}, id="md-route"),
    pytest.param("/api/v1/dossiers/{page}", {"format": "md"}, id="main-format-md"),
    pytest.param(
        f"/api/v1/dossiers/{{page}}/rev/{FIXTURE_REV_ID}", {"format": "md"}, id="rev-format-md"
    ),
]
_ALL_ROUTES = [*_JSON_ROUTES, *_MARKDOWN_ROUTES]


def _content_with_markers(full_with_sources: str) -> str:
    """Cut the dossier part, markers included, out of a render that has a Sources block."""
    head = full_with_sources[: full_with_sources.index(f"\n{SOURCES_HEADING}")]
    return head.rstrip("\n") + "\n"


@pytest.mark.parametrize("selection", SELECTIONS)
@pytest.mark.parametrize(("url", "params"), _JSON_ROUTES)
async def test_json_has_exactly_the_selected_parts(app, built_page, url, params, selection) -> None:
    async with app_client(app) as client:
        response = await client.get(
            url.format(page=built_page), params={**params, "parts": selection}
        )

    body = response.json()
    selected = set(selection.split(","))
    assert response.status_code == 200
    assert body["schema_version"] == "2"
    assert body["license_notice"] == LICENSE_NOTICE
    assert set(body) == {"schema_version", "license_notice", "dossier"} | selected - {"dossier"}
    assert set(body["dossier"]) == {"sections", "chunks", "graph"}
    assert all(chunk["citation_id"] for chunk in body["dossier"]["chunks"])
    if "metadata" in selected:
        assert set(body["metadata"]) == {"id", "topic", "build", "freshness", "budget", "links"}
        assert "self" in body["metadata"]["links"]
        assert "self_" not in body["metadata"]["links"]
    if "sources" in selected:
        assert body["sources"]


@pytest.mark.parametrize("selection", SELECTIONS)
@pytest.mark.parametrize(("url", "params"), _MARKDOWN_ROUTES)
async def test_markdown_routes_return_what_the_renderer_writes_for_the_selection(
    app, built_page, url, params, selection
) -> None:
    parts = parse_parts(selection)
    rev_id = FIXTURE_REV_ID if "/rev/" in url else None
    async with app_client(app) as client:
        response = await client.get(
            url.format(page=built_page), params={**params, "parts": selection}
        )
        view = await app.state.service.get_dossier_view(
            built_page, 8000, "json", False, rev_id=rev_id, parts=parts
        )

    assert response.status_code == 200
    assert response.text == render_markdown(view, False, False, parts)


@pytest.mark.parametrize(
    "raw", ["metadata", "sources", "metadata,sources", "bogus", "", "dossier,"]
)
@pytest.mark.parametrize(
    "url",
    [
        "/api/v1/dossiers/{page}",
        "/api/v1/dossiers/{page}.md",
        f"/api/v1/dossiers/{{page}}/rev/{FIXTURE_REV_ID}",
    ],
    ids=["main", "md-route", "rev"],
)
async def test_invalid_parts_are_422(app, built_page, url, raw) -> None:
    async with app_client(app) as client:
        response = await client.get(url.format(page=built_page), params={"parts": raw})

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


async def test_post_rejects_invalid_parts_before_admitting(app, built_page) -> None:
    async with app_client(app) as client:
        response = await client.post(
            "/api/v1/dossiers", params={"parts": "metadata"}, json={"title": FIXTURE_TITLE}
        )

    assert response.status_code == 422
    assert "parts must include dossier" in response.json()["detail"]


@pytest.mark.parametrize(("url", "params"), _ALL_ROUTES)
async def test_default_equals_explicit_dossier(app, built_page, url, params) -> None:
    async with app_client(app) as client:
        default = await client.get(url.format(page=built_page), params=params)
        explicit = await client.get(
            url.format(page=built_page), params={**params, "parts": "dossier"}
        )

    assert default.content == explicit.content
    assert default.headers["etag"] == explicit.headers["etag"]


@pytest.mark.parametrize(("url", "params"), _ALL_ROUTES)
async def test_order_and_duplicates_do_not_change_body_or_etag(
    app, built_page, url, params
) -> None:
    async with app_client(app) as client:
        plain = await client.get(url.format(page=built_page), params={**params, "parts": FULL})
        shuffled = await client.get(
            url.format(page=built_page),
            params={**params, "parts": "sources, Metadata,dossier,sources"},
        )

    assert plain.content == shuffled.content
    assert plain.headers["etag"] == shuffled.headers["etag"]


async def test_etag_differs_for_every_selection(app, built_page) -> None:
    async with app_client(app) as client:
        etags = {
            selection: (
                await client.get(f"/api/v1/dossiers/{built_page}", params={"parts": selection})
            ).headers["etag"]
            for selection in SELECTIONS
        }

    assert len(set(etags.values())) == len(SELECTIONS)


@pytest.mark.parametrize("budget", ["2000", "8000"])
async def test_selection_never_changes_the_passages(app, built_page, budget) -> None:
    async with app_client(app) as client:
        dossiers = [
            (
                await client.get(
                    f"/api/v1/dossiers/{built_page}", params={"parts": selection, "budget": budget}
                )
            ).json()["dossier"]
            for selection in SELECTIONS
        ]

    assert all(dossier == dossiers[0] for dossier in dossiers)


@pytest.mark.parametrize("budget", ["2000", "8000"])
@pytest.mark.parametrize(("url", "params"), _ALL_ROUTES)
async def test_used_est_tokens_is_the_content_with_markers(
    app, built_page, url, params, budget
) -> None:
    target = url.format(page=built_page)
    async with app_client(app) as client:
        meta = await client.get(
            f"/api/v1/dossiers/{built_page}",
            params={"parts": "dossier,metadata", "budget": budget},
        )
        sourced = await client.get(
            f"/api/v1/dossiers/{built_page}.md",
            params={"parts": "dossier,sources", "budget": budget},
        )
        reply = await client.get(target, params={**params, "budget": budget})

    used = meta.json()["metadata"]["budget"]["used_est_tokens"]
    assert used == est_tokens(_content_with_markers(sourced.text))
    assert used <= int(budget)
    assert int(reply.headers["wke-dossier-tokens"]) == used


@pytest.mark.parametrize("selection", SELECTIONS)
@pytest.mark.parametrize(("url", "params"), _ALL_ROUTES)
async def test_both_token_headers_on_every_route(app, built_page, url, params, selection) -> None:
    async with app_client(app) as client:
        response = await client.get(
            url.format(page=built_page), params={**params, "parts": selection}
        )

    assert int(response.headers["wke-total-tokens"]) == est_tokens(response.text)
    assert 0 < int(response.headers["wke-dossier-tokens"]) <= 8000
    assert "wke-tokens" not in response.headers


@pytest.mark.parametrize("selection", [None, *SELECTIONS])
async def test_post_200_equals_get_for_the_same_parts(app, built_page, selection) -> None:
    params = {} if selection is None else {"parts": selection}
    async with app_client(app) as client:
        posted = await client.post("/api/v1/dossiers", params=params, json={"title": FIXTURE_TITLE})
        fetched = await client.get(f"/api/v1/dossiers/{built_page}", params=params)

    assert posted.status_code == 200
    assert posted.content == fetched.content
    assert posted.headers["etag"] == fetched.headers["etag"]
    assert posted.headers["wke-dossier-tokens"] == fetched.headers["wke-dossier-tokens"]
    assert posted.headers["wke-total-tokens"] == fetched.headers["wke-total-tokens"]


async def test_main_rev_and_post_serialise_the_full_body_the_same(app, built_page) -> None:
    params = {"parts": FULL}
    async with app_client(app) as client:
        main = await client.get(f"/api/v1/dossiers/{built_page}", params=params)
        rev = await client.get(f"/api/v1/dossiers/{built_page}/rev/{FIXTURE_REV_ID}", params=params)
        posted = await client.post("/api/v1/dossiers", params=params, json={"title": FIXTURE_TITLE})

    assert main.content == rev.content == posted.content
    assert json.loads(main.content)["metadata"]["links"].keys() >= {"self", "markdown"}


async def test_links_carry_the_selection_unless_it_is_the_default(app, built_page) -> None:
    async with app_client(app) as client:
        default = await app.state.service.get_dossier_view(built_page, 8000, "json", False)
        full = await client.get(f"/api/v1/dossiers/{built_page}", params={"parts": FULL})

    links = full.json()["metadata"]["links"]
    for name in ("self_", "pinned", "markdown"):
        assert "parts=" not in str(getattr(default.links, name))
    for name in ("self", "pinned", "markdown"):
        assert links[name].endswith(f"&parts={FULL}")
