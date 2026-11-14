"""Cached reads of the revision inputs, and the citations built from the related pages."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from tests.support.constants import FIXTURE_PAGE_ID, FIXTURE_REV_ID, FIXTURE_TITLE
from tests.support.metrics import metric_sample
from tests.support.wikimedia import WmFixtures, make_wikimedia_client
from wke.clients.redis import RedisClient
from wke.clients.wikimedia import WikimediaClient
from wke.jobs.build.cite import build_related_citations
from wke.jobs.build.fetch import fetch_html, fetch_related, fetch_revision_timestamp

ORIGIN = "https://en.wikipedia.org"


def _offline_wikimedia(redis_client: RedisClient) -> WikimediaClient:
    """A client that fails every request, so a read can only come from the cache."""
    return make_wikimedia_client(redis_client, lambda _request: httpx.Response(500))


def _hits(kind: str) -> float:
    return metric_sample("wke_cache_requests_total", {"kind": kind, "result": "hit"})


async def test_html_is_cached_after_the_first_fetch(
    redis_client: RedisClient, wikimedia_client: WikimediaClient, wm_fixtures: WmFixtures
) -> None:
    before = _hits("html")
    first = await fetch_html(redis_client, wikimedia_client, FIXTURE_REV_ID)
    second = await fetch_html(redis_client, _offline_wikimedia(redis_client), FIXTURE_REV_ID)

    assert first == second == wm_fixtures.text("parsoid.html")
    assert _hits("html") == before + 1


async def test_revision_timestamp_is_cached_after_the_first_fetch(
    redis_client: RedisClient, wikimedia_client: WikimediaClient
) -> None:
    first = await fetch_revision_timestamp(redis_client, wikimedia_client, FIXTURE_REV_ID)
    second = await fetch_revision_timestamp(
        redis_client, _offline_wikimedia(redis_client), FIXTURE_REV_ID
    )

    assert first == second
    assert first.tzinfo is not None


async def test_related_pages_are_cached_after_the_first_fetch(
    redis_client: RedisClient, wikimedia_client: WikimediaClient
) -> None:
    before = _hits("related")
    first = await fetch_related(redis_client, wikimedia_client, FIXTURE_PAGE_ID, FIXTURE_TITLE)
    second = await fetch_related(
        redis_client, _offline_wikimedia(redis_client), FIXTURE_PAGE_ID, FIXTURE_TITLE
    )

    assert first
    assert first == second
    assert _hits("related") == before + 1


def _page(page_id: int, **overrides: Any) -> dict[str, Any]:
    page: dict[str, Any] = {
        "pageid": page_id,
        "title": f"Page {page_id}",
        "lastrevid": page_id * 10,
        "extract": f"Lead of {page_id}.",
        "revisions": [{"timestamp": "2026-01-02T03:04:05Z"}],
    }
    return page | overrides


def test_related_citations_skip_incomplete_pages_without_a_gap_in_the_ids() -> None:
    pages = [
        _page(1, revisions=[]),
        _page(2, lastrevid=None),
        _page(3),
        {
            "title": "No page id",
            "lastrevid": 1,
            "revisions": [{"timestamp": "2026-01-02T03:04:05Z"}],
        },
        _page(4),
    ]

    citations, nodes, leads = build_related_citations(pages, ORIGIN, start_index=2)

    assert [c.id for c in citations] == ["c2", "c3"]
    assert [c.pin.page_id for c in citations] == [3, 4]
    assert [n.id for n in nodes] == [3, 4]
    assert leads == [{"page_id": 3, "text": "Lead of 3."}, {"page_id": 4, "text": "Lead of 4."}]
    assert all(c.role == "related" for c in citations)
    pin = citations[0].pin
    assert str(pin.url) == f"{ORIGIN}/wiki/Page_3"
    assert str(pin.permalink) == f"{ORIGIN}/w/index.php?oldid=30"
    assert pin.rev_timestamp.isoformat() == "2026-01-02T03:04:05+00:00"


@pytest.mark.parametrize(
    ("title", "path"),
    [("Caf\u00e9 au lait", "Caf%C3%A9_au_lait"), ("Tom & Jerry?", "Tom_%26_Jerry%3F")],
)
def test_related_pin_url_quotes_the_title(title: str, path: str) -> None:
    [citation], _, _ = build_related_citations([_page(5, title=title)], ORIGIN, start_index=2)

    assert str(citation.pin.url) == f"{ORIGIN}/wiki/{path}"
