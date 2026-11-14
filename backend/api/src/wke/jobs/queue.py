"""Job admission and the five-list Redis queue."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable
from typing import Literal

from redis.exceptions import RedisError

from wke.clients.redis import RedisClient
from wke.core import keys
from wke.core.errors import ApiException
from wke.core.models import Job
from wke.jobs.job_record import make_job_id, new_queued_job

logger = logging.getLogger(__name__)

BLMOVE_POLL_SECONDS = 0.2
JOBKEY_WINNER_POLL_INTERVAL_SECONDS = 0.05
JOBKEY_WINNER_POLL_ATTEMPTS = 20
NEXT_ITEM_BACKOFF_INITIAL_SECONDS = 0.5
NEXT_ITEM_BACKOFF_MAX_SECONDS = 10.0
JOBKEY_RECLAIM_TTL_SECONDS = 10
JOBKEY_RECLAIM_POLL_INTERVAL_SECONDS = 0.05
JOBKEY_RECLAIM_POLL_ATTEMPTS = 20


class JobQueue:
    """Admission, status storage and priority dequeue for build jobs."""

    def __init__(
        self,
        redis: RedisClient,
        pipeline_version: str,
        queue_cap: int,
        background_queue_cap: int | None = None,
    ) -> None:
        self._redis = redis
        self._pipeline_version = pipeline_version
        self._queue_cap = queue_cap
        # Defaults to queue_cap for callers (mostly tests) that only pass
        # one cap; production wiring passes settings.background_queue_cap.
        self._background_queue_cap = (
            background_queue_cap if background_queue_cap is not None else queue_cap
        )
        # Backoff state for next_item's Redis-outage handling, persisted across
        # calls so a sustained outage does not reset to a hot spin every
        # NEXT_ITEM_TIMEOUT_SECONDS.
        self._next_item_backoff_seconds = NEXT_ITEM_BACKOFF_INITIAL_SECONDS

    async def admit(
        self,
        page_id: int,
        rev_id: int,
        title: str,
        background: bool = False,
        force: bool = False,
        gate: Callable[[], None] | None = None,
    ) -> Job | Literal["ready"]:
        """Admit a build: reuse a ready dossier, an in-flight job, or enqueue.

        Args:
            page_id: Wikipedia page id.
            rev_id: pinned revision id.
            title: normalized article title, stored on the Job for display.
            background: True to enqueue on q:background instead of
                q:interactive (prebuilds, rebuilds).
            force: True to enqueue a rebuild even though a dossier already
                exists for this (page_id, rev_id) -- POST refresh=true.
                The existing dossier is left in place (stale-while-
                revalidate) and overwritten only once the rebuild
                finalizes; single-flight dedup via jobkey still applies,
                so concurrent refreshes admit at most one rebuild.
            gate: called once, only when the request would join or start
                a build (never for a "ready" result), before any jobkey or
                queue write. It may raise to refuse the admission, e.g.
                the per-IP build limit, so a refused request queues nothing.

        Returns:
            Job | "ready": "ready" when a dossier already exists for this
            (page_id, rev_id, pipeline_version) and force is False;
            otherwise the Job, new or already in flight.

        Raises:
            ApiException: 503 queue_full when the combined depth of
                q:interactive and q:background is already at the cap, or
                whatever `gate` raises.
        """
        dossier_key = keys.dossier(page_id, rev_id, self._pipeline_version)
        dossier_exists = await self._redis.exists(dossier_key)
        if not force and dossier_exists:
            return "ready"
        if gate is not None:
            gate()

        job_id = make_job_id(page_id, rev_id, self._pipeline_version)
        jobkey = keys.jobkey(page_id, rev_id)
        acquired = await self._redis.set(jobkey, job_id, ex=keys.JOBKEY_TTL_SECONDS, nx=True)
        if not acquired:
            contended = await self._resolve_contended_jobkey(
                job_id, page_id, rev_id, dossier_exists
            )
            if contended is not None:
                return contended

        depth = await self.queue_depth()
        await self._ensure_queue_capacity(background, jobkey)
        job = new_queued_job(job_id, page_id, rev_id, title, depth)
        await self.set_job(job)
        queue_name = keys.QUEUE_BACKGROUND if background else keys.QUEUE_INTERACTIVE

        # RPUSH (tail), BLMOVE pops LEFT (head):
        # first admitted, first served.
        # LPUSH here makes every queue LIFO and turn queue_position into a number
        # not reflecting serve order.
        await self._redis.rpush(queue_name, job_id)
        logger.info(
            "job_admitted job_id=%s page_id=%s rev_id=%s background=%s",
            job.id,
            page_id,
            rev_id,
            background,
        )
        return job

    async def _resolve_contended_jobkey(
        self, job_id: str, page_id: int, rev_id: int, dossier_exists: bool
    ) -> Job | None:
        """Settle an admission that lost the jobkey race.

        Args:
            job_id: the deterministic job id for this page/revision.
            page_id: Wikipedia page id.
            rev_id: pinned revision id.
            dossier_exists: whether a dossier is already stored.

        Returns:
            Job | None: the in-flight job to hand back, or None when the
            caller has reclaimed the jobkey (or the holder vanished) and
            should enqueue its own build.
        """
        # The winner may still be between its SET NX and its first set_job();
        # polling briefly then for job:{id} rather than returning None and
        # falling through to a duplicate RPUSH.
        existing = await self._poll_for_job(job_id)

        # A job already at status done/failed with no dossier behind it is
        # stale (e.g. a structural build whose short-TTL dossier already expired),
        # not a real in-flight build.
        # With a dossier present, done/failed means a previous refresh already
        # finished; that is not stale, so it is still returned rather than re-admitted.
        is_stale_done = existing is not None and existing.status in ("done", "failed")
        if existing is not None and not (is_stale_done and not dossier_exists):
            return existing

        # jobkey is held but job:{id} never appeared, or only a stale
        # done/failed job did: reclaim the jobkey so the job created by the
        # caller is the one and only build under it.
        # Every concurrent loser computes the same job_id, with no mutex each would
        # reclaim in turn and push a duplicate build.
        # Only the caller that wins jobkey_reclaim SET NX can reclaim, rest wait.
        reclaim_key = keys.jobkey_reclaim(page_id, rev_id)
        reclaimed = await self._redis.set(
            reclaim_key, job_id, ex=JOBKEY_RECLAIM_TTL_SECONDS, nx=True
        )
        if reclaimed:
            try:
                await self._redis.set(
                    keys.jobkey(page_id, rev_id), job_id, ex=keys.JOBKEY_TTL_SECONDS
                )
            finally:
                await self._redis.delete(reclaim_key)
            return None
        for _ in range(JOBKEY_RECLAIM_POLL_ATTEMPTS):
            if await self._redis.get(reclaim_key) is None:
                break
            await asyncio.sleep(JOBKEY_RECLAIM_POLL_INTERVAL_SECONDS)
        # None here means the winner crashed before writing job:{id}; the
        # caller still admits a build rather than returning nothing.
        return await self.get_job(job_id)

    async def _ensure_queue_capacity(self, background: bool, jobkey: str) -> None:
        """Refuse the admission when the target queue is at its cap.

        The cap is checked against only the queue this admission targets,
        each with its own limit: a full q:background (the nightly trending
        prebuild) must not reject real users' interactive POSTs, and vice
        versa.

        Args:
            background: True when the build targets q:background.
            jobkey: the single-flight key to release on refusal.

        Raises:
            ApiException: 503 queue_full when the target queue is full.
        """
        if background:
            own_queue_depth = await self._redis.llen(keys.QUEUE_BACKGROUND)
            own_cap = self._background_queue_cap
        else:
            own_queue_depth = await self._redis.llen(keys.QUEUE_INTERACTIVE)
            own_cap = self._queue_cap
        if own_queue_depth >= own_cap:
            await self._redis.delete(jobkey)
            raise ApiException(503, "queue_full", detail="Build queue is full.", retry_after=5)

    async def enqueue_summary_item(
        self, job_id: str, section_id: str, background: bool = False
    ) -> None:
        """Push one section summary item after the partial dossier is persisted.

        Args:
            job_id: the build job's id.
            section_id: the Section.id to summarize.
            background: True for q:sum:background, else q:sum:interactive.

        Returns:
            None.
        """
        queue_name = keys.QUEUE_SUM_BACKGROUND if background else keys.QUEUE_SUM_INTERACTIVE
        await self._redis.rpush(queue_name, f"{job_id}:{section_id}")

    async def get_job(self, job_id: str) -> Job | None:
        """Read a job's current status.

        Args:
            job_id: 16 hex char job id.

        Returns:
            Job | None: None if the job does not exist or has expired.
        """
        raw = await self._redis.get(keys.job(job_id))
        if raw is None:
            return None
        return Job.model_validate_json(raw)

    async def _poll_for_job(self, job_id: str) -> Job | None:
        """Poll briefly for a job the jobkey's winner is about to write.

        Args:
            job_id: 16 hex char job id.

        Returns:
            Job | None: the job once it appears, or None after the poll
            budget (~1s) is exhausted.
        """
        for _ in range(JOBKEY_WINNER_POLL_ATTEMPTS):
            job = await self.get_job(job_id)
            if job is not None:
                return job
            await asyncio.sleep(JOBKEY_WINNER_POLL_INTERVAL_SECONDS)
        return None

    async def set_job(self, job: Job) -> None:
        """Write a job's current status, refreshing its 1 h TTL.

        Args:
            job: the Job to persist.

        Returns:
            None.
        """
        record = job.model_dump(mode="json", exclude_none=True)
        if job.request_id is not None:
            record["request_id"] = job.request_id
        await self._redis.set(keys.job(job.id), json.dumps(record), ex=keys.JOB_TTL_SECONDS)

    async def next_item(self, timeout: float) -> tuple[str, str] | None:
        """Pop the next queue item in strict priority order.

        Polls `q:interactive`, `q:sum:interactive`, `q:background`,
        `q:sum:background` in that order with short BLMOVE calls onto
        `q:processing`, so a higher-priority item that arrives while a
        lower-priority BLMOVE is blocked is still served first.

        A Redis failure backs off with capped exponential delay (0.5 s up
        to 10 s, persisted across calls) instead of spinning through all
        four queues with no wait, which `RedisClient.blmove` would
        otherwise make indistinguishable from an empty queue.

        Args:
            timeout: total seconds to wait before returning None.

        Returns:
            tuple[str, str] | None: (queue_name, item) or None on timeout.
        """
        deadline = time.monotonic() + timeout
        while True:
            for queue_name in keys.QUEUE_PRIORITY_ORDER:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                try:
                    item = await self._redis.blmove(
                        queue_name, keys.QUEUE_PROCESSING, min(BLMOVE_POLL_SECONDS, remaining)
                    )
                except RedisError:
                    remaining = deadline - time.monotonic()
                    await asyncio.sleep(min(self._next_item_backoff_seconds, max(remaining, 0.0)))
                    self._next_item_backoff_seconds = min(
                        self._next_item_backoff_seconds * 2, NEXT_ITEM_BACKOFF_MAX_SECONDS
                    )
                    continue
                self._next_item_backoff_seconds = NEXT_ITEM_BACKOFF_INITIAL_SECONDS
                if item is not None:
                    return queue_name, item

    async def queue_depth(self) -> int:
        """Count the jobs waiting in q:interactive and q:background.

        Returns:
            int: the combined length of both queues.
        """
        interactive = await self._redis.llen(keys.QUEUE_INTERACTIVE)
        background = await self._redis.llen(keys.QUEUE_BACKGROUND)
        return interactive + background
