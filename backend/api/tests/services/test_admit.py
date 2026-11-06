"""Build admission against the recorded Wikimedia fixtures."""

from __future__ import annotations

import pytest

from tests.support.constants import (
    FIXTURE_PAGE_ID,
    FIXTURE_REV_ID,
    FIXTURE_REV_TIMESTAMP,
    FIXTURE_TITLE,
    MISSING_TITLE,
    PIPELINE_VERSION,
)
from tests.support.services import make_service
from tests.support.wikimedia import WmFixtures, wikimedia_handler
from wke.clients.redis import RedisClient
from wke.core import keys
from wke.core.errors import ApiException
from wke.core.models import Job
from wke.core.viewcache import current_generation
from wke.services.dossiers import DossierService


def _service(redis_client: RedisClient, wm_fixtures: WmFixtures) -> DossierService:
    return make_service(redis_client, wikimedia_handler(wm_fixtures))


async def test_admission_pins_the_revision_and_caches_its_edit_time(
    redis_client: RedisClient, wm_fixtures: WmFixtures
) -> None:
    result = await _service(redis_client, wm_fixtures).request_build(FIXTURE_TITLE)

    assert isinstance(result, Job)
    cached = await redis_client.get(keys.wm_revts(FIXTURE_REV_ID))
    assert cached == FIXTURE_REV_TIMESTAMP.replace("Z", "+00:00")


async def test_refresh_rebuilds_in_the_background_and_drops_cached_views(
    redis_client: RedisClient, wm_fixtures: WmFixtures
) -> None:
    dossier_key = keys.dossier(FIXTURE_PAGE_ID, FIXTURE_REV_ID, PIPELINE_VERSION)
    await redis_client.set(dossier_key, "{}")
    service = _service(redis_client, wm_fixtures)
    generation = current_generation()

    ready = await service.request_build(FIXTURE_TITLE)
    assert ready == "ready"
    assert current_generation() == generation

    refreshed = await service.request_build(FIXTURE_TITLE, refresh=True)

    assert isinstance(refreshed, Job)
    assert current_generation() > generation
    assert await redis_client.get(dossier_key) == "{}"
    assert await redis_client.llen(keys.QUEUE_BACKGROUND) == 1
    assert await redis_client.llen(keys.QUEUE_INTERACTIVE) == 0


async def test_a_missing_title_is_a_404_and_its_page_id_stays_unknown(
    redis_client: RedisClient, wm_fixtures: WmFixtures
) -> None:
    service = _service(redis_client, wm_fixtures)

    with pytest.raises(ApiException) as exc_info:
        await service.request_build(MISSING_TITLE)

    assert exc_info.value.code == "not_found"
    assert await service.peek_dossier_state_for_title(MISSING_TITLE) is None


async def test_peek_reads_only_the_cache_and_reports_the_stored_state(
    redis_client: RedisClient, wm_fixtures: WmFixtures
) -> None:
    service = _service(redis_client, wm_fixtures)
    assert await service.peek_dossier_state_for_title(FIXTURE_TITLE) is None

    await service.request_build(FIXTURE_TITLE)

    assert await service.peek_dossier_state_for_title(FIXTURE_TITLE) == (FIXTURE_PAGE_ID, "none")
