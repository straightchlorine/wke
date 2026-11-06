"""EventStreams recentchange consumer: SSE parsing, filtering, counters.

Reads the Wikimedia recentchange EventStream, keeps only English
Wikipedia mainspace human edits, updates per-minute rate counters,
appends every kept edit to a bounded ring buffer, and updates the
latest-revision pointer for pages in the tracked set. Never stores a
username or an edit comment.

The live recentchange schema (verified 2026-09-28 against a 200-event
recording, `tests/fixtures/wm/recentchange.sse`) carries no `page_id`
field, only `title`. Page identity for the tracked-page pointers is
therefore resolved through the durable `tracked_page_ids` hash
(written by the dossier build path whenever a page joins the tracked
set); a cache miss means the tracked-page bookkeeping is skipped for
that event, not fabricated -- see `resolve_tracked_page_id`.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import TypeAdapter, ValidationError

from wke.clients.redis import RedisClient
from wke.core import keys
from wke.core.errors import ApiException
from wke.core.models import EditEvent
from wke.core.titles import normalize_title
from wke.metrics import (
    WATCHER_CONNECTED,
    WATCHER_EVENTS_TOTAL,
    WATCHER_LAST_EVENT_TIMESTAMP,
)

logger = logging.getLogger(__name__)

UserKind = Literal["registered", "anonymous", "bot"]
RcEvent = dict[str, Any]
RC_EVENT_ADAPTER = TypeAdapter(RcEvent)

CANARY_DOMAIN = "canary"
ARTICLE_NAMESPACE = 0
TEMPORARY_ACCOUNT_PREFIX = "~"
EDIT_EVENT_TYPE = "edit"
ENWIKI_WIKI = "enwiki"
ENWIKI_SUBSTRING = f'"wiki":"{ENWIKI_WIKI}"'

ENWIKI_RC_KIND = "enwiki"
TRACKED_RC_KIND = "tracked"

PAGEEDITS_MAX_MEMBERS = 200
EDITS_RING_MAX_LENGTH = 500

LAST_ID_KEY = "watcher:last_id"
RESUME_MAX_AGE_SECONDS = 3600

HEARTBEAT_INTERVAL_SECONDS = 10.0
READ_TIMEOUT_SECONDS = 30.0
BACKOFF_MIN_SECONDS = 1.0
BACKOFF_MAX_SECONDS = 60.0


@dataclass(frozen=True)
class SSEEvent:
    """One dispatched Server-Sent Event."""

    id: str | None
    event: str
    data: str


class SSEParser:
    """Incremental Server-Sent Events line parser.

    Feeds raw bytes in arbitrary chunks, including chunks that split a
    line, a multi-line `data:` field, or an event boundary, and returns
    fully dispatched events as they complete. Comment lines (leading
    `:`) and unknown fields are ignored; multiple `data:` lines within
    one event are joined with `\\n`, per the SSE spec. The last-seen
    `id:` value persists across events until a new one is set.
    """

    def __init__(self) -> None:
        self._buffer = b""
        self._data_lines: list[str] = []
        self._event_type = "message"
        self._id: str | None = None

    def feed(self, chunk: bytes) -> list[SSEEvent]:
        """Feed a chunk of bytes and return any newly dispatched events.

        Args:
            chunk: raw bytes read from the stream, any length or split.

        Returns:
            list[SSEEvent]: zero or more events completed by this chunk.
        """
        self._buffer += chunk
        events: list[SSEEvent] = []
        while b"\n" in self._buffer:
            raw_line, self._buffer = self._buffer.split(b"\n", 1)
            if raw_line.endswith(b"\r"):
                raw_line = raw_line[:-1]
            dispatched = self._consume_line(raw_line.decode("utf-8", errors="replace"))
            if dispatched is not None:
                events.append(dispatched)
        return events

    def _consume_line(self, line: str) -> SSEEvent | None:
        if line == "":
            event_type = self._event_type
            self._event_type = "message"
            if not self._data_lines:
                return None
            data = "\n".join(self._data_lines)
            self._data_lines = []
            return SSEEvent(id=self._id, event=event_type, data=data)
        # A comment line (leading ":") has an empty field name and is ignored below.
        field_name, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if field_name == "data":
            self._data_lines.append(value)
        elif field_name == "event":
            self._event_type = value
        elif field_name == "id":
            self._id = value
        return None


def looks_like_enwiki(raw_data: str) -> bool:
    """Cheap pre-filter applied before any JSON parsing.

    Args:
        raw_data: the raw `data:` payload of one SSE event.

    Returns:
        bool: True if the substring every enwiki event carries is
        present. Rejects most non-enwiki events (measured ~94% of the
        stream) without parsing the JSON.
    """
    return ENWIKI_SUBSTRING in raw_data


def parse_kept_event(raw_data: str) -> RcEvent | None:
    """Parse and filter one SSE data payload, cheapest check first.

    Args:
        raw_data: the raw `data:` payload of one SSE event.

    Returns:
        RcEvent | None: the parsed event if it is an enwiki, mainspace,
        non-bot, non-canary `edit` event; otherwise None. Also
        increments `wke_watcher_events_total` by outcome.
    """
    if not looks_like_enwiki(raw_data):
        WATCHER_EVENTS_TOTAL.labels(kind="other_wiki").inc()
        return None
    try:
        event = RC_EVENT_ADAPTER.validate_json(raw_data)
    except ValidationError:
        WATCHER_EVENTS_TOTAL.labels(kind="unparseable").inc()
        return None
    meta: RcEvent = event.get("meta") or {}
    if meta.get("domain") == CANARY_DOMAIN:
        WATCHER_EVENTS_TOTAL.labels(kind="canary").inc()
        return None
    if event.get("wiki") != ENWIKI_WIKI:
        WATCHER_EVENTS_TOTAL.labels(kind="other_wiki").inc()
        return None
    if event.get("namespace") != ARTICLE_NAMESPACE:
        WATCHER_EVENTS_TOTAL.labels(kind="non_article_ns").inc()
        return None
    if event.get("type") != EDIT_EVENT_TYPE:
        WATCHER_EVENTS_TOTAL.labels(kind="non_edit_type").inc()
        return None
    if event.get("bot"):
        WATCHER_EVENTS_TOTAL.labels(kind="bot").inc()
        return None
    WATCHER_EVENTS_TOTAL.labels(kind="kept").inc()
    return event


def classify_user_kind(event: RcEvent) -> UserKind:
    """Classify the editor kind without ever returning the identity itself.

    Args:
        event: parsed recentchange event.

    Returns:
        UserKind: "bot", "anonymous" (an IP address or a Wikimedia temporary
        account, whose name starts with `~`), or "registered".
    """
    if event.get("bot"):
        return "bot"
    user = event.get("user")
    if isinstance(user, str):
        if user.startswith(TEMPORARY_ACCOUNT_PREFIX):
            return "anonymous"
        try:
            ipaddress.ip_address(user)
        except ValueError:
            return "registered"
        return "anonymous"
    return "registered"


def minute_bucket(epoch_seconds: float) -> str:
    """Build the UTC minute bucket used by `rc:*` counter keys.

    Args:
        epoch_seconds: unix timestamp.

    Returns:
        str: minute timestamp in `YYYYMMDDHHMM` format.
    """
    return datetime.fromtimestamp(epoch_seconds, tz=UTC).strftime("%Y%m%d%H%M")


async def resolve_tracked_page_id(redis: RedisClient, title: str) -> int | None:
    """Look up the cached page_id for a recentchange event's title.

    Args:
        redis: RedisClient.
        title: RC event `title` field (underscores for spaces).

    Returns:
        int | None: the page_id if `tracked_page_ids` has an entry for
        the title, else None. A miss is not retried against Wikimedia --
        the watcher never makes an outbound API call -- so the
        tracked-page pointers are simply skipped for that event.
    """
    try:
        title_key = normalize_title(title)
    except ApiException:
        return None
    cached = await redis.hget(keys.TRACKED_PAGE_IDS, title_key)
    if cached is None:
        return None
    try:
        return int(cached)
    except ValueError:
        return None


def build_edit_event(event: RcEvent, cursor: int, page_id: int | None) -> EditEvent:
    """Build an EditEvent from a filtered recentchange event.

    Args:
        event: parsed, filtered recentchange event (already passed
            through `parse_kept_event`).
        cursor: sequence number for this event, from `edits:seq`.
        page_id: resolved page_id, or None if unresolved.

    Returns:
        EditEvent: never carries a username or a comment.
    """
    revision: RcEvent = event.get("revision") or {}
    length: RcEvent = event.get("length") or {}
    rev_new: object = revision.get("new")
    rev_old: object = revision.get("old")
    byte_delta = None
    new_len: object = length.get("new")
    old_len: object = length.get("old")
    if isinstance(new_len, int) and isinstance(old_len, int):
        byte_delta = new_len - old_len
    ts_value = event.get("timestamp")
    ts = (
        datetime.fromtimestamp(ts_value, tz=UTC)
        if isinstance(ts_value, int | float)
        else datetime.now(UTC)
    )
    return EditEvent(
        cursor=cursor,
        page_id=page_id,
        title=str(event.get("title", "")),
        rev_new=rev_new if isinstance(rev_new, int) else 0,
        rev_old=rev_old if isinstance(rev_old, int) else None,
        ts=ts,
        user_kind=classify_user_kind(event),
        byte_delta=byte_delta,
    )


async def _incr_counter(redis: RedisClient, key: str, ttl_seconds: int) -> None:
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, ttl_seconds)


async def process_kept_event(
    redis: RedisClient, event: RcEvent, now: float | None = None
) -> EditEvent:
    """Apply every write a kept recentchange event triggers.

    Args:
        redis: RedisClient.
        event: parsed, filtered recentchange event.
        now: unix timestamp to use for the minute bucket and pageedits
            score; defaults to `time.time()`.

    Returns:
        EditEvent: the event as appended to the ring buffer.
    """
    now = time.time() if now is None else now
    minute = minute_bucket(now)
    await _incr_counter(redis, keys.rc_counter(ENWIKI_RC_KIND, minute), keys.RC_COUNTER_TTL_SECONDS)

    seq = await redis.incr(keys.EDITS_SEQ)
    page_id = await resolve_tracked_page_id(redis, str(event.get("title", "")))
    edit_event = build_edit_event(event, cursor=seq or 0, page_id=page_id)

    await redis.lpush(keys.EDITS_RING, edit_event.model_dump_json())
    await redis.ltrim(keys.EDITS_RING, 0, EDITS_RING_MAX_LENGTH - 1)

    if page_id is not None and await redis.sismember(keys.TRACKED, str(page_id)):
        pageedits_key = keys.pageedits(page_id)
        await redis.set(
            keys.latest_rev(page_id), str(edit_event.rev_new), ex=keys.LATEST_REV_TTL_SECONDS
        )
        await redis.zadd(pageedits_key, {str(edit_event.rev_new): now})
        await redis.expire(pageedits_key, keys.PAGEEDITS_TTL_SECONDS)
        await redis.zremrangebyrank(pageedits_key, 0, -(PAGEEDITS_MAX_MEMBERS + 1))
        await _incr_counter(
            redis, keys.rc_counter(TRACKED_RC_KIND, minute), keys.RC_COUNTER_TTL_SECONDS
        )

    WATCHER_LAST_EVENT_TIMESTAMP.set(now)
    return edit_event


class Watcher:
    """Long-lived recentchange SSE consumer with reconnect and resume."""

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        redis: RedisClient,
        stream_url: str,
        user_agent: str,
        heartbeat_path: Path,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._http = http_client
        self._redis = redis
        self._stream_url = stream_url
        self._headers = {"Accept": "text/event-stream", "User-Agent": user_agent}
        self._heartbeat_path = heartbeat_path
        self._clock = clock
        self._sleep = sleep

    async def run_forever(self) -> None:
        """Stream, filter and record recentchange events until cancelled.

        Reconnects with full-jitter backoff on connection errors.
        """
        heartbeat_task = asyncio.create_task(self.heartbeat_loop())
        attempt = 0
        try:
            while True:
                try:
                    await self.run_once()
                    attempt = 0
                except (httpx.HTTPError, OSError) as exc:
                    logger.warning("watcher stream error: %s", exc.__class__.__name__)
                WATCHER_CONNECTED.set(0)
                attempt += 1
                ceiling = min(BACKOFF_MAX_SECONDS, BACKOFF_MIN_SECONDS * (2**attempt))
                await self._sleep(random.uniform(BACKOFF_MIN_SECONDS, ceiling))
        finally:
            heartbeat_task.cancel()

    async def heartbeat_loop(self) -> None:
        """Write the liveness file and the Redis heartbeat key forever.

        The file backs the pod's own liveness probe; the Redis key lets
        GET /api/v1/status, running in a different pod, tell whether the
        watcher is alive.
        """
        while True:
            now = self._clock()
            self._heartbeat_path.write_text(str(now))
            await self._redis.set(
                keys.WATCHER_HEARTBEAT,
                datetime.fromtimestamp(now, tz=UTC).isoformat(),
                ex=keys.WATCHER_HEARTBEAT_TTL_SECONDS,
            )
            await self._sleep(HEARTBEAT_INTERVAL_SECONDS)

    async def run_once(self) -> None:
        """Hold one SSE connection open and handle its events until it ends.

        Raises:
            httpx.HTTPError: on a connection failure or a non-2xx response.
        """
        headers = dict(self._headers)
        last_id = await self._redis.get(LAST_ID_KEY)
        if last_id is not None:
            headers["Last-Event-ID"] = last_id
        parser = SSEParser()
        timeout = httpx.Timeout(READ_TIMEOUT_SECONDS)
        async with self._http.stream(
            "GET", self._stream_url, headers=headers, timeout=timeout
        ) as response:
            response.raise_for_status()
            WATCHER_CONNECTED.set(1)
            async for chunk in response.aiter_bytes():
                for sse_event in parser.feed(chunk):
                    await self._handle_sse_event(sse_event)

    async def _handle_sse_event(self, sse_event: SSEEvent) -> None:
        if sse_event.id is not None:
            await self._redis.set(LAST_ID_KEY, sse_event.id, ex=RESUME_MAX_AGE_SECONDS)
        parsed = parse_kept_event(sse_event.data)
        if parsed is None:
            return
        await process_kept_event(self._redis, parsed, now=self._clock())
