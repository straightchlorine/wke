"""The rating loop: rates the prose passages of stored dossiers through wke-ml, a call each."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from wke.clients.ml import MLClient, MLUnavailable
from wke.clients.redis import RedisClient
from wke.core import keys
from wke.core.dossiers import pointer_rev_id
from wke.core.models import Dossier
from wke.jobs.build.constants import (
    RATING_CALL_ATTEMPTS,
    RATING_MODEL,
    RATING_MODEL_FILE,
    RATING_PROMPT_SHA256,
    RATING_RETRY_PAUSE_SECONDS,
)
from wke.jobs.build.rating import (
    RatingConfig,
    RatingDocument,
    parse_document,
    rating_key,
    rating_lock_key,
)
from wke.jobs.build.stages import lead_text
from wke.metrics import RATING_STAGE_TOTAL

logger = logging.getLogger(__name__)

NEXT_ITEM_TIMEOUT_SECONDS = 1.0
HEARTBEAT_INTERVAL_SECONDS = 5.0
REAP_INTERVAL_SECONDS = 30.0
# The pause after a Redis call of the loop failed, and how many heartbeat writes in a row may
# fail (the claim lives JOB_HEARTBEAT_TTL_SECONDS, far longer) before the item is given back.
REDIS_ERROR_PAUSE_SECONDS = 1.0
HEARTBEAT_FAILURES_ALLOWED = 3
# Outcomes that are retried later; every other end of a stage is final.
_RETRIED = ("ml_unavailable", "deadline")


class _StageEnd(Exception):
    """The attempt stops with this outcome; the stored passages stay."""

    def __init__(self, outcome: str) -> None:
        super().__init__(outcome)
        self.outcome = outcome


class _ClaimLost(Exception):
    """The claim on the item could not be set or kept; the item goes back on the queue."""


class _HeartbeatLost(_ClaimLost):
    """The heartbeat of a claim failed too often; the item is retried after a backoff."""


@dataclass
class _Attempt:
    """What one attempt of a stage got done."""

    new_scores: int = 0


@dataclass(frozen=True)
class RatingItem:
    """A q:rate entry: "page:rev", or "page:rev:failures:due" for a retry that waits until due."""

    page_id: int
    rev_id: int
    failures: int = 0
    due: float = 0.0

    @classmethod
    def parse(cls, value: str) -> RatingItem:
        page, rev, *retry = value.split(":")
        if not retry:
            return cls(int(page), int(rev))
        return cls(int(page), int(rev), int(retry[0]), float(retry[1]))

    def encode(self) -> str:
        if not self.due:
            return f"{self.page_id}:{self.rev_id}"
        return f"{self.page_id}:{self.rev_id}:{self.failures}:{self.due:.3f}"


class Rater:
    """Takes "page_id:rev_id" items off q:rate and rates that dossier's prose passages.

    Several instances may run (a rollout): the one that takes an item claims its revision with a
    heartbeat, as the build worker does for a job; another that meets the same revision skips it,
    and an item whose heartbeat is gone is put back on the queue.
    """

    def __init__(
        self,
        redis: RedisClient,
        ml: MLClient,
        config: RatingConfig,
        pipeline_version: str,
        heartbeat_sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._heartbeat_sleep = heartbeat_sleep
        self._redis = redis
        self._ml = ml
        self.config = config
        self._pipeline_version = pipeline_version

    async def run_forever(self) -> None:
        """Put stalled items back, then take items one at a time until cancelled.

        Raises:
            asyncio.CancelledError: when stopped; the item in flight goes back to the front of
                the queue.
        """
        await self._reap()
        last_reap = time.monotonic()
        while True:
            if time.monotonic() - last_reap >= REAP_INTERVAL_SECONDS:
                await self._reap()
                last_reap = time.monotonic()
            value = await self._next_item()
            if value is None:
                continue
            pause = 0.0
            try:
                pause = await self._rate_item(value)
            except asyncio.CancelledError:
                await self._give_back(value)
                raise
            except _HeartbeatLost:
                await self._retry_later(value)
                await asyncio.sleep(REDIS_ERROR_PAUSE_SECONDS)
                continue
            except _ClaimLost:
                await self._give_back(value)
                await asyncio.sleep(REDIS_ERROR_PAUSE_SECONDS)
                continue
            except Exception:
                logger.exception("rating item failed: %s", value)
                await self._release_lock(value)
            await self._remove(value)
            await asyncio.sleep(pause)

    async def _next_item(self) -> str | None:
        try:
            return await self._redis.blmove(
                keys.QUEUE_RATE, keys.QUEUE_RATE_PROCESSING, NEXT_ITEM_TIMEOUT_SECONDS
            )
        except Exception:
            logger.exception("rating queue read failed")
            await asyncio.sleep(NEXT_ITEM_TIMEOUT_SECONDS)
            return None

    async def _reap(self) -> None:
        """Run the reap; a Redis error is logged and waited out, it never ends the loop."""
        try:
            await self._reap_stalled()
        except Exception:
            logger.exception("rating reap failed")
            await asyncio.sleep(REDIS_ERROR_PAUSE_SECONDS)

    async def _remove(self, value: str) -> None:
        """Take a finished item off q:rate:processing; if that fails the reap finds it later."""
        try:
            await self._redis.lrem(keys.QUEUE_RATE_PROCESSING, 1, value)
        except Exception:
            logger.exception("rating item could not be removed from processing: %s", value)
            await asyncio.sleep(REDIS_ERROR_PAUSE_SECONDS)

    async def _give_back(self, value: str) -> None:
        """Put the item first on the queue again; if that fails the reap finds it later."""
        try:
            await self._redis.lpush(keys.QUEUE_RATE, value)
            await self._redis.lrem(keys.QUEUE_RATE_PROCESSING, 1, value)
        except Exception:
            logger.exception("rating item could not be put back: %s", value)

    async def _retry_later(self, value: str) -> None:
        """Queue an item whose heartbeat failed again after the backoff of an unavailable wke-ml.

        If Redis fails here the item stays in processing and the reap finds it later.
        """
        try:
            item = RatingItem.parse(value)
            await self._retry(item, "heartbeat_lost", _Attempt())
            await self._redis.lrem(keys.QUEUE_RATE_PROCESSING, 1, value)
        except Exception:
            logger.exception("rating item could not be queued for a retry: %s", value)
            return
        await self._release_lock(value)

    async def _release_lock(self, value: str) -> None:
        """Release the build's rating lock of an item that failed unexpectedly."""
        try:
            item = RatingItem.parse(value)
            await self._redis.delete(
                rating_lock_key(item.page_id, item.rev_id, self._pipeline_version)
            )
        except ValueError:
            return
        except Exception:
            logger.exception("rating lock could not be released: %s", value)

    async def _reap_stalled(self) -> None:
        """Put the items of q:rate:processing whose heartbeat is gone back on the queue."""
        for value in await self._redis.lrange(keys.QUEUE_RATE_PROCESSING, 0, -1):
            try:
                item = RatingItem.parse(value)
            except ValueError:
                stalled = True
            else:
                stalled = not await self._redis.exists(
                    keys.rating_heartbeat(item.page_id, item.rev_id)
                )
            if stalled:
                await self._redis.lpush(keys.QUEUE_RATE, value)
                await self._redis.lrem(keys.QUEUE_RATE_PROCESSING, 1, value)
                logger.warning("requeued stalled rating item %s", value)

    async def _heartbeat(self, key: str) -> None:
        """Refresh the claim until cancelled; ends by itself when the claim cannot be kept.

        RedisClient.set answers False when Redis failed, so a False counts like a raised error.
        """
        failures = 0
        while True:
            await self._heartbeat_sleep(HEARTBEAT_INTERVAL_SECONDS)
            try:
                written = await self._redis.set(
                    key, datetime.now(UTC).isoformat(), ex=keys.JOB_HEARTBEAT_TTL_SECONDS
                )
            except Exception:
                logger.exception("rating heartbeat write failed")
                written = False
            failures = 0 if written else failures + 1
            if failures >= HEARTBEAT_FAILURES_ALLOWED:
                logger.error("rating heartbeat lost after %s failed writes", failures)
                return

    async def _rate_item(self, value: str) -> float:
        """Rate one item, or put a retry that is not due yet back at the tail.

        Returns:
            float: seconds the loop waits before it takes the next item.
        """
        item = RatingItem.parse(value)
        if item.due > time.time():
            await self._redis.rpush(keys.QUEUE_RATE, value)
            return min(item.due - time.time(), NEXT_ITEM_TIMEOUT_SECONDS)
        started = time.monotonic()
        heartbeat = keys.rating_heartbeat(item.page_id, item.rev_id)
        try:
            claimed = await self._redis.set(
                heartbeat,
                datetime.now(UTC).isoformat(),
                ex=keys.JOB_HEARTBEAT_TTL_SECONDS,
                nx=True,
            )
        except Exception as exc:
            logger.exception("rating claim could not be written: %s", item.encode())
            raise _ClaimLost from exc
        if not claimed:
            self._finish(item, "claimed", 0, started)
            return 0.0
        beat = asyncio.create_task(self._heartbeat(heartbeat))
        work = asyncio.create_task(self._rate_claimed(item, started))
        try:
            await asyncio.wait({beat, work}, return_when=asyncio.FIRST_COMPLETED)
            if not work.done():
                # The heartbeat ended first: no claim, so no rating.
                raise _HeartbeatLost
            work.result()
        finally:
            beat.cancel()
            work.cancel()
            await asyncio.gather(beat, work, return_exceptions=True)
            try:
                await self._redis.delete(heartbeat)
            except Exception:
                logger.exception("rating claim could not be released: %s", item.encode())
        return 0.0

    async def _rate_claimed(self, item: RatingItem, started: float) -> None:
        attempt = _Attempt()
        passages = 0
        outcome = "done"
        if not await self._is_current(item):
            outcome = "superseded"
        else:
            raw = await self._redis.get(
                keys.dossier(item.page_id, item.rev_id, self._pipeline_version)
            )
            if raw is None:
                outcome = "dossier_gone"
            else:
                dossier = Dossier.model_validate_json(raw)
                passages = sum(1 for c in dossier.chunks if c.kind == "prose")
                try:
                    async with asyncio.timeout(self.config.deadline_seconds):
                        await self._rate_dossier(dossier, item, attempt)
                except _StageEnd as end:
                    outcome = end.outcome
                except TimeoutError:
                    outcome = "deadline"
        self._finish(item, outcome, passages, started)
        if outcome != "done":
            await self._redis.delete(
                rating_lock_key(item.page_id, item.rev_id, self._pipeline_version)
            )
        if outcome in _RETRIED:
            await self._retry(item, outcome, attempt)

    async def _is_current(self, item: RatingItem) -> bool:
        """Tell whether the revision is still the one the page's pointer names.

        Returns:
            bool: False only when a readable pointer names another revision.
        """
        raw = await self._redis.get(keys.ptr(item.page_id))
        current = pointer_rev_id(raw) if raw is not None else None
        return current is None or current == item.rev_id

    async def _retry(self, item: RatingItem, outcome: str, attempt: _Attempt) -> None:
        """Queue the stage again after a backoff, unless attempts without progress ran out.

        A stage that stored a new score starts counting its failures over, so a long article cut
        off by the deadline keeps resuming until it is done.
        """
        failures = 0 if attempt.new_scores else item.failures + 1
        if failures >= self.config.max_attempts:
            logger.warning(
                "rating given up page_id=%s rev_id=%s after %s attempts: %s",
                item.page_id,
                item.rev_id,
                failures,
                outcome,
            )
            return
        delay = self.config.retry_backoff_seconds * 2 ** max(failures - 1, 0)
        retry = RatingItem(item.page_id, item.rev_id, failures, time.time() + delay)
        await self._redis.rpush(keys.QUEUE_RATE, retry.encode())

    def _finish(self, item: RatingItem, outcome: str, passages: int, started: float) -> None:
        RATING_STAGE_TOTAL.labels(outcome=outcome).inc()
        logger.info(
            "rating_stage page_id=%s rev_id=%s passages=%s seconds=%.1f outcome=%s",
            item.page_id,
            item.rev_id,
            passages,
            time.monotonic() - started,
            outcome,
        )

    async def _rate_dossier(self, dossier: Dossier, item: RatingItem, attempt: _Attempt) -> None:
        prose = [c for c in dossier.chunks if c.kind == "prose"]
        key = rating_key(item.page_id, item.rev_id, self._pipeline_version)
        stored = parse_document(await self._redis.get(key))
        wanted = {c.id for c in prose}
        scores = {i: s for i, s in (stored.scores if stored else {}).items() if i in wanted}
        lead = lead_text(prose)
        for chunk in prose:
            if chunk.id in scores:
                continue
            scores[chunk.id] = await self._rate_passage(
                dossier.topic.title, lead, chunk.id, chunk.text.strip()
            )
            if not await self._store(key, scores, done=False):
                return
            attempt.new_scores += 1
        await self._store(key, scores, done=True)

    async def _store(self, key: str, scores: dict[str, float | None], done: bool) -> bool:
        """Write the document; a partial one never replaces a finished one.

        A second attempt on the same revision (a lock that expired, another replica) holds an
        older copy of the scores; once the first has finished, the second stops instead of
        writing it back.

        Returns:
            bool: False when a finished document was already stored and nothing was written.
        """
        if not done:
            current = parse_document(await self._redis.get(key))
            if current is not None and current.done:
                return False
        document = RatingDocument(
            prompt_sha256=RATING_PROMPT_SHA256, model=RATING_MODEL, done=done, scores=scores
        )
        await self._redis.set(key, document.model_dump_json(), ex=keys.DOSSIER_TTL_SECONDS)
        return True

    async def _rate_passage(self, title: str, lead: str, chunk_id: str, text: str) -> float | None:
        """Rate one passage, retrying a failed call; a 422 (prompt too long) scores None.

        Raises:
            _StageEnd: wke-ml stayed unavailable, or answered under another prompt or model.
        """
        for attempt in range(RATING_CALL_ATTEMPTS):
            if attempt:
                await asyncio.sleep(RATING_RETRY_PAUSE_SECONDS)
            try:
                reply = await self._ml.rate(
                    title,
                    lead,
                    [{"id": chunk_id, "text": text}],
                    deadline_ms=self.config.call_timeout_seconds * 1000,
                )
            except MLUnavailable as exc:
                if exc.reason == "http_422":
                    return None
                logger.warning("rating call failed for %s: %s", chunk_id, exc.reason)
                continue
            if (
                reply.get("prompt_sha256") != RATING_PROMPT_SHA256
                or reply.get("model") != RATING_MODEL_FILE
            ):
                raise _StageEnd("mismatch")
            score = (reply.get("scores") or {}).get(chunk_id)
            return float(score) if score is not None else None
        raise _StageEnd("ml_unavailable")
