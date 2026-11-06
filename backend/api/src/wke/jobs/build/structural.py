"""Persistence of the structural fallback dossier, built when wke-ml is unavailable."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from pydantic import HttpUrl

from wke.clients.redis import RedisClient
from wke.core import keys
from wke.core.models import (
    BuildInfo,
    Chunk,
    ChunkKind,
    Citation,
    Dossier,
    DossierGraph,
    DossierTopic,
    GraphNode,
    Job,
    Section,
)
from wke.core.parse import ParsedArticle, ParsedSection
from wke.core.titles import normalize_title
from wke.core.viewcache import invalidate_views
from wke.jobs.build.constants import LICENSE_NOTICE
from wke.jobs.build.payload import dossier_payload, ptr_json
from wke.jobs.build.progress import bump_done
from wke.jobs.build.sections import label_sections, own_heading_path, section_state
from wke.jobs.queue import JobQueue
from wke.metrics import SUMMARY_STATE_TOTAL

logger = logging.getLogger(__name__)


def _merge_nested_sections(
    parsed: ParsedArticle,
) -> tuple[list[ParsedSection], dict[str, list[str]], dict[str, int], dict[str, int]]:
    """Fold each nested section's chunks and drop counts into its top-level section.

    Args:
        parsed: the parsed article.

    Returns:
        tuple: the top-level sections, then their chunk ids, dropped list
        counts and dropped table counts keyed by section id.
    """
    top_level = [s for s in parsed.sections if not s.heading_path]
    chunk_ids_by_section: dict[str, list[str]] = {s.id: list(s.chunk_ids) for s in top_level}
    # Attribute each nested section's chunks to whichever top-level
    # section most recently preceded it in document order, by id.
    # Two top-level sections can share a heading (e.g. two "History"
    # sections), so looking a child's ancestor heading text up in a
    # {heading: section} dict would silently merge both duplicates'
    # children into whichever duplicate the dict happened to keep.
    dropped_lists: dict[str, int] = {s.id: s.dropped_lists for s in top_level}
    dropped_tables: dict[str, int] = {s.id: s.dropped_tables for s in top_level}
    current_top_level_id: str | None = None
    for section in parsed.sections:
        if not section.heading_path:
            current_top_level_id = section.id
            continue

        if current_top_level_id is not None:
            chunk_ids_by_section[current_top_level_id].extend(section.chunk_ids)
            dropped_lists[current_top_level_id] += section.dropped_lists
            dropped_tables[current_top_level_id] += section.dropped_tables

    return top_level, chunk_ids_by_section, dropped_lists, dropped_tables


def _rank_chunks_by_order(parsed: ParsedArticle) -> tuple[list[Chunk], dict[str, ChunkKind]]:
    """Score chunks by document order, since no embedding ran.

    Args:
        parsed: the parsed article; its chunks are updated in place.

    Returns:
        tuple: the chunks and a chunk-id to kind map.
    """
    order_by_chunk_id = {c.id: c.order for c in parsed.chunks}
    chunks = list(parsed.chunks)
    kinds: dict[str, ChunkKind] = {c.id: c.kind for c in chunks}
    for chunk in chunks:
        chunk.relevance = 1.0 / (1.0 + order_by_chunk_id.get(chunk.id, chunk.order))
        chunk.cluster_id = None
    return chunks, kinds


def _structural_sections(
    top_level: list[ParsedSection],
    title: str,
    citation_of: dict[str, str],
    chunk_ids_by_section: dict[str, list[str]],
    dropped_lists: dict[str, int],
    dropped_tables: dict[str, int],
    kinds: dict[str, ChunkKind],
) -> list[Section]:
    """Build the summary-less sections of a structural dossier.

    Args:
        top_level: the article's top-level parsed sections.
        title: the article title.
        citation_of: section id to citation id.
        chunk_ids_by_section: chunk ids per top-level section id.
        dropped_lists: dropped list counts per section id.
        dropped_tables: dropped table counts per section id.
        kinds: chunk id to chunk kind.

    Returns:
        list[Section]: sections whose summary_state is never "pending".
    """
    labelled_top_level = label_sections(top_level, title, heading_label_source="structural")
    sections: list[Section] = []
    for section, label, label_source in labelled_top_level:
        state = section_state(chunk_ids_by_section[section.id], kinds)
        sections.append(
            Section(
                id=section.id,
                label=label,
                label_source=label_source,
                chunk_ids=chunk_ids_by_section[section.id],
                heading_path=own_heading_path(section),
                citation_id=citation_of.get(section.id),
                dropped_non_prose=bool(dropped_lists[section.id] or dropped_tables[section.id]),
                dropped_lists=dropped_lists[section.id],
                dropped_tables=dropped_tables[section.id],
                summary=None,
                summary_state="unavailable" if state == "pending" else state,
            )
        )
    for section in sections:
        SUMMARY_STATE_TOTAL.labels(state=section.summary_state).inc()
    return sections


def _structural_dossier(
    *,
    now: datetime,
    pipeline_version: str,
    page_id: int,
    title: str,
    dossier_id: str,
    seed_citation: Citation,
    related_citations: list[Citation],
    section_citations: list[Citation],
    related_nodes: list[GraphNode],
    parsed: ParsedArticle,
    chunks: list[Chunk],
    sections: list[Section],
    stage_seconds: dict[str, float],
) -> Dossier:
    """Assemble the complete structural-fallback dossier.

    Args:
        now: build timestamp.
        pipeline_version: PIPELINE_VERSION setting.
        page_id: Wikipedia page id.
        title: the article title.
        dossier_id: the dossier id.
        seed_citation: the citation of the seed article.
        related_citations: citations of the related pages.
        section_citations: per-section citations.
        related_nodes: graph nodes of the related pages.
        parsed: the parsed article.
        chunks: the scored chunks.
        sections: the structural sections.
        stage_seconds: timings by stage name.

    Returns:
        Dossier: state "complete", analysis "structural".
    """
    seed_node = GraphNode(
        id=page_id, title=title, role="seed", section_ids=[s.id for s in sections]
    )
    return Dossier(
        id=dossier_id,
        topic=DossierTopic(page_id=page_id, title=title, url=seed_citation.pin.url),
        build=BuildInfo(
            state="complete",
            built_at=now,
            pipeline_version=pipeline_version,
            analysis="structural",
            summaries_done=0,
            summaries_total=0,
            truncated=parsed.truncated,
            stage_seconds=stage_seconds,
        ),
        citations=[seed_citation, *related_citations, *section_citations],
        sections=sections,
        chunks=chunks,
        graph=DossierGraph(nodes=[seed_node, *related_nodes], edges=[]),
        license_notice=LICENSE_NOTICE,
    )


async def _store_structural(
    redis: RedisClient,
    dossier: Dossier,
    *,
    page_id: int,
    rev_id: int,
    title: str,
    pipeline_version: str,
    now: datetime,
) -> None:
    """Write the structural dossier and its indexes to Redis.

    Args:
        redis: Redis client.
        dossier: the dossier to store with the short structural TTL.
        page_id: Wikipedia page id.
        rev_id: pinned revision id.
        title: the article title.
        pipeline_version: PIPELINE_VERSION setting.
        now: build timestamp.
    """
    dossier_key = keys.dossier(page_id, rev_id, pipeline_version)
    await redis.set(
        dossier_key,
        dossier_payload(dossier),
        ex=keys.DOSSIER_STRUCTURAL_TTL_SECONDS,
    )
    await redis.set(keys.ptr(page_id), ptr_json(rev_id, pipeline_version, now))
    await redis.sadd(keys.TRACKED, str(page_id))
    await redis.hset(keys.TRACKED_PAGE_IDS, normalize_title(title), str(page_id))
    await redis.zadd(keys.BUILT, {str(page_id): now.timestamp()})
    invalidate_views()


async def _finish_structural_job(
    redis: RedisClient,
    job: Job,
    job_queue: JobQueue,
    *,
    page_id: int,
    rev_id: int,
    now: datetime,
    result_url: HttpUrl | None,
    stage_seconds: dict[str, float],
) -> None:
    """Mark the job done and release its single-flight key.

    Args:
        redis: Redis client.
        job: the job to finish.
        job_queue: JobQueue, for set_job.
        page_id: Wikipedia page id.
        rev_id: pinned revision id.
        now: completion timestamp.
        result_url: Job.result_url, or None.
        stage_seconds: timings by stage name, for the log line.
    """
    bump_done(job)  # persist complete
    job.status = "done"
    job.queue_position = None
    job.stage = "persist"
    job.partial_available = True
    job.result_url = result_url
    job.updated_at = now
    job.finished_at = now
    await job_queue.set_job(job)
    # The structural dossier's TTL is short (DOSSIER_STRUCTURAL_TTL_SECONDS)
    # so a later ML retry can take over; jobkey's 1h TTL must not outlive
    # it, or POST admits the same stale "done" job for ~50 more minutes
    # with nothing behind it once the dossier expires.
    await redis.delete(keys.jobkey(page_id, rev_id))
    logger.info(
        "job_structural_done job_id=%s page_id=%s rev_id=%s stage_seconds=%.2f",
        job.id,
        page_id,
        rev_id,
        stage_seconds.get("build", 0.0),
    )


async def persist_structural(
    *,
    redis: RedisClient,
    job: Job,
    job_queue: JobQueue,
    pipeline_version: str,
    page_id: int,
    rev_id: int,
    title: str,
    dossier_id: str,
    seed_citation: Citation,
    related_citations: list[Citation],
    section_citations: list[Citation],
    citation_of: dict[str, str],
    related_nodes: list[GraphNode],
    parsed: ParsedArticle,
    stage_seconds: dict[str, float],
    result_url: HttpUrl | None = None,
) -> None:
    """Persist a complete structural dossier when wke-ml is unavailable.

    Args:
        redis: Redis client.
        job: the running job; finished here.
        job_queue: JobQueue, for set_job.
        pipeline_version: PIPELINE_VERSION setting.
        page_id: Wikipedia page id.
        rev_id: pinned revision id.
        title: the article title.
        dossier_id: the dossier id.
        seed_citation: the citation of the seed article.
        related_citations: citations of the related pages.
        section_citations: per-section citations.
        citation_of: section id to citation id.
        related_nodes: graph nodes of the related pages.
        parsed: the parsed article.
        stage_seconds: timings by stage name.
        result_url: Job.result_url, or None.
    """
    top_level, chunk_ids_by_section, dropped_lists, dropped_tables = _merge_nested_sections(parsed)
    chunks, kinds = _rank_chunks_by_order(parsed)
    sections = _structural_sections(
        top_level, title, citation_of, chunk_ids_by_section, dropped_lists, dropped_tables, kinds
    )
    now = datetime.now(UTC)
    dossier = _structural_dossier(
        now=now,
        pipeline_version=pipeline_version,
        page_id=page_id,
        title=title,
        dossier_id=dossier_id,
        seed_citation=seed_citation,
        related_citations=related_citations,
        section_citations=section_citations,
        related_nodes=related_nodes,
        parsed=parsed,
        chunks=chunks,
        sections=sections,
        stage_seconds=stage_seconds,
    )
    await _store_structural(
        redis,
        dossier,
        page_id=page_id,
        rev_id=rev_id,
        title=title,
        pipeline_version=pipeline_version,
        now=now,
    )
    await _finish_structural_job(
        redis,
        job,
        job_queue,
        page_id=page_id,
        rev_id=rev_id,
        now=now,
        result_url=result_url,
        stage_seconds=stage_seconds,
    )
