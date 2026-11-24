"""Entry point of a build job: fetch through the first persist, queueing the summaries."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from wke.clients.ml import DEFAULT_ANALYZE_DEADLINE_MS, MLClient, MLUnavailable
from wke.clients.redis import RedisClient
from wke.clients.wikimedia import WikimediaClient
from wke.core import keys
from wke.core.models import Job
from wke.jobs.build.constants import (
    ANALYZE_MAX_EDGES,
    ML_PATH_STAGE_COUNT,
    RATING_LOCK_MARGIN_SECONDS,
)
from wke.jobs.build.failure import fail_job
from wke.jobs.build.payload import result_url
from wke.jobs.build.persist import persist_and_queue_summaries
from wke.jobs.build.progress import begin_job, bump_done, enter_stage, set_total
from wke.jobs.build.rating import RatingConfig
from wke.jobs.build.stages import assemble_dossier, fetch_and_parse, lead_text, persist_degraded
from wke.jobs.queue import JobQueue
from wke.metrics import ANALYZE_ATTEMPTS_TOTAL, DOSSIER_BUILD_SECONDS

logger = logging.getLogger(__name__)


async def _analyze_with_retries(
    ml: MLClient,
    job: Job,
    *,
    lead: str,
    chunks: list[dict[str, str]],
    related_leads: list[dict[str, Any]],
    page_id: int,
    deadline_ms: int,
    retries: int,
    pause_ms: int,
    retry_on_timeout: bool,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> dict[str, Any]:
    """Call wke-ml analyze, retrying a transient failure, one log line per attempt.

    Args:
        ml: wke-ml client.
        job: the build job, for the log line.
        lead: lead paragraph text.
        chunks: {id, text} prose chunk payloads.
        related_leads: related-article leads.
        page_id: the page being built.
        deadline_ms: deadline of each attempt.
        retries: retries after the first attempt.
        pause_ms: pause before each retry.
        retry_on_timeout: whether a timeout is retried (http_4xx never is).
        sleep: awaited with the pause in seconds; injected by tests.

    Returns:
        dict[str, Any]: the analyze response.

    Raises:
        MLUnavailable: the last attempt's failure.
    """
    text_chars = sum(len(c["text"]) for c in chunks)
    attempt = 0
    while True:
        attempt += 1
        started = time.monotonic()
        try:
            result = await ml.analyze(
                lead=lead,
                chunks=chunks,
                related_leads=related_leads,
                page_id=page_id,
                max_edges=ANALYZE_MAX_EDGES,
                deadline_ms=deadline_ms,
            )
        except MLUnavailable as exc:
            _log_analyze(job, len(chunks), text_chars, deadline_ms, started, exc.reason, attempt)
            retryable = not exc.reason.startswith("http_4") and (
                exc.reason != "timeout" or retry_on_timeout
            )
            if attempt > retries or not retryable:
                raise
            await sleep(pause_ms / 1000)
        else:
            _log_analyze(job, len(chunks), text_chars, deadline_ms, started, "ok", attempt)
            return result


def _log_analyze(
    job: Job,
    chunk_count: int,
    text_chars: int,
    deadline_ms: int,
    started: float,
    outcome: str,
    attempt: int,
) -> None:
    ANALYZE_ATTEMPTS_TOTAL.labels(outcome=outcome).inc()
    elapsed_ms = round((time.monotonic() - started) * 1000)
    logger.info(
        "analyze_attempt job_id=%s chunks=%s text_chars=%s deadline_ms=%s elapsed_ms=%s "
        "outcome=%s attempt=%s",
        job.id,
        chunk_count,
        text_chars,
        deadline_ms,
        elapsed_ms,
        outcome,
        attempt,
        extra={"job_id": job.id, "request_id": job.request_id},
    )


async def _queue_rating(
    job_queue: JobQueue, rating: RatingConfig, page_id: int, rev_id: int
) -> None:
    """Queue the stored dossier's rating stage when selection by rating is on."""
    if rating.enabled:
        await job_queue.enqueue_rating(
            page_id, rev_id, rating.deadline_seconds + RATING_LOCK_MARGIN_SECONDS
        )


