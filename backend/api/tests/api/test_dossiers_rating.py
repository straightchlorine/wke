"""Selection by rating on the REST routes: JSON field, ETag and cache lifetime."""

from __future__ import annotations

import re

import pytest

from tests.support.apps import app_client
from tests.support.constants import FIXTURE_REV_ID, PIPELINE_VERSION
from wke.core import keys
from wke.core.models import Dossier
from wke.jobs.build.constants import RATING_MODEL, RATING_PROMPT_SHA256
from wke.jobs.build.rating import RatingDocument, rating_key
from wke.settings import Settings

PARTS = {"parts": "dossier,metadata"}
IMMUTABLE = "public, max-age=31536000, immutable"
LATEST = "public, max-age=60"


@pytest.fixture
def rating_on(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "selection_rating", True)


async def _store_rating(fake_redis, page_id: int) -> None:
    key = keys.dossier(page_id, FIXTURE_REV_ID, PIPELINE_VERSION)
    dossier = Dossier.model_validate_json(await fake_redis.get(key))
    document = RatingDocument(
        prompt_sha256=RATING_PROMPT_SHA256,
        model=RATING_MODEL,
        done=True,
        scores={c.id: 1.0 for c in dossier.chunks if c.kind == "prose"},
    )
    await fake_redis.set(
        rating_key(page_id, FIXTURE_REV_ID, PIPELINE_VERSION), document.model_dump_json()
    )


async def test_with_the_switch_off_nothing_is_added_to_the_response(app, built_page) -> None:
    async with app_client(app) as client:
        response = await client.get(f"/api/v1/dossiers/{built_page}", params=PARTS)
        pinned = await client.get(f"/api/v1/dossiers/{built_page}/rev/{FIXTURE_REV_ID}")

    assert "selection" not in response.json()["metadata"]["build"]
    assert not re.search(r'-r[01]"$', response.headers["etag"])
    assert pinned.headers["cache-control"] == IMMUTABLE


async def test_without_a_stored_rating_the_response_says_relevance_and_is_not_immutable(
    app, built_page, rating_on
) -> None:
    async with app_client(app) as client:
        response = await client.get(f"/api/v1/dossiers/{built_page}", params=PARTS)
        as_md = await client.get(f"/api/v1/dossiers/{built_page}.md")
        pinned = await client.get(f"/api/v1/dossiers/{built_page}/rev/{FIXTURE_REV_ID}")

    assert response.json()["metadata"]["build"]["selection"] == "relevance"
    assert response.headers["etag"].endswith('-r0"')
    assert as_md.headers["etag"].endswith('-r0"')
    assert pinned.headers["cache-control"] == LATEST


async def test_with_a_stored_rating_the_response_says_rating_and_the_etag_changes(
    app, built_page, fake_redis, rating_on
) -> None:
    async with app_client(app) as client:
        before = await client.get(f"/api/v1/dossiers/{built_page}", params=PARTS)
        await _store_rating(fake_redis, built_page)
        after = await client.get(
            f"/api/v1/dossiers/{built_page}",
            params=PARTS,
            headers={"If-None-Match": before.headers["etag"]},
        )
        pinned = await client.get(f"/api/v1/dossiers/{built_page}/rev/{FIXTURE_REV_ID}")

    assert after.status_code == 200
    assert after.json()["metadata"]["build"]["selection"] == "rating"
    assert after.headers["etag"].endswith('-r1"')
    assert after.headers["etag"][:-3] == before.headers["etag"][:-3]
    assert pinned.headers["cache-control"] == IMMUTABLE
