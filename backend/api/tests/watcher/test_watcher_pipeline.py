"""Watcher end to end: streaming transport -> filter -> Redis writes, reconnect, heartbeat."""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import httpx
import pytest

from tests.support.metrics import metric_sample
from wke.clients.redis import RedisClient
from wke.core import keys
from wke.core.titles import normalize_title
from wke.watcher import stream as stream_module
from wke.watcher.stream import RcEvent, Watcher, process_kept_event

FIXED_NOW = 1790595540.0
CHUNK_SIZE = 53


class _ChunkedStream(httpx.AsyncByteStream):
    def __init__(self, data: bytes, chunk_size: int) -> None:
        self._data = data
        self._chunk_size = chunk_size

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for start in range(0, len(self._data), self._chunk_size):
            yield self._data[start : start + self._chunk_size]


def _build_watcher(
    redis_client: RedisClient, sse_bytes: bytes, tmp_path: Path
) -> tuple[Watcher, list[dict[str, str]]]:
    sent_headers: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent_headers.append(dict(request.headers))
        return httpx.Response(200, stream=_ChunkedStream(sse_bytes, CHUNK_SIZE))

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    watcher = Watcher(
        http_client,
        redis_client,
        "https://stream.wikimedia.org/v2/stream/recentchange",
        "wke/test httpx/test",
        tmp_path / "heartbeat",
        clock=lambda: FIXED_NOW,
    )
    return watcher, sent_headers


async def test_run_once_stores_exactly_the_filtered_events(
    redis_client: RedisClient, sse_bytes: bytes, tmp_path: Path
) -> None:
    watcher, _ = _build_watcher(redis_client, sse_bytes, tmp_path)
    await watcher.run_once()

    ring = await redis_client.lrange(keys.EDITS_RING, 0, -1)
    assert len(ring) == 4
    stored_titles = {json.loads(entry)["title"] for entry in ring}
    assert stored_titles == {
        "List of elevator accidents",
        "Sandra Leiblum",
        "Climbing",
        "Volleyball at the 2026 Asian Games \u2013 Men's tournament",
    }


async def test_run_once_stores_the_user_kind_of_the_kept_edits(
    redis_client: RedisClient, sse_bytes: bytes, tmp_path: Path
) -> None:
    watcher, _ = _build_watcher(redis_client, sse_bytes, tmp_path)
    await watcher.run_once()

    ring = await redis_client.lrange(keys.EDITS_RING, 0, -1)
    kinds = sorted(json.loads(entry)["user_kind"] for entry in ring)
    # Three named editors and one temporary account (`~2026-...`).
    assert kinds == ["anonymous", "registered", "registered", "registered"]


async def test_run_once_never_stores_a_user_field(
    redis_client: RedisClient, sse_bytes: bytes, tmp_path: Path
) -> None:
    watcher, _ = _build_watcher(redis_client, sse_bytes, tmp_path)
    await watcher.run_once()

    ring = await redis_client.lrange(keys.EDITS_RING, 0, -1)
    for entry in ring:
        stored = json.loads(entry)
        assert "user" not in stored
        assert "comment" not in stored
        assert set(stored) <= {
            "cursor",
            "page_id",
            "title",
            "rev_new",
            "rev_old",
            "ts",
            "user_kind",
            "byte_delta",
            "diff_url",
        }


async def test_run_once_increments_enwiki_minute_counter(
    redis_client: RedisClient, sse_bytes: bytes, tmp_path: Path
) -> None:
    watcher, _ = _build_watcher(redis_client, sse_bytes, tmp_path)
    await watcher.run_once()

    bucket = keys.minute_bucket(FIXED_NOW)
    count = await redis_client.get(keys.rc_counter("enwiki", bucket))
    assert count == "4"
    ttl = await redis_client.ttl(keys.rc_counter("enwiki", bucket))
    assert 0 < ttl <= keys.RC_COUNTER_TTL_SECONDS


