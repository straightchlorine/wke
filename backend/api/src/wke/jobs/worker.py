"""Job worker loop: priority dequeue, heartbeat, stall reaping, SIGTERM requeue."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime

from wke.clients.ml import MLClient
from wke.clients.redis import RedisClient
from wke.clients.wikimedia import WikimediaClient
from wke.core import keys
from wke.jobs.build.run import run_build
from wke.jobs.build.summarize import run_summary_item
from wke.jobs.queue import JobQueue
from wke.logging_setup import job_id_var, request_id_var

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_SECONDS = 5.0
REAP_STALE_SECONDS = 90
NEXT_ITEM_TIMEOUT_SECONDS = 1.0


def _job_id_of(value: str) -> str:
    return value.split(":", 1)[0]


def _is_summary_item(value: str) -> bool:
    return ":" in value


class Worker:
    """Pops queue items in priority order and runs the pipeline for each."""

    def __init__(
        self,
        redis: RedisClient,
        job_queue: JobQueue,
        wikimedia: WikimediaClient,
        ml: MLClient,
        pipeline_version: str,
        summary_sections: int,
        num_beams: int,
        wikipedia_api_url: str,
        public_host: str = "",
        public_scheme: str = "https",
    ) -> None:
        self._redis = redis
        self._job_queue = job_queue
        self._wikimedia = wikimedia
        self._ml = ml
        self._pipeline_version = pipeline_version
        self._summary_sections = summary_sections
        self._num_beams = num_beams
        self._wikipedia_api_url = wikipedia_api_url
        self._public_host = public_host
        self._public_scheme = public_scheme
        self._current: str | None = None

    async def run_forever(self) -> None:
        """Reap stalled items once at startup, then dequeue and process forever.

        Raises:
            asyncio.CancelledError: re-raised after requeuing the
                in-flight item, so callers (SIGTERM handling, lifespan
                shutdown) can await cancellation cleanly.
        """
        await self.reap_stalled()
        try:
            while True:
                await self._run_once()
        except asyncio.CancelledError:
            await self._requeue_current()
            raise

    async def _run_once(self) -> None:
        item = await self._job_queue.next_item(NEXT_ITEM_TIMEOUT_SECONDS)
        if item is None:
            return
        queue_name, value = item
        self._current = value
        job_token = job_id_var.set(_job_id_of(value))
        request_token = request_id_var.set(f"job-{_job_id_of(value)}")
        heartbeat_task = asyncio.create_task(self._heartbeat(value))
        cancelled = False
        try:
            request_id_var.set(await self._request_id_for(value))
            await self._process(queue_name, value)
        except asyncio.CancelledError:
            cancelled = True
            raise
        except Exception:
            logger.exception("worker item failed: %s %s", queue_name, value)
        finally:
            job_id_var.reset(job_token)
            request_id_var.reset(request_token)
            heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_task
            if not cancelled:
                await self._redis.lrem(keys.QUEUE_PROCESSING, 1, value)
                self._current = None

    async def _request_id_for(self, value: str) -> str:
        """Pick the request id bound to log lines and the wke-ml calls of one item.

        Args:
            value: a queue item, a job id or "job_id:section_id".

        Returns:
            str: the submitting request's id, or "job-<job_id>" (a valid
            X-Request-ID) when the job has none or no longer exists.
        """
        job_id = _job_id_of(value)
        job = await self._job_queue.get_job(job_id)
        if job is not None and job.request_id:
            return job.request_id
        return f"job-{job_id}"

    async def _process(self, queue_name: str, value: str) -> None:
        background = queue_name in (keys.QUEUE_BACKGROUND, keys.QUEUE_SUM_BACKGROUND)
        if queue_name in (keys.QUEUE_SUM_INTERACTIVE, keys.QUEUE_SUM_BACKGROUND):
            job_id, section_id = value.split(":", 1)
            await run_summary_item(
                job_id,
                section_id,
                redis=self._redis,
                job_queue=self._job_queue,
                ml=self._ml,
                pipeline_version=self._pipeline_version,
                num_beams=self._num_beams,
            )
        else:
            job = await self._job_queue.get_job(value)
            if job is None:
                logger.warning("build item %s has no job record; dropping", value)
                return
            await run_build(
                job,
                redis=self._redis,
                wikimedia=self._wikimedia,
                ml=self._ml,
                job_queue=self._job_queue,
                pipeline_version=self._pipeline_version,
                summary_sections=self._summary_sections,
                wikipedia_api_url=self._wikipedia_api_url,
                background=background,
                public_host=self._public_host,
                public_scheme=self._public_scheme,
            )

    async def _heartbeat(self, value: str) -> None:
        job_id = _job_id_of(value)
        hb_key = keys.job_heartbeat(job_id)
        while True:
            # Written first, then slept, so a job stuck in a single long
            # stage (no set_job of its own) still has a fresh heartbeat
            # from the moment it started processing.
            await self._redis.set(
                hb_key,
                datetime.now(UTC).isoformat(),
                ex=keys.JOB_HEARTBEAT_TTL_SECONDS,
            )
            await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)

    async def reap_stalled(self) -> None:
        """Requeue q:processing items whose job heartbeat is stale or missing."""
        items = await self._redis.lrange(keys.QUEUE_PROCESSING, 0, -1)
        for value in items:
            if await self._is_stale(value):
                await self._requeue(value)

    async def _is_stale(self, value: str) -> bool:
        job_id = _job_id_of(value)
        job = await self._job_queue.get_job(job_id)
        if job is None:
            return True
        reference = job.updated_at
        heartbeat_raw = await self._redis.get(keys.job_heartbeat(job_id))
        if heartbeat_raw is not None:
            heartbeat_at = datetime.fromisoformat(heartbeat_raw)
            reference = max(reference, heartbeat_at)
        age = (datetime.now(UTC) - reference).total_seconds()
        return age > REAP_STALE_SECONDS

    async def _requeue_current(self) -> None:
        if self._current is not None:
            await self._requeue(self._current)

    async def _requeue(self, value: str) -> None:
        await self._redis.lrem(keys.QUEUE_PROCESSING, 1, value)
        target = keys.QUEUE_SUM_BACKGROUND if _is_summary_item(value) else keys.QUEUE_BACKGROUND
        # LPUSH (head), not RPUSH: a requeued item was already in flight
        # once, so it runs next rather than going to the back of the
        # normal admission queue (which is RPUSH/FIFO -- see JobQueue.admit).
        await self._redis.lpush(target, value)
        logger.warning("requeued stalled item %s onto %s", value, target)
