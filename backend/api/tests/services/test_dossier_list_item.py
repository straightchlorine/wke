"""Honesty checks for DossierListItem: largest_budget_filled must be the
smallest budget whose pack is complete (32000 if none is), and pinned_at
must be the seed pin's rev_timestamp, not the fetch time.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tests.factories.dossier import (
    make_fixture_dossier,
    make_lead_only_dossier,
    make_overflowing_fixture_dossier,
)
from tests.support.services import make_service, seed_dossier
from wke.clients.redis import RedisClient
from wke.core import keys, pack
from wke.core.citations import seed_pin as seed_pin_of
from wke.core.models import Chunk, Dossier, DossierListItem
from wke.core.text.tokens import est_tokens


def _sliced_overflow_dossier() -> Dossier:
    """An overflow-fixture dossier too big for 2000 tokens but complete at 8000."""
    dossier = make_overflowing_fixture_dossier()
    keep_sections = dossier.sections[:1] + dossier.sections[1:3]
    keep_ids = {chunk_id for section in keep_sections for chunk_id in section.chunk_ids}
    keep_chunks = [chunk for chunk in dossier.chunks if chunk.id in keep_ids]
    return dossier.model_copy(update={"sections": keep_sections, "chunks": keep_chunks})


def _unpackable_overflow_dossier() -> Dossier:
    """An overflow-fixture dossier too big to complete at any of the three budgets."""
    dossier = make_overflowing_fixture_dossier()
    huge_chunks: list[Chunk] = []
    for chunk in dossier.chunks:
        text = (chunk.text + " ") * 3
        huge_chunks.append(chunk.model_copy(update={"text": text, "est_tokens": est_tokens(text)}))
    return dossier.model_copy(update={"chunks": huge_chunks})


async def _list_item(redis_client: RedisClient, dossier: Dossier) -> DossierListItem:
    await seed_dossier(redis_client, dossier)
    service = make_service(redis_client)
    items, _ = await service.list_dossiers(None, 10, None)
    return next(item for item in items if item.page_id == dossier.topic.page_id)


async def test_largest_budget_filled_is_2000_when_smallest_pack_is_complete(
    redis_client: RedisClient,
) -> None:
    item = await _list_item(redis_client, make_fixture_dossier())

    assert item.largest_budget_filled == 2000


async def test_largest_budget_filled_is_2000_when_only_the_header_and_sources_would_overflow(
    redis_client: RedisClient,
) -> None:
    # The passage and its heading and tag fit 2000; the title, pin line, notices
    # and Sources line that surround it in the Markdown are not charged.
    dossier = make_lead_only_dossier(1975)
    assert pack.pack(dossier, 2000).budget.complete

    item = await _list_item(redis_client, dossier)

    assert item.largest_budget_filled == 2000


async def test_largest_budget_filled_is_8000_when_that_is_the_first_complete_pack(
    redis_client: RedisClient,
) -> None:
    item = await _list_item(redis_client, _sliced_overflow_dossier())

    assert item.largest_budget_filled == 8000


async def test_largest_budget_filled_defaults_to_32000_when_none_complete(
    redis_client: RedisClient,
) -> None:
    dossier = _unpackable_overflow_dossier()
    assert not pack.pack(dossier, 32000).budget.complete

    item = await _list_item(redis_client, dossier)

    assert item.largest_budget_filled == 32000


async def test_pinned_at_is_the_seed_pins_rev_timestamp_not_retrieved_at(
    redis_client: RedisClient,
) -> None:
    dossier = make_fixture_dossier()
    seed_pin = seed_pin_of(dossier)
    stale_pin = seed_pin.model_copy(update={"retrieved_at": datetime(2030, 1, 1, tzinfo=UTC)})
    citations = [
        citation.model_copy(update={"pin": stale_pin}) if citation.role == "seed" else citation
        for citation in dossier.citations
    ]
    dossier = dossier.model_copy(update={"citations": citations})

    item = await _list_item(redis_client, dossier)

    assert item.pinned_at == stale_pin.rev_timestamp
    assert item.pinned_at != stale_pin.retrieved_at


async def test_freshness_state_is_unknown_when_watcher_has_no_pointer(
    redis_client: RedisClient,
) -> None:
    item = await _list_item(redis_client, make_fixture_dossier())

    assert item.freshness_state == "unknown"
    assert item.edits_since_pin == 0


async def test_freshness_state_is_fresh_when_pinned_rev_is_the_latest(
    redis_client: RedisClient,
) -> None:
    dossier = make_fixture_dossier()
    page_id = dossier.topic.page_id
    pinned_rev_id = seed_pin_of(dossier).rev_id
    await redis_client.set(keys.latest_rev(page_id), str(pinned_rev_id))

    item = await _list_item(redis_client, dossier)

    assert item.freshness_state == "fresh"
    assert item.edits_since_pin == 0


async def test_freshness_state_is_stale_when_watcher_saw_a_newer_revision(
    redis_client: RedisClient,
) -> None:
    dossier = make_fixture_dossier()
    page_id = dossier.topic.page_id
    pinned_rev_id = seed_pin_of(dossier).rev_id
    latest_rev_id = pinned_rev_id + 1
    await redis_client.set(keys.latest_rev(page_id), str(latest_rev_id))
    await redis_client.zadd(
        keys.pageedits(page_id),
        {str(latest_rev_id): (dossier.build.built_at + timedelta(minutes=1)).timestamp()},
    )

    item = await _list_item(redis_client, dossier)

    assert item.freshness_state == "stale"
    assert item.edits_since_pin == 1


async def test_edits_since_pin_counts_watcher_edits_even_without_a_latest_pointer(
    redis_client: RedisClient,
) -> None:
    dossier = make_fixture_dossier()
    await redis_client.zadd(
        keys.pageedits(dossier.topic.page_id),
        {"1": (dossier.build.built_at + timedelta(minutes=1)).timestamp()},
    )

    item = await _list_item(redis_client, dossier)

    assert item.freshness_state == "unknown"
    assert item.edits_since_pin == 1
