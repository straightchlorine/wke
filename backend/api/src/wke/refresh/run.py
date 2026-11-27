"""Keeps stored dossiers alive and asks for rebuilds of the ones whose article changed.

A stored dossier expires 7 days after its build and a read does not extend it. For
every page in the `built` index this job reads the pointer and the dossier. A dossier
that expires soon gets its full lifetime back, stale or not, with nothing else changed,
so the page stays even when a rebuild is refused, deferred or fails. A dossier whose
article has a newer revision is in addition sent to `maybe_enqueue_rebuild`, which keeps
its own conditions and debounce. The job reads Redis only: no Wikipedia, no model.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

from pydantic import ValidationError
from redis.asyncio import Redis

from wke.clients.redis import RedisClient
from wke.core import keys
from wke.core.dossiers import pointer_rev_id
from wke.core.errors import ApiException
from wke.core.keys.ttl import DAY
from wke.core.models import Dossier
from wke.jobs.build.rating import rating_key
from wke.jobs.queue import JobQueue
from wke.services.freshness import compute_freshness, maybe_enqueue_rebuild

logger = logging.getLogger(__name__)

# A dossier with less than this left on its key gets the full lifetime back.
EXPIRY_WINDOW_SECONDS = 2 * DAY
# The most rebuilds one run admits; the next run takes up the rest.
MAX_REBUILDS_PER_RUN = 200
# After this long the run stops asking for rebuilds and only extends expiries.
REBUILD_PHASE_SECONDS = 30 * 60
# How long to wait after a full background queue before the next page.
QUEUE_FULL_WAIT_SECONDS = 30

SleepFn = Callable[[float], Awaitable[None]]
ClockFn = Callable[[], float]


@dataclass
class RefreshSummary:
    """What one run did.

    A dossier can count under several of stale, extended and a rebuild outcome.

    Attributes:
        stored: dossiers the run judged.
        stale: of those, the ones whose article has a newer revision.
        admitted: rebuilds queued.
        refused: rebuilds `maybe_enqueue_rebuild` declined (too young, not quiet, debounced).
        deferred: stale dossiers left for the next run: full queue, or a limit reached.
        extended: dossiers whose key got its full lifetime back, stale or not.
        left_alone: dossiers neither extended nor asked to rebuild.
        skipped: pages left out of the judging, such as a gone key or another version.
    """

    stored: int = 0
    stale: int = 0
    admitted: int = 0
    refused: int = 0
    deferred: int = 0
    extended: int = 0
    left_alone: int = 0
    skipped: int = 0


@dataclass(frozen=True)
class _Stored:
    """One stored dossier as the run needs it."""

    page_id: int
    rev_id: int
    title: str
    built_at: datetime
    expires_in_ms: int


async def run_refresh(
    raw_redis: Redis,
    redis: RedisClient,
    job_queue: JobQueue,
    pipeline_version: str,
    sleep: SleepFn = asyncio.sleep,
    clock: ClockFn = time.monotonic,
) -> RefreshSummary:
    """Refresh every stored dossier once, those closest to expiry first.

    Args:
        raw_redis: the plain Redis client; the job's own reads and writes go through it so
            that a Redis failure raises instead of reading as an empty answer.
        redis: the fail-open wrapper `maybe_enqueue_rebuild` and the job queue take.
        job_queue: background build admission queue.
        pipeline_version: PIPELINE_VERSION setting; a dossier of another version is skipped.
        sleep: injectable sleep for the wait after a full queue.
        clock: injectable monotonic clock for the rebuild time limit.

    Returns:
        RefreshSummary: the counts of the run.

    Raises:
        redis.exceptions.RedisError: Redis failed; nothing is retried.
    """
    started = clock()
    summary = RefreshSummary()
    stored = await _load_stored(raw_redis, pipeline_version, summary)
    stored.sort(key=lambda item: item.expires_in_ms)
    summary.stored = len(stored)

    stop_logged = False
    for item in stored:
        # The expiry is renewed first, so no outcome of the rebuild can lose the page.
        extended = await _extend(raw_redis, item, pipeline_version)
        if extended:
            summary.extended += 1
        freshness = await compute_freshness(redis, item.page_id, item.rev_id, item.built_at)
        asked = False
        if freshness.state == "stale":
            summary.stale += 1
            if (
                summary.admitted >= MAX_REBUILDS_PER_RUN
                or clock() - started >= REBUILD_PHASE_SECONDS
            ):
                summary.deferred += 1
                if not stop_logged:
                    logger.info("rebuild limit reached, the next run takes up the rest")
                    stop_logged = True
            else:
                asked = True
                await _ask_rebuild(redis, job_queue, item, summary, sleep)
        if not extended and not asked:
            summary.left_alone += 1
    return summary


async def _load_stored(
    raw_redis: Redis, pipeline_version: str, summary: RefreshSummary
) -> list[_Stored]:
    """Read every page of the `built` index that has a readable dossier to keep.

    A page is skipped when its pointer or its dossier under this pipeline version is gone,
    the dossier is unreadable, or it is a structural one: that kind lives 10 minutes on
    purpose so that a later model build can replace it.

    Args:
        raw_redis: the plain Redis client.
        pipeline_version: PIPELINE_VERSION setting.
        summary: counts; `skipped` grows for every page left out.

    Returns:
        list[_Stored]: the dossiers to judge, in index order.
    """
    found: list[_Stored] = []
    for raw_page_id in await raw_redis.zrange(keys.BUILT, 0, -1):
        page_id = int(raw_page_id)
        ptr_raw = await raw_redis.get(keys.ptr(page_id))
        rev_id = pointer_rev_id(ptr_raw) if ptr_raw is not None else None
        if rev_id is None:
            summary.skipped += 1
            continue
        key = keys.dossier(page_id, rev_id, pipeline_version)
        async with raw_redis.pipeline(transaction=True) as pipe:
            pipe.get(key)
            pipe.pttl(key)
            dossier_raw, expires_in_ms = await pipe.execute()
        # PTTL answers -2 for a missing key and -1 for a key that never expires.
        if dossier_raw is None or expires_in_ms == -2:
            summary.skipped += 1
            continue
        try:
            dossier = Dossier.model_validate_json(dossier_raw)
        except ValidationError:
            logger.warning("unreadable dossier for page_id=%s skipped", page_id)
            summary.skipped += 1
            continue
        if dossier.build.analysis == "structural":
            summary.skipped += 1
            continue
        found.append(
            _Stored(
                page_id=page_id,
                rev_id=rev_id,
                title=dossier.topic.title,
                built_at=dossier.build.built_at,
                expires_in_ms=expires_in_ms if expires_in_ms >= 0 else 2**62,
            )
        )
    return found


async def _ask_rebuild(
    redis: RedisClient,
    job_queue: JobQueue,
    item: _Stored,
    summary: RefreshSummary,
    sleep: SleepFn,
) -> None:
    """Ask for the rebuild of one stale dossier and count the answer.

    A full queue is waited out for QUEUE_FULL_WAIT_SECONDS and the page is left for the
    next run: the debounce key `maybe_enqueue_rebuild` sets would refuse it again now.

    Args:
        redis: the fail-open Redis wrapper.
        job_queue: background build admission queue.
        item: the stale dossier.
        summary: counts, updated in place.
        sleep: injectable sleep.
    """
    try:
        admitted = await maybe_enqueue_rebuild(
            redis, job_queue, item.page_id, item.title, item.built_at
        )
    except ApiException as exc:
        logger.warning("rebuild not admitted for page_id=%s: %s", item.page_id, exc)
        summary.deferred += 1
        if exc.code == "queue_full":
            await sleep(QUEUE_FULL_WAIT_SECONDS)
        return
    if admitted:
        summary.admitted += 1
    else:
        summary.refused += 1


async def _extend(raw_redis: Redis, item: _Stored, pipeline_version: str) -> bool:
    """Give a dossier that expires soon its full lifetime back.

    The rating document of the revision, if there is one, gets the same lifetime, since
    a read re-ranks the passages by it and the page would change without it. The
    dossier value, the pointer and the built time are not touched.

    Args:
        raw_redis: the plain Redis client.
        item: a stored dossier, stale or not.
        pipeline_version: PIPELINE_VERSION setting.

    Returns:
        bool: True if the dossier key was extended; False if it has more than the window
        left, never expires, or vanished since it was read.
    """
    if item.expires_in_ms > EXPIRY_WINDOW_SECONDS * 1000:
        return False
    key = keys.dossier(item.page_id, item.rev_id, pipeline_version)
    if not await raw_redis.expire(key, keys.DOSSIER_TTL_SECONDS):
        return False
    await raw_redis.expire(
        rating_key(item.page_id, item.rev_id, pipeline_version), keys.DOSSIER_TTL_SECONDS
    )
    return True