async def run_build(
    job: Job,
    *,
    redis: RedisClient,
    wikimedia: WikimediaClient,
    ml: MLClient,
    job_queue: JobQueue,
    pipeline_version: str,
    summary_sections: int,
    wikipedia_api_url: str,
    background: bool,
    public_host: str = "",
    public_scheme: str = "https",
    analyze_deadline_ms: int = DEFAULT_ANALYZE_DEADLINE_MS,
    analyze_retries: int = 0,
    analyze_retry_pause_ms: int = 0,
    analyze_retry_on_timeout: bool = False,
    structural_ttl_seconds: int = keys.DOSSIER_STRUCTURAL_TTL_SECONDS,
    rating: RatingConfig = RatingConfig(),
) -> None:
    """Run one build job from fetch to the first persist, failing it cleanly on error.

    Any exception marks the job "failed" (with the error attached) and
    deletes the single-flight jobkey, so the next POST for this page/rev
    starts a fresh build instead of finding the same job stuck "running"
    for up to an hour. The exception is re-raised so the worker still logs
    it. When wke-ml is unavailable the structural dossier is persisted
    instead and the job is done.

    Args:
        job: the admitted Job (page_id/rev_id/title already pinned).
        redis: Redis client.
        wikimedia: Wikimedia client (fetch, related).
        ml: wke-ml client (analyze; summarize happens in run_summary_item).
        job_queue: JobQueue, for enqueue_summary_item and set_job.
        pipeline_version: PIPELINE_VERSION setting, part of the dossier key.
        summary_sections: SUMMARY_SECTIONS setting.
        wikipedia_api_url: settings.wikipedia_api_url, used only to derive
            the wiki's origin for citation/permalink URLs.
        background: True if this build came off q:background (propagated
            to the summary items it queues).
        public_host: PUBLIC_HOST setting, for Job.result_url; empty
            leaves result_url unset.
        public_scheme: PUBLIC_SCHEME setting, for Job.result_url.
        analyze_deadline_ms: ANALYZE_DEADLINE_MS setting, the deadline of each analyze call.
        analyze_retries: ANALYZE_RETRIES setting.
        analyze_retry_pause_ms: ANALYZE_RETRY_PAUSE_MS setting.
        analyze_retry_on_timeout: ANALYZE_RETRY_ON_TIMEOUT setting.
        structural_ttl_seconds: DOSSIER_STRUCTURAL_TTL_SECONDS setting.
        rating: the rating settings; when enabled, the stored dossier is queued for rating.

    Raises:
        Exception: whatever the build raised, after marking the job failed
            and releasing its jobkey (ApiException from WikimediaClient on
            an unrecoverable fetch failure, ValidationError for a dossier
            that would not read back).
    """
    try:
        assert job.rev_id is not None
        page_id, rev_id = job.page_id, job.rev_id
        started = time.monotonic()
        logger.info(
            "job_started job_id=%s page_id=%s rev_id=%s",
            job.id,
            page_id,
            rev_id,
            extra={"job_id": job.id, "request_id": job.request_id},
        )
        await begin_job(job, job_queue)
        fetched = await fetch_and_parse(
            job, redis=redis, wikimedia=wikimedia, job_queue=job_queue, api_url=wikipedia_api_url
        )
        await enter_stage(job, job_queue, "embed")
        prose_chunks = [c for c in fetched.parsed.chunks if c.kind == "prose"]
        try:
            analysis_result = await _analyze_with_retries(
                ml,
                job,
                lead=lead_text(prose_chunks),
                chunks=[{"id": c.id, "text": c.text} for c in prose_chunks],
                related_leads=fetched.related_leads,
                page_id=page_id,
                deadline_ms=analyze_deadline_ms,
                retries=analyze_retries,
                pause_ms=analyze_retry_pause_ms,
                retry_on_timeout=analyze_retry_on_timeout,
            )
        except MLUnavailable as exc:
            logger.warning("ML unavailable during analyze for job %s: %s", job.id, exc.reason)
            await persist_degraded(
                job,
                fetched,
                redis=redis,
                job_queue=job_queue,
                pipeline_version=pipeline_version,
                started=started,
                result=result_url(public_host, public_scheme, page_id),
                structural_ttl_seconds=structural_ttl_seconds,
            )
            await _queue_rating(job_queue, rating, page_id, rev_id)
            return

        await enter_stage(job, job_queue, "cluster")
        dossier, selected_ids = assemble_dossier(
            job,
            fetched,
            analysis_result,
            pipeline_version=pipeline_version,
            summary_sections=summary_sections,
            build_seconds=time.monotonic() - started,
        )
        bump_done(job)  # cluster complete
        set_total(job, ML_PATH_STAGE_COUNT + len(selected_ids) + 1)  # + summary items + finalize
        job.stage = "persist"
        job.partial_available = True
        await persist_and_queue_summaries(
            redis=redis,
            job_queue=job_queue,
            job=job,
            dossier=dossier,
            selected_ids=selected_ids,
            pipeline_version=pipeline_version,
            background=background,
            ttl_seconds=keys.DOSSIER_TTL_SECONDS,
            result_url=result_url(public_host, public_scheme, page_id),
        )
        await _queue_rating(job_queue, rating, page_id, rev_id)
        DOSSIER_BUILD_SECONDS.labels(outcome="partial", analysis="ml").observe(
            time.monotonic() - started
        )
    except Exception as exc:
        await fail_job(job, redis, job_queue, pipeline_version, exc)
        raise
