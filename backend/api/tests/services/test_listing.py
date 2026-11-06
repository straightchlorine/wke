"""Paging, filtering and unreadable rows of the dossier catalog."""

from __future__ import annotations

import json

import pytest

from tests.factories.dossier import make_fixture_dossier
from tests.support.constants import PIPELINE_VERSION
from tests.support.services import make_service, renamed, seed_dossier
from wke.clients.redis import RedisClient
from wke.core import keys
from wke.services.dossiers import DossierService


async def _catalog(redis_client: RedisClient, titles: list[str]) -> DossierService:
    """Store one dossier per title, built one minute apart, the last title newest."""
    base = make_fixture_dossier()
    for index, title in enumerate(titles, start=1):
        built_at = base.build.built_at.replace(minute=index)
        dossier = renamed(base, index, title)
        dossier = dossier.model_copy(
            update={"build": dossier.build.model_copy(update={"built_at": built_at})}
        )
        await seed_dossier(redis_client, dossier)
    return make_service(redis_client)


async def test_pages_follow_next_cursor_newest_first(redis_client: RedisClient) -> None:
    service = await _catalog(redis_client, ["One", "Two", "Three"])

    first, cursor = await service.list_dossiers(None, 2, None)
    second, last_cursor = await service.list_dossiers(None, 2, cursor)

    assert [item.title for item in first] == ["Three", "Two"]
    assert cursor == "2"
    assert [item.title for item in second] == ["One"]
    assert last_cursor is None


async def test_a_page_that_ends_exactly_at_the_last_item_has_no_next_cursor(
    redis_client: RedisClient,
) -> None:
    service = await _catalog(redis_client, ["One", "Two"])

    items, next_cursor = await service.list_dossiers(None, 2, None)

    assert len(items) == 2
    assert next_cursor is None


@pytest.mark.parametrize("cursor", ["-1", "abc", ""])
async def test_a_cursor_that_is_not_a_non_negative_integer_starts_at_the_first_page(
    redis_client: RedisClient, cursor: str
) -> None:
    service = await _catalog(redis_client, ["One", "Two"])

    items, next_cursor = await service.list_dossiers(None, 1, cursor)

    assert [item.title for item in items] == ["Two"]
    assert next_cursor == "1"


async def test_q_filters_titles_case_insensitively(redis_client: RedisClient) -> None:
    service = await _catalog(redis_client, ["Grace Hopper", "Alan Turing", "Hopper Dam"])

    items, next_cursor = await service.list_dossiers("HOPPER", 10, None)

    assert [item.title for item in items] == ["Hopper Dam", "Grace Hopper"]
    assert next_cursor is None


async def test_rows_without_a_readable_pointer_or_dossier_are_left_out(
    redis_client: RedisClient,
) -> None:
    service = await _catalog(redis_client, ["Readable"])
    unreadable = {
        "bad-pointer": ("not json", None),
        "pointer-without-rev": ('{"pipeline_version": "x"}', None),
        "no-dossier": (json.dumps({"rev_id": 1}), None),
        "unreadable-dossier": (json.dumps({"rev_id": 1}), '{"build": 1}'),
    }
    for page_id, (pointer, dossier_json) in enumerate(unreadable.values(), start=100):
        await redis_client.zadd(keys.BUILT, {str(page_id): 1.0})
        await redis_client.set(keys.ptr(page_id), pointer)
        if dossier_json is not None:
            await redis_client.set(keys.dossier(page_id, 1, PIPELINE_VERSION), dossier_json)
    await redis_client.zadd(keys.BUILT, {"999": 1.0})

    items, _ = await service.list_dossiers(None, 10, None)

    assert [item.title for item in items] == ["Readable"]
