"""A packed dossier view: not-built errors, links, and the rebuild a stale read triggers."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from tests.factories.dossier import make_fixture_dossier
from tests.support.services import make_service, seed_dossier
from wke.clients.redis import RedisClient
from wke.core import keys
from wke.core.citations import seed_pin
from wke.core.errors import ApiException
from wke.core.models import DossierView
from wke.services.dossiers import DossierService

DOSSIER = make_fixture_dossier()
PAGE_ID = DOSSIER.topic.page_id
PINNED_REV_ID = seed_pin(DOSSIER).rev_id


async def _stale_page(redis_client: RedisClient) -> DossierService:
    """Store the dossier with a newer revision the watcher saw ten minutes ago."""
    await seed_dossier(redis_client, DOSSIER)
    newer = PINNED_REV_ID + 1
    await redis_client.set(keys.latest_rev(PAGE_ID), str(newer))
    await redis_client.zadd(
        keys.pageedits(PAGE_ID), {str(newer): datetime.now(UTC).timestamp() - 600}
    )
    return make_service(redis_client)


async def _let_background_tasks_run() -> None:
    for _ in range(20):
        await asyncio.sleep(0)


async def test_a_stale_latest_read_queues_a_background_rebuild(redis_client: RedisClient) -> None:
    service = await _stale_page(redis_client)

    view = await service.get_dossier_view(PAGE_ID, 8000, "json", False)
    await _let_background_tasks_run()

    assert view.freshness.state == "stale"
    assert await redis_client.llen(keys.QUEUE_BACKGROUND) == 1


async def test_a_read_pinned_to_a_revision_never_queues_a_rebuild(
    redis_client: RedisClient,
) -> None:
    service = await _stale_page(redis_client)

    view = await service.get_dossier_view(PAGE_ID, 8000, "json", False, rev_id=PINNED_REV_ID)
    await _let_background_tasks_run()

    assert view.freshness.state == "stale"
    assert await redis_client.llen(keys.QUEUE_BACKGROUND) == 0


@pytest.mark.parametrize(
    "pointer", [None, "not json", '{"pipeline_version": "x"}', '{"rev_id": 1}']
)
async def test_a_page_without_a_usable_pointer_or_dossier_is_not_built(
    redis_client: RedisClient, pointer: str | None
) -> None:
    if pointer is not None:
        await redis_client.set(keys.ptr(PAGE_ID), pointer)

    with pytest.raises(ApiException) as exc_info:
        await make_service(redis_client).get_dossier_view(PAGE_ID, 8000, "json", False)

    assert (exc_info.value.status_code, exc_info.value.code) == (404, "not_built")


async def test_a_revision_that_was_never_built_is_not_built(redis_client: RedisClient) -> None:
    await seed_dossier(redis_client, DOSSIER)

    with pytest.raises(ApiException) as exc_info:
        await make_service(redis_client).get_dossier_view(
            PAGE_ID, 8000, "json", False, rev_id=PINNED_REV_ID + 1
        )

    assert exc_info.value.code == "not_built"


async def test_links_name_the_pinned_revision_and_carry_a_non_default_parts_selection(
    redis_client: RedisClient,
) -> None:
    await seed_dossier(redis_client, DOSSIER)
    service = make_service(redis_client)

    plain = await service.get_dossier_view(PAGE_ID, 8000, "json", False)
    with_sources = await service.get_dossier_view(
        PAGE_ID, 2000, "json", False, parts=frozenset({"dossier", "sources"})
    )

    dossier_url = f"https://wke.piotrkrzysztof.dev/api/v1/dossiers/{PAGE_ID}"
    assert str(plain.links.self_) == f"{dossier_url}?budget=8000&format=json"
    assert str(plain.links.pinned) == f"{dossier_url}/rev/{PINNED_REV_ID}?budget=8000"
    assert str(plain.links.markdown) == f"{dossier_url}.md?budget=8000"
    assert str(with_sources.links.self_).endswith("&parts=dossier,sources")
    assert str(with_sources.links.pinned).endswith("?budget=2000&parts=dossier,sources")


async def test_markdown_format_returns_the_rendered_text(redis_client: RedisClient) -> None:
    await seed_dossier(redis_client, DOSSIER)
    service = make_service(redis_client)

    markdown = await service.get_dossier_view(PAGE_ID, 8000, "markdown", False)
    view = await service.get_dossier_view(PAGE_ID, 8000, "json", False)

    assert isinstance(markdown, str)
    assert isinstance(view, DossierView)
    assert DOSSIER.topic.title in markdown
