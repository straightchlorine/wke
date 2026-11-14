"""GET /api/v1/dossiers and its sub-routes, and the dossier list."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

import pytest

from tests.support.apps import app_client, make_app
from tests.support.constants import FIXTURE_REV_ID, FIXTURE_TITLE, PIPELINE_VERSION
from wke.core import keys
from wke.core.models import Dossier
from wke.core.render import SUMMARY_LABEL
from wke.settings import Settings


async def test_get_dossier_link_header_uses_https_by_default(app, built_page) -> None:
    async with app_client(app) as client:
        response = await client.get(f"/api/v1/dossiers/{built_page}")

    assert response.status_code == 200
    target = urlsplit(re.match(r"<([^>]+)>", response.headers["link"])[1])
    assert (target.scheme, target.netloc) == ("https", "wke.piotrkrzysztof.dev")


async def test_get_dossier_link_header_uses_public_scheme_http(
    fake_redis, wikimedia_client, ml_client_ok, built_page, monkeypatch
) -> None:
    """PUBLIC_SCHEME=http (local dev, no TLS) must flow through to the
    Link header, not a hardcoded https.
    """
    monkeypatch.setenv("PUBLIC_SCHEME", "http")
    app = make_app(
        fake_redis,
        Settings.model_validate({}),
        wikimedia_http=wikimedia_client._http,
        ml_http=ml_client_ok._http,
        start_worker=True,
    )

    async with app_client(app) as client:
        response = await client.get(f"/api/v1/dossiers/{built_page}")

    assert response.status_code == 200
    target = urlsplit(re.match(r"<([^>]+)>", response.headers["link"])[1])
    assert (target.scheme, target.netloc) == ("http", "wke.piotrkrzysztof.dev")
    assert "https://" not in response.headers["link"]


async def test_get_dossier_carries_freshness_and_discovery_links(app, built_page) -> None:
    async with app_client(app) as client:
        response = await client.get(
            f"/api/v1/dossiers/{built_page}", params={"parts": "dossier,metadata"}
        )

    metadata = response.json()["metadata"]
    assert response.headers["wke-freshness"] == metadata["freshness"]["state"]
    assert response.headers["link"] == (
        f'<{metadata["links"]["markdown"]}>; rel="alternate"; type="text/markdown", '
        '</llms.txt>; rel="describedby"'
    )


async def test_get_dossier_unbuilt_page_is_404(app) -> None:
    async with app_client(app) as client:
        response = await client.get("/api/v1/dossiers/999999")

    assert response.status_code == 404
    assert response.json()["code"] == "not_built"


async def test_get_dossier_revision_has_immutable_cache_control(app, built_page) -> None:
    async with app_client(app) as client:
        response = await client.get(f"/api/v1/dossiers/{built_page}/rev/{FIXTURE_REV_ID}")

    assert response.status_code == 200
    assert "immutable" in response.headers["cache-control"]


async def test_get_dossier_revision_partial_build_is_not_immutable(app, partial_built_page) -> None:
    async with app_client(app) as client:
        response = await client.get(f"/api/v1/dossiers/{partial_built_page}/rev/{FIXTURE_REV_ID}")

    assert response.status_code == 200
    assert "immutable" not in response.headers["cache-control"]
    assert response.headers["cache-control"] == "public, max-age=60"


async def test_get_dossier_omitted_budget_defaults_to_8000(app, built_page) -> None:
    async with app_client(app) as client:
        response = await client.get(
            f"/api/v1/dossiers/{built_page}", params={"parts": "dossier,metadata"}
        )

    assert response.status_code == 200
    assert response.json()["metadata"]["budget"]["requested"] == 8000


async def test_get_dossier_revision_structural_build_is_not_immutable(
    app, built_page, fake_redis
) -> None:
    """A complete build without ML analysis is rebuilt later: not cacheable for a year."""
    key = keys.dossier(built_page, FIXTURE_REV_ID, PIPELINE_VERSION)
    dossier = Dossier.model_validate_json(await fake_redis.get(key))
    structural = dossier.model_copy(
        update={"build": dossier.build.model_copy(update={"analysis": "structural"})}
    )
    await fake_redis.set(key, structural.model_dump_json())

    async with app_client(app) as client:
        response = await client.get(f"/api/v1/dossiers/{built_page}/rev/{FIXTURE_REV_ID}")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=60"


async def test_get_dossier_bad_format_is_422(app, built_page) -> None:
    async with app_client(app) as client:
        response = await client.get(f"/api/v1/dossiers/{built_page}", params={"format": "yaml"})

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


async def test_list_dossiers_returns_built_page(app, built_page) -> None:
    async with app_client(app) as client:
        response = await client.get("/api/v1/dossiers")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"items", "next_cursor"}
    assert body["next_cursor"] is None
    assert any(item["page_id"] == built_page for item in body["items"])


@pytest.mark.parametrize(
    ("params", "status"),
    [
        ({"limit": 1}, 200),
        ({"limit": 100}, 200),
        ({"limit": 0}, 422),
        ({"limit": 101}, 422),
        ({"q": ""}, 422),
    ],
)
async def test_list_dossiers_params_are_bounded(
    app, params: dict[str, int | str], status: int
) -> None:
    async with app_client(app) as client:
        response = await client.get("/api/v1/dossiers", params=params)

    assert response.status_code == status


async def test_list_dossiers_filters_by_query(app, built_page) -> None:
    async with app_client(app) as client:
        no_match = await client.get("/api/v1/dossiers", params={"q": "Nonexistent Xyz"})
        match = await client.get("/api/v1/dossiers", params={"q": FIXTURE_TITLE.lower()})

    assert no_match.json()["items"] == []
    assert any(item["page_id"] == built_page for item in match.json()["items"])


_REV = FIXTURE_REV_ID
NOTICE_PATTERN = r"Summary (withheld|skipped|unavailable)"

_MARKDOWN_URLS = [
    pytest.param("/api/v1/dossiers/{page}.md", {}, id="md-route"),
    pytest.param("/api/v1/dossiers/{page}", {"format": "md"}, id="main-format-md"),
    pytest.param(f"/api/v1/dossiers/{{page}}/rev/{_REV}", {"format": "md"}, id="rev-format-md"),
]


@pytest.mark.parametrize(("url", "params"), _MARKDOWN_URLS)
async def test_inline_links_are_opt_in_and_named_on_the_budget_line(
    app, built_page, url, params
) -> None:
    params = {**params, "parts": "dossier,metadata"}
    async with app_client(app) as client:
        plain = await client.get(url.format(page=built_page), params=params)
        linked = await client.get(url.format(page=built_page), params={**params, "links": "true"})

    assert plain.status_code == linked.status_code == 200
    assert "inline links are not counted" not in plain.text
    assert "inline links are not counted in the budget" in linked.text
    assert plain.headers["etag"] != linked.headers["etag"]


@pytest.mark.parametrize(
    "url",
    [
        "/api/v1/dossiers/{page}",
        "/api/v1/dossiers/{page}.md",
        f"/api/v1/dossiers/{{page}}/rev/{_REV}",
    ],
    ids=["main", "md-route", "rev"],
)
@pytest.mark.parametrize("budget", ["9999", "huge"])
async def test_get_dossier_bad_budget_is_422(app, built_page, url, budget) -> None:
    async with app_client(app) as client:
        response = await client.get(url.format(page=built_page), params={"budget": budget})

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "validation_error"


@pytest.mark.parametrize(
    "url",
    [
        "/api/v1/dossiers/{page}",
        "/api/v1/dossiers/{page}.md",
        f"/api/v1/dossiers/{{page}}/rev/{_REV}",
    ],
    ids=["main", "md-route", "rev"],
)
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2000", 2000),
        ("8000", 8000),
        ("32000", 32000),
        ("2k", 2000),
        ("8k", 8000),
        ("32k", 32000),
    ],
)
async def test_get_dossier_budget_value_and_alias_are_200(
    app, built_page, url: str, raw: str, expected: int
) -> None:
    async with app_client(app) as client:
        response = await client.get(
            url.format(page=built_page), params={"budget": raw, "parts": "dossier,metadata"}
        )

    assert response.status_code == 200
    if url.endswith(".md"):
        assert response.headers["content-type"].startswith("text/markdown")
        async with app_client(app) as client:
            other = await client.get(
                url.format(page=built_page),
                params={
                    "budget": "2000" if expected != 2000 else "8000",
                    "parts": "dossier,metadata",
                },
            )
        assert other.headers["etag"] != response.headers["etag"]
    else:
        assert response.json()["metadata"]["budget"]["requested"] == expected


async def test_get_dossier_summaries_true_changes_etag_and_keeps_the_wke_headers(
    app, built_page
) -> None:
    url = f"/api/v1/dossiers/{built_page}"
    async with app_client(app) as client:
        default = await client.get(url)
        with_summaries = await client.get(url, params={"summaries": "true"})

    assert default.status_code == with_summaries.status_code == 200
    assert default.headers["etag"] != with_summaries.headers["etag"]
    assert 0 < int(default.headers["wke-dossier-tokens"]) <= 8000
    assert 0 < int(with_summaries.headers["wke-dossier-tokens"]) <= 8000
    assert default.headers["wke-freshness"] == with_summaries.headers["wke-freshness"]


@pytest.mark.parametrize(("url", "extra"), _MARKDOWN_URLS)
async def test_markdown_has_no_summaries_or_notices_by_default(app, built_page, url, extra) -> None:
    url = url.format(page=built_page)
    async with app_client(app) as client:
        default = await client.get(url, params=extra)
        explicit_off = await client.get(url, params={**extra, "summaries": "false"})
        opted_in = await client.get(url, params={**extra, "summaries": "true"})

    assert opted_in.headers["content-type"].startswith("text/markdown")
    assert SUMMARY_LABEL in opted_in.text
    assert SUMMARY_LABEL not in default.text
    assert not re.search(NOTICE_PATTERN, default.text)
    assert default.text == explicit_off.text
    assert default.headers["etag"] == explicit_off.headers["etag"]
    assert default.headers["etag"] != opted_in.headers["etag"]
