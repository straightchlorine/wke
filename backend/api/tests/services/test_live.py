"""The live feed: stream state by age, the edit ring and the cursor."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, tzinfo

import pytest

from tests.support.services import make_service
from wke.clients.redis import RedisClient
from wke.core import keys
from wke.core.models import EditEvent
from wke.services.live import LIVE_LAST_HOUR_MINUTES, LIVE_MAX_EDITS, stream_state

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("age_seconds", "expected"),
    [
        (None, "down"),
        (0, "connected"),
        (90, "connected"),
        (91, "reconnecting"),
        (600, "reconnecting"),
        (601, "down"),
    ],
)
def teststream_state_by_age_of_newest_event(age_seconds: int | None, expected: str) -> None:
    last_event_at = None if age_seconds is None else NOW - timedelta(seconds=age_seconds)

    assert stream_state(NOW, last_event_at) == expected


async def _push_edits(redis_client: RedisClient, count: int) -> None:
    """Fill the ring as the watcher does: newest first, cursor equal to the sequence."""
    for cursor in range(1, count + 1):
        event = EditEvent(
            cursor=cursor,
            title=f"Page {cursor}",
            rev_new=cursor,
            ts=datetime.now(UTC),
            user_kind="registered",
        )
        await redis_client.lpush(keys.EDITS_RING, event.model_dump_json())
    await redis_client.set(keys.EDITS_SEQ, str(count))


async def test_edits_after_since_are_newest_first_and_capped(redis_client: RedisClient) -> None:
    await _push_edits(redis_client, LIVE_MAX_EDITS + 10)
    service = make_service(redis_client)

    everything = await service.get_live(0)
    recent = await service.get_live(LIVE_MAX_EDITS + 7)

    assert [e.cursor for e in everything.edits] == list(range(LIVE_MAX_EDITS + 10, 10, -1))
    assert everything.cursor == LIVE_MAX_EDITS + 10
    assert [e.cursor for e in recent.edits] == [LIVE_MAX_EDITS + 10 - n for n in range(3)]
    assert everything.stream == "connected"


async def test_unreadable_ring_entries_are_skipped_and_the_cursor_falls_back(
    redis_client: RedisClient,
) -> None:
    await _push_edits(redis_client, 2)
    await redis_client.delete(keys.EDITS_SEQ)
    await redis_client.lpush(keys.EDITS_RING, "not an event")
    service = make_service(redis_client)

    live = await service.get_live(0)

    assert [e.cursor for e in live.edits] == [2, 1]
    assert live.cursor == 2


async def test_empty_ring_is_down_with_cursor_zero(redis_client: RedisClient) -> None:
    live = await make_service(redis_client).get_live(0)

    assert (live.stream, live.cursor, live.last_event_at, live.edits) == ("down", 0, None, [])


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz: tzinfo | None = None) -> datetime:
        return NOW


async def test_counters_cover_the_last_hour_and_the_day_so_far(
    redis_client: RedisClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("wke.services.live.datetime", _FrozenDatetime)
    for minutes_ago in range(LIVE_LAST_HOUR_MINUTES):
        bucket = keys.minute_bucket(NOW.timestamp() - minutes_ago * 60)
        await redis_client.set(keys.rc_counter(keys.ENWIKI_RC_KIND, bucket), "1")
    midnight = NOW.replace(hour=0, minute=0).timestamp()
    await redis_client.zadd(keys.BUILT, {"1": midnight - 1, "2": midnight, "3": NOW.timestamp()})
    await redis_client.sadd(keys.TRACKED, "a", "b")
    service = make_service(redis_client)

    full = (await service.get_live(0)).counters
    await redis_client.delete(
        keys.rc_counter(keys.ENWIKI_RC_KIND, keys.minute_bucket(NOW.timestamp() - 59 * 60))
    )
    missing_oldest = (await service.get_live(0)).counters

    assert (full.enwiki_edits_last_hour, full.window_complete) == (60, True)
    assert (missing_oldest.enwiki_edits_last_hour, missing_oldest.window_complete) == (59, False)
    assert full.dossiers_built_today == 2
    assert full.topics_tracked == 2
    assert full.window_since == NOW - timedelta(minutes=60)
