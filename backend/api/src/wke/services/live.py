"""The live feed of recent edits and counters."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from wke.core import keys
from wke.core.models import EditEvent, LiveCounters, LiveResponse
from wke.services.base import ServiceBase

LIVE_LAST_HOUR_MINUTES = 60
STREAM_CONNECTED_AGE_SECONDS = 90
STREAM_RECONNECTING_AGE_SECONDS = 600
LIVE_MAX_EDITS = 50


def stream_state(
    now: datetime, last_event_at: datetime | None
) -> Literal["connected", "reconnecting", "down"]:
    """Classify the Recent Changes stream by the age of its newest event.

    Args:
        now: the request time.
        last_event_at: timestamp of the newest edit in the ring, or None.

    Returns:
        Literal["connected", "reconnecting", "down"]: the stream state of that age.
    """
    if last_event_at is None:
        return "down"
    age = (now - last_event_at).total_seconds()
    if age <= STREAM_CONNECTED_AGE_SECONDS:
        return "connected"
    if age <= STREAM_RECONNECTING_AGE_SECONDS:
        return "reconnecting"
    return "down"


class LiveMixin(ServiceBase):
    """The live feed of recent edits and counters."""

    async def get_live(self, since: int) -> LiveResponse:
        """Read recent tracked-page edits and live counters.

        Args:
            since: cursor from a previous response; only edits with a
                strictly greater cursor are returned.

        Returns:
            LiveResponse: up to 50 newest tracked-page edits after
            since, the current cursor, and rolling counters.
        """
        now = datetime.now(UTC)
        all_edits = await self._read_edit_ring()
        edits = [event for event in all_edits if event.cursor > since][:LIVE_MAX_EDITS]

        seq_raw = await self._redis.get(keys.EDITS_SEQ)
        cursor = int(seq_raw) if seq_raw else (all_edits[0].cursor if all_edits else 0)

        last_event_at = all_edits[0].ts if all_edits else None
        counters = await self._live_counters(now)
        return LiveResponse(
            stream=stream_state(now, last_event_at),
            server_time=now,
            cursor=cursor,
            last_event_at=last_event_at,
            edits=edits,
            counters=counters,
        )

    async def _read_edit_ring(self) -> list[EditEvent]:
        """Read the edit ring, newest first, skipping unreadable entries.

        Returns:
            list[EditEvent]: the valid events in ring order.
        """
        raw_ring = await self._redis.lrange(keys.EDITS_RING, 0, keys.EDITS_RING_MAX_LENGTH - 1)
        events: list[EditEvent] = []
        for raw_event in raw_ring:
            try:
                events.append(EditEvent.model_validate_json(raw_event))
            except ValueError:
                continue
        return events

    async def _sum_edit_counters(self, now: datetime) -> tuple[int, int, int]:
        """Sum the per-minute edit counters over the last hour.

        Args:
            now: the request time.

        Returns:
            tuple[int, int, int]: enwiki edits, tracked edits and the number
            of minute buckets that exist.
        """
        buckets = [
            keys.minute_bucket(now.timestamp() - minutes_ago * 60)
            for minutes_ago in range(LIVE_LAST_HOUR_MINUTES)
        ]
        counter_keys = [keys.rc_counter(keys.ENWIKI_RC_KIND, b) for b in buckets]
        counter_keys += [keys.rc_counter(keys.TRACKED_RC_KIND, b) for b in buckets]
        values = await self._redis.mget(counter_keys)
        enwiki_values = values[: len(buckets)]
        tracked_values = values[len(buckets) :]
        enwiki_total = tracked_total = buckets_found = 0
        for enwiki_raw, tracked_raw in zip(enwiki_values, tracked_values, strict=True):
            if enwiki_raw is not None:
                enwiki_total += int(enwiki_raw)
                buckets_found += 1
            if tracked_raw is not None:
                tracked_total += int(tracked_raw)
        return enwiki_total, tracked_total, buckets_found

    async def _live_counters(self, now: datetime) -> LiveCounters:
        """Build the rolling counters for the live response.

        Args:
            now: the request time.

        Returns:
            LiveCounters: last-hour edit counts and today's build totals.
        """
        enwiki_total, tracked_total, buckets_found = await self._sum_edit_counters(now)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        dossiers_built_today = await self._redis.zcount(
            keys.BUILT, f"{today_start.timestamp()}", "+inf"
        )
        tracked_members = await self._redis.smembers(keys.TRACKED)
        return LiveCounters(
            enwiki_edits_last_hour=enwiki_total,
            tracked_edits_last_hour=tracked_total,
            window_complete=buckets_found >= LIVE_LAST_HOUR_MINUTES,
            window_since=now - timedelta(minutes=LIVE_LAST_HOUR_MINUTES),
            dossiers_built_today=dossiers_built_today,
            topics_tracked=len(tracked_members),
        )
