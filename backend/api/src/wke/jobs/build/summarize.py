"""One content-addressed summary item per selected section, and the job's last step."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from wke.clients.ml import MLClient, MLUnavailable
from wke.clients.redis import RedisClient
from wke.core import keys
from wke.core.models import Chunk, Dossier, MachineSummary, MachineSummaryParams, Section
from wke.core.text.tokens import est_tokens
from wke.jobs.build.constants import (
    SUMMARY_INPUT_CHAR_CAP,
    SUMMARY_MAX_LENGTH,
    SUMMARY_MIN_LENGTH,
    SUMMARY_MODEL,
    SUMMARY_MODEL_REVISION,
)
from wke.jobs.build.failure import fail_job
from wke.jobs.build.finalize import finalize
from wke.jobs.build.payload import dossier_payload
from wke.jobs.build.progress import bump_done
from wke.jobs.build.summary_gate import attach_summary, mark_unavailable
from wke.jobs.queue import JobQueue
from wke.metrics import CACHE_REQUESTS_TOTAL, SUMMARY_STATE_TOTAL

logger = logging.getLogger(__name__)


async def run_summary_item(
    job_id: str,
    section_id: str,
    *,
    redis: RedisClient,
    job_queue: JobQueue,
    ml: MLClient,
    pipeline_version: str,
    num_beams: int,
) -> None:
    """Summarise one section of a stored dossier and settle the job when all are done.

    An unexpected exception (a malformed stored dossier, a Redis failure)
    marks the job "failed" and deletes its jobkey instead of leaving it
    stuck "running" with a dossier that will never finalize; it is
    re-raised afterwards. A missing job, dossier or section is logged and
    the item dropped.

    Args:
        job_id: id of the build job.
        section_id: the Section.id to summarise.
        redis: Redis client.
        job_queue: JobQueue, for get_job and set_job.
        ml: wke-ml client.
        pipeline_version: PIPELINE_VERSION setting, part of the dossier key.
        num_beams: NUM_BEAMS setting, passed to wke-ml /v1/summarize.

    Raises:
        Exception: whatever the item raised, after marking the job failed
            and releasing its jobkey.
    """
    try:
        job = await job_queue.get_job(job_id)
        if job is None or job.rev_id is None:
            logger.warning("summary item for missing/expired job %s", job_id)
            return

        dossier_key = keys.dossier(job.page_id, job.rev_id, pipeline_version)
        raw = await redis.get(dossier_key)
        if raw is None:
            logger.warning("summary item for missing dossier %s", dossier_key)
            return
        dossier = Dossier.model_validate_json(raw)

        section = next((s for s in dossier.sections if s.id == section_id), None)
        if section is None:
            logger.warning("summary item for unknown section %s in job %s", section_id, job_id)
            return

        foreign_titles = [c.pin.title for c in dossier.citations if c.role == "related"]
        await summarize_section(redis, ml, section, dossier.chunks, num_beams, foreign_titles)
        SUMMARY_STATE_TOTAL.labels(state=section.summary_state).inc()
        bump_done(job)  # this summary item complete

        selected_resolved = _settled_summaries(dossier)
        if selected_resolved >= dossier.build.summaries_total:
            await finalize(redis, job_queue, job, dossier, pipeline_version)
        else:
            dossier.build.summaries_done = selected_resolved
            await redis.set(dossier_key, dossier_payload(dossier), ex=keys.DOSSIER_TTL_SECONDS)
            job.updated_at = datetime.now(UTC)
            await job_queue.set_job(job)
    except Exception as exc:
        failed = await job_queue.get_job(job_id)
        if failed is not None:
            await fail_job(failed, redis, job_queue, pipeline_version, exc)
        raise


def _settled_summaries(dossier: Dossier) -> int:
    """Count the selected sections whose summary is settled.

    A section with no prose chunk is "skipped" from the start and never gets
    a summary item, so it does not count.

    Args:
        dossier: the stored dossier.

    Returns:
        int: sections that are done, unavailable, withheld, or skipped with prose.
    """
    prose_ids = {c.id for c in dossier.chunks if c.kind == "prose"}
    return sum(
        1
        for s in dossier.sections
        if s.summary_state in ("done", "unavailable", "withheld")
        or (s.summary_state == "skipped" and any(cid in prose_ids for cid in s.chunk_ids))
    )


def summary_input(section: Section, chunks: list[Chunk]) -> tuple[str, list[str]]:
    """Assemble the passages the model reads for one section.

    The section's opening passage comes first, then the rest in document
    order, until SUMMARY_INPUT_CHAR_CAP characters are used.

    Args:
        section: the section to summarise.
        chunks: the dossier's chunks.

    Returns:
        tuple: the joined input text and the ids of the chunks in it.
    """
    chunk_by_id = {c.id: c for c in chunks}
    prose = [
        chunk_by_id[cid]
        for cid in section.chunk_ids
        if cid in chunk_by_id and chunk_by_id[cid].kind == "prose"
    ]
    input_text = ""
    input_ids: list[str] = []
    for chunk in sorted(prose, key=lambda c: c.order):
        if input_text and len(input_text) + 1 + len(chunk.text) > SUMMARY_INPUT_CHAR_CAP:
            break
        input_text = f"{input_text} {chunk.text}".strip()
        input_ids.append(chunk.id)
    return input_text, input_ids


def _summary_from_result(
    result: dict[str, Any], section: Section, input_text: str, input_ids: list[str], num_beams: int
) -> MachineSummary | None:
    """Build a MachineSummary from wke-ml's response, or None if it is incomplete.

    A MachineSummary must come only from wke-ml's own output: a missing or
    empty text, or a missing model/model_revision, is never padded with our
    defaults, which would fabricate provenance for content wke-ml never
    actually returned.

    Args:
        result: the decoded /v1/summarize response.
        section: the section being summarised, for the log line.
        input_text: the joined text the model read.
        input_ids: ids of the chunks the model read.
        num_beams: the beam count used for the call.

    Returns:
        MachineSummary | None: None when text, model or model_revision is missing.
    """
    text = result.get("text")
    model = result.get("model")
    model_revision = result.get("model_revision")
    if not text or not model or not model_revision:
        logger.warning(
            "summarize response for section %s missing text/model/model_revision", section.id
        )
        return None
    return MachineSummary(
        text=text,
        model=model,
        model_revision=model_revision,
        params=MachineSummaryParams(
            num_beams=num_beams,
            min_length=SUMMARY_MIN_LENGTH,
            max_length=SUMMARY_MAX_LENGTH,
            input_tokens=est_tokens(input_text),
        ),
        # Always the locally computed input_ids, never wke-ml's own
        # field: wke-ml is sent raw text, not chunk ids, so it has no
        # way to report real ones back.
        input_chunk_ids=input_ids,
        generated_at=datetime.now(UTC),
        infer_seconds=result.get("infer_seconds"),
    )


async def summarize_section(
    redis: RedisClient,
    ml: MLClient,
    section: Section,
    chunks: list[Chunk],
    num_beams: int,
    foreign_titles: Sequence[str] = (),
) -> None:
    """Summarise one section through the cache or wke-ml and attach the result.

    Args:
        redis: Redis client, for the content-addressed summary cache.
        ml: wke-ml client.
        section: the section to summarise; changed in place.
        chunks: the dossier's chunks.
        num_beams: the beam count for the call.
        foreign_titles: titles of other articles the summary may not name.
    """
    input_text, input_ids = summary_input(section, chunks)

    if not input_text:
        # No chunk had text to summarize (empty section) -- distinct from
        # the model being unreachable, so it must not render the "model
        # could not be reached" notice.
        section.summary = None
        section.summary_state = "skipped"
        return

    params_str = f"beams={num_beams}|min={SUMMARY_MIN_LENGTH}|max={SUMMARY_MAX_LENGTH}"
    cache_key = keys.sum_key(input_text, SUMMARY_MODEL, SUMMARY_MODEL_REVISION, params_str)
    cached = await redis.get(cache_key)
    heading = section.heading_path[-1] if section.heading_path else section.label
    if cached is not None:
        CACHE_REQUESTS_TOTAL.labels(kind="sum", result="hit").inc()
        # A content-addressed hit can be a summary cached for a chunk
        # text identical to this section's but produced under a
        # different revision. Its cached input_chunk_ids embed that old
        # rev_id ("{rev_id}:{section}:{n}") and would cite chunks that
        # do not exist in this dossier, so they are always replaced
        # with the current build's own input_ids.
        summary = MachineSummary.model_validate_json(cached)
        attach_summary(
            section, summary, input_ids, input_text, heading, foreign_titles, truncated=False
        )
        return
    CACHE_REQUESTS_TOTAL.labels(kind="sum", result="miss").inc()

    try:
        result = await ml.summarize(
            input_text,
            num_beams=num_beams,
            min_length=SUMMARY_MIN_LENGTH,
            max_length=SUMMARY_MAX_LENGTH,
        )
    except MLUnavailable as exc:
        logger.warning("summarize unavailable for section %s: %s", section.id, exc.reason)
        mark_unavailable(section)
        return

    summary = _summary_from_result(result, section, input_text, input_ids, num_beams)
    if summary is None:
        mark_unavailable(section)
        return
    truncated = bool(result.get("truncated"))
    if not truncated:
        await redis.set(cache_key, summary.model_dump_json(), ex=keys.SUMMARY_TTL_SECONDS)
    attach_summary(section, summary, input_ids, input_text, heading, foreign_titles, truncated)