async def test_run_once_updates_tracked_page_pointers(
    redis_client: RedisClient, sse_bytes: bytes, tmp_path: Path
) -> None:
    title_key = normalize_title("Climbing")
    await redis_client.hset(keys.TRACKED_PAGE_IDS, title_key, "5041")
    await redis_client.sadd(keys.TRACKED, "5041")

    watcher, _ = _build_watcher(redis_client, sse_bytes, tmp_path)
    await watcher.run_once()

    latest = await redis_client.get(keys.latest_rev(5041))
    assert latest == "1377229292"
    ttl = await redis_client.ttl(keys.latest_rev(5041))
    assert keys.LATEST_REV_TTL_SECONDS - 60 < ttl <= keys.LATEST_REV_TTL_SECONDS
    assert await redis_client.zrevrange(keys.pageedits(5041), 0, -1) == ["1377229292"]
    assert await redis_client.zscore(keys.pageedits(5041), "1377229292") == FIXED_NOW
    bucket = keys.minute_bucket(FIXED_NOW)
    tracked_count = await redis_client.get(keys.rc_counter("tracked", bucket))
    assert tracked_count == "1"


async def test_run_once_skips_pointers_for_untracked_page(
    redis_client: RedisClient, sse_bytes: bytes, tmp_path: Path
) -> None:
    title_key = normalize_title("Climbing")
    await redis_client.hset(keys.TRACKED_PAGE_IDS, title_key, "5041")

    watcher, _ = _build_watcher(redis_client, sse_bytes, tmp_path)
    await watcher.run_once()

    assert await redis_client.get(keys.latest_rev(5041)) is None


async def test_run_once_sends_last_event_id_when_fresh(
    redis_client: RedisClient, sse_bytes: bytes, tmp_path: Path
) -> None:
    await redis_client.set(keys.WATCHER_LAST_ID, "some-cursor", ex=60)
    watcher, sent_headers = _build_watcher(redis_client, sse_bytes, tmp_path)
    await watcher.run_once()

    assert sent_headers[0].get("last-event-id") == "some-cursor"


async def test_run_once_omits_last_event_id_once_expired(
    redis_client: RedisClient, sse_bytes: bytes, tmp_path: Path
) -> None:
    watcher, sent_headers = _build_watcher(redis_client, sse_bytes, tmp_path)
    await watcher.run_once()

    assert "last-event-id" not in sent_headers[0]


async def test_run_once_sets_the_last_event_timestamp(
    redis_client: RedisClient, sse_bytes: bytes, tmp_path: Path
) -> None:
    watcher, _ = _build_watcher(redis_client, sse_bytes, tmp_path)
    await watcher.run_once()

    assert metric_sample("wke_watcher_last_event_timestamp", {}) == FIXED_NOW


async def test_run_once_saves_last_event_id_with_one_hour_ttl(
    redis_client: RedisClient, sse_bytes: bytes, tmp_path: Path
) -> None:
    watcher, _ = _build_watcher(redis_client, sse_bytes, tmp_path)
    await watcher.run_once()

    saved = await redis_client.get(keys.WATCHER_LAST_ID)
    assert saved is not None
    ttl = await redis_client.ttl(keys.WATCHER_LAST_ID)
    assert 0 < ttl <= 3600


async def test_run_once_raises_on_an_error_status(
    redis_client: RedisClient, tmp_path: Path
) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(503))
    watcher = Watcher(
        httpx.AsyncClient(transport=transport),
        redis_client,
        "https://stream.wikimedia.org/v2/stream/recentchange",
        "wke/test httpx/test",
        tmp_path / "heartbeat",
    )

    with pytest.raises(httpx.HTTPStatusError):
        await watcher.run_once()


def _edit(rev: int) -> RcEvent:
    return {"title": "Climbing", "timestamp": 1790595517, "revision": {"new": rev}}


async def test_process_kept_event_sets_the_counter_ttl_on_the_first_increment(
    redis_client: RedisClient,
) -> None:
    await process_kept_event(redis_client, _edit(1), now=FIXED_NOW)

    ttl = await redis_client.ttl(keys.rc_counter("enwiki", keys.minute_bucket(FIXED_NOW)))
    assert 0 < ttl <= keys.RC_COUNTER_TTL_SECONDS


