"""/sitemap.xml: static pages, one URL per built dossier, ETag and 304."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from unittest.mock import AsyncMock

from tests.support.apps import app_client
from tests.support.constants import FIXTURE_TITLE, FIXTURE_WIKI_TITLE
from wke.api.sitemap import render_sitemap
from wke.core import keys
from wke.core.models import DossierListItem
from wke.core.viewcache import invalidate_views

NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def _item(page_id: int, title: str) -> DossierListItem:
    return DossierListItem(
        page_id=page_id,
        title=title,
        rev_id=10 + page_id,
        pinned_at=datetime(2026, 9, 1, 12, 30, 5, tzinfo=UTC),
        freshness_state="fresh",
        edits_since_pin=0,
        largest_budget_filled=8000,
        sections=3,
        built_at=datetime(2026, 9, 2, tzinfo=UTC),
    )


async def test_sitemap_empty_index_lists_static_pages_only() -> None:
    service = AsyncMock()
    service.base_url = "https://empty.example.test"
    service.list_dossiers.return_value = ([], None)

    body = await render_sitemap(service)

    root = ET.fromstring(body)
    locs = [e.text for e in root.findall("s:url/s:loc", NS)]
    assert locs == [
        "https://empty.example.test/",
        "https://empty.example.test/t/",
        "https://empty.example.test/machines",
    ]
    assert root.findall("s:url/s:lastmod", NS) == []


async def test_sitemap_lists_dossiers_and_escapes_titles() -> None:
    service = AsyncMock()
    service.base_url = "https://two.example.test"
    service.list_dossiers.return_value = (
        [_item(1, "AT&T <Corp>"), _item(2, FIXTURE_TITLE)],
        None,
    )

    body = await render_sitemap(service)

    assert body.isascii()
    root = ET.fromstring(body)
    urls = root.findall("s:url", NS)
    assert len(urls) == 5
    locs = [u.findtext("s:loc", namespaces=NS) for u in urls]
    assert f"https://two.example.test/t/{FIXTURE_WIKI_TITLE}" in locs
    assert "https://two.example.test/t/AT%26T_%3CCorp%3E" in locs
    assert urls[3].findtext("s:lastmod", namespaces=NS) == "2026-09-01T12:30:05Z"


async def test_sitemap_caps_entries() -> None:
    service = AsyncMock()
    service.base_url = "https://cap.example.test"
    service.list_dossiers.return_value = ([_item(i, f"T{i}") for i in range(10)], "next")

    body = await render_sitemap(service, max_entries=6)

    assert len(ET.fromstring(body).findall("s:url", NS)) == 6


async def test_sitemap_route_is_served_as_xml(app) -> None:
    async with app_client(app) as client:
        response = await client.get("/sitemap.xml")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")


async def test_sitemap_etag_follows_the_listed_dossiers(app, built_page, fake_redis) -> None:
    async with app_client(app) as client:
        before = await client.get("/sitemap.xml")
        await fake_redis.delete(keys.BUILT)
        invalidate_views()
        after = await client.get("/sitemap.xml", headers={"If-None-Match": before.headers["etag"]})

    assert after.status_code == 200
    assert after.headers["etag"] != before.headers["etag"]


async def test_sitemap_lists_a_dossier_built_after_the_first_render() -> None:
    service = AsyncMock()
    service.base_url = "https://fresh.example.test"
    service.list_dossiers.return_value = ([], None)
    await render_sitemap(service)

    service.list_dossiers.return_value = ([_item(7, "Madonna")], None)
    invalidate_views()
    body = await render_sitemap(service)

    assert "https://fresh.example.test/t/Madonna" in body