async def test_process_kept_event_keeps_the_newest_edits_in_the_ring(
    redis_client: RedisClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(keys, "EDITS_RING_MAX_LENGTH", 3)
    for rev in range(1, 6):
        await process_kept_event(redis_client, _edit(rev), now=FIXED_NOW)

    ring = await redis_client.lrange(keys.EDITS_RING, 0, -1)
    stored = [json.loads(entry) for entry in ring]
    assert [(entry["cursor"], entry["rev_new"]) for entry in stored] == [(5, 5), (4, 4), (3, 3)]


async def test_process_kept_event_bounds_the_tracked_page_edit_history(
    redis_client: RedisClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(stream_module, "PAGEEDITS_MAX_MEMBERS", 2)
    await redis_client.hset(keys.TRACKED_PAGE_IDS, normalize_title("Climbing"), "5041")
    await redis_client.sadd(keys.TRACKED, "5041")
    for rev in range(1, 5):
        await process_kept_event(redis_client, _edit(rev), now=FIXED_NOW + rev)

    assert await redis_client.zrevrange(keys.pageedits(5041), 0, -1) == ["4", "3"]
    ttl = await redis_client.ttl(keys.pageedits(5041))
    assert 0 < ttl <= keys.PAGEEDITS_TTL_SECONDS


async def test_heartbeat_loop_writes_redis_key_with_ttl(
    redis_client: RedisClient, sse_bytes: bytes, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 0 so the loop ticks at least once during the short sleep below.
    monkeypatch.setattr(stream_module, "HEARTBEAT_INTERVAL_SECONDS", 0)
    watcher, _ = _build_watcher(redis_client, sse_bytes, tmp_path)

    task = asyncio.create_task(watcher.heartbeat_loop())
    try:
        await asyncio.sleep(0.05)
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    saved = await redis_client.get(keys.WATCHER_HEARTBEAT)
    assert saved == "2026-09-28T11:39:00+00:00"
    assert (tmp_path / "heartbeat").read_text() == str(FIXED_NOW)
    ttl = await redis_client.ttl(keys.WATCHER_HEARTBEAT)
    assert 0 < ttl <= keys.WATCHER_HEARTBEAT_TTL_SECONDS


def _ceiling(_low: float, high: float) -> float:
    return high


def _floor(low: float, _high: float) -> float:
    return low


async def _backoffs_until_cancelled(
    redis_client: RedisClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    outcomes: list[int | str],
    stop_after: int,
    draw: Callable[[float, float], float] = _ceiling,
) -> list[float]:
    """Run `run_forever` over scripted connection outcomes; return the backoff sleeps.

    Args:
        redis_client: the Redis the watcher writes to.
        tmp_path: directory for the heartbeat file.
        monkeypatch: pins the jitter draw.
        outcomes: per connection, an HTTP status or "error" for a connect failure;
            the last outcome repeats.
        stop_after: number of backoff sleeps after which the run is cancelled.
        draw: replaces `random.uniform`; the default picks the ceiling.

    Returns:
        list[float]: the backoff durations in order.
    """
    scripted = iter(outcomes)
    last: int | str = outcomes[-1]

    def handler(request: httpx.Request) -> httpx.Response:
        outcome = next(scripted, last)
        if outcome == "error":
            raise httpx.ConnectError("down")
        assert isinstance(outcome, int)
        return httpx.Response(outcome)

    backoffs: list[float] = []

    async def sleep(seconds: float) -> None:
        if seconds == stream_module.HEARTBEAT_INTERVAL_SECONDS:
            await asyncio.Event().wait()
        backoffs.append(seconds)
        if len(backoffs) == stop_after:
            raise asyncio.CancelledError

    monkeypatch.setattr(stream_module.random, "uniform", draw)
    watcher = Watcher(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        redis_client,
        "https://stream.wikimedia.org/v2/stream/recentchange",
        "wke/test httpx/test",
        tmp_path / "heartbeat",
        clock=lambda: FIXED_NOW,
        sleep=sleep,
    )
    with pytest.raises(asyncio.CancelledError):
        await watcher.run_forever()
    return backoffs


async def test_run_forever_resets_the_backoff_after_a_clean_stream(
    redis_client: RedisClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backoffs = await _backoffs_until_cancelled(
        redis_client, tmp_path, monkeypatch, [503, "error", 200, "error"], stop_after=4
    )

    assert backoffs == [2.0, 4.0, 2.0, 4.0]
    assert metric_sample("wke_watcher_connected", {}) == 0
    assert (tmp_path / "heartbeat").exists()


async def test_run_forever_caps_the_backoff(
    redis_client: RedisClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backoffs = await _backoffs_until_cancelled(
        redis_client, tmp_path, monkeypatch, ["error"], stop_after=8
    )

    assert backoffs == [2.0, 4.0, 8.0, 16.0, 32.0, 60.0, 60.0, 60.0]


async def test_run_forever_draws_the_backoff_from_the_minimum(
    redis_client: RedisClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backoffs = await _backoffs_until_cancelled(
        redis_client, tmp_path, monkeypatch, ["error"], stop_after=3, draw=_floor
    )

    assert backoffs == [stream_module.BACKOFF_MIN_SECONDS] * 3
