"""Steps of a build between admission and persistence: fetch, parse, analyse, assemble."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import HttpUrl, TypeAdapter

from wke.clients.redis import RedisClient
from wke.clients.wikimedia import WikimediaClient
from wke.core.citations import citation_url
from wke.core.models import (
    BuildInfo,
    Chunk,
    Citation,
    Dossier,
    DossierGraph,
    DossierTopic,
    GraphEdge,
    GraphNode,
    Job,
)
from wke.core.parse import ParsedArticle, parse_html
from wke.core.text.wikilinks import wiki_origin
from wke.jobs.build.cite import build_related_citations, cite_sections, revision_pin
from wke.jobs.build.constants import LICENSE_NOTICE, STRUCTURAL_PATH_STAGE_COUNT
from wke.jobs.build.fetch import fetch_html, fetch_related, fetch_revision_timestamp
from wke.jobs.build.progress import bump_done, enter_stage, set_total
from wke.jobs.build.sections import assemble_sections
from wke.jobs.build.structural import persist_structural
from wke.jobs.queue import JobQueue
from wke.metrics import DOSSIER_BUILD_SECONDS, JOB_STAGE_SECONDS

_HTTP_URL = TypeAdapter(HttpUrl)

logger = logging.getLogger(__name__)


def lead_text(prose_chunks: list[Chunk]) -> str:
    """Join the lead chunks, or fall back to the first prose chunk.

    Args:
        prose_chunks: the article's prose chunks in document order.

    Returns:
        The text sent to wke-ml as the article lead.
    """
    lead_chunks = [c for c in prose_chunks if not c.heading_path]
    return " ".join(c.text for c in lead_chunks) or (prose_chunks[0].text if prose_chunks else "")


def apply_analysis(chunks: list[Chunk], analysis_result: dict[str, Any]) -> list[GraphEdge]:
    """Copy relevance and cluster ids from the wke-ml response onto the chunks.

    Both response maps are keyed by chunk id (wke_ml.analyze), not parallel lists.

    Args:
        chunks: the article's chunks, updated in place.
        analysis_result: the AnalyzeResponse payload.

    Returns:
        The graph edges of the response.
    """
    relevance_by_id = analysis_result.get("relevance", {})
    cluster_by_id = analysis_result.get("cluster_ids", {})
    for chunk in chunks:
        chunk.relevance = float(relevance_by_id.get(chunk.id, chunk.relevance))
        chunk.cluster_id = cluster_by_id.get(chunk.id, chunk.cluster_id)
    return [
        GraphEdge(source=edge["source"], target=edge["target"], weight=edge["weight"])
        for edge in analysis_result.get("edges", [])
    ]


@dataclass(frozen=True)
class Fetched:
    """Everything stages fetch, parse and related produce for one revision."""

    dossier_id: str
    parsed: ParsedArticle
    seed_citation: Citation
    related_citations: list[Citation]
    related_nodes: list[GraphNode]
    related_leads: list[dict[str, Any]]
    section_citations: list[Citation]
    citation_of: dict[str, str]


async def fetch_and_parse(
    job: Job,
    *,
    redis: RedisClient,
    wikimedia: WikimediaClient,
    job_queue: JobQueue,
    api_url: str,
) -> Fetched:
    """Run the fetch, parse and related stages for the job's pinned revision.

    Args:
        job: the running job (page_id, rev_id and title pinned).
        redis: Redis client.
        wikimedia: Wikimedia client (fetch, related).
        job_queue: JobQueue, for set_job.
        api_url: settings.wikipedia_api_url, to derive the wiki origin.

    Returns:
        Fetched: the parsed article with its seed and related citations.
    """
    assert job.rev_id is not None
    page_id, rev_id, title = job.page_id, job.rev_id, job.title or ""
    html = await fetch_html(redis, wikimedia, rev_id)
    rev_timestamp = await fetch_revision_timestamp(redis, wikimedia, rev_id)
    origin = wiki_origin(api_url)
    seed_pin = revision_pin(page_id, title, rev_id, origin, rev_timestamp)
    seed_citation = Citation(
        id="c1",
        pin=seed_pin,
        role="seed",
        url=_HTTP_URL.validate_python(citation_url(seed_pin, None)),
    )

    await enter_stage(job, job_queue, "parse")
    parsed: ParsedArticle = await asyncio.to_thread(parse_html, html, rev_id, seed_citation.id)

    await enter_stage(job, job_queue, "related")
    related_pages = await fetch_related(redis, wikimedia, page_id, title)
    related_citations, related_nodes, related_leads = build_related_citations(
        related_pages, origin, start_index=2
    )
    build_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()[:12]
    section_citations, citation_of = cite_sections(parsed, seed_citation, related_citations)
    return Fetched(
        dossier_id=f"{page_id}@{rev_id}:{build_hash}",
        parsed=parsed,
        seed_citation=seed_citation,
        related_citations=related_citations,
        related_nodes=related_nodes,
        related_leads=related_leads,
        section_citations=section_citations,
        citation_of=citation_of,
    )


async def persist_degraded(
    job: Job,
    fetched: Fetched,
    *,
    redis: RedisClient,
    job_queue: JobQueue,
    pipeline_version: str,
    started: float,
    result: HttpUrl | None,
) -> None:
    """Persist the structural-only dossier when wke-ml is unavailable.

    Args:
        job: the running job.
        fetched: the output of the fetch, parse and related stages.
        redis: Redis client.
        job_queue: JobQueue, for set_job.
        pipeline_version: PIPELINE_VERSION setting.
        started: time.monotonic() at the start of the build.
        result: the Job.result_url value, or None.
    """
    assert job.rev_id is not None
    bump_done(job)  # embed attempt over (unavailable)
    set_total(job, STRUCTURAL_PATH_STAGE_COUNT)
    build_seconds = time.monotonic() - started
    JOB_STAGE_SECONDS.labels(stage="build").observe(build_seconds)
    await persist_structural(
        redis=redis,
        job=job,
        job_queue=job_queue,
        pipeline_version=pipeline_version,
        page_id=job.page_id,
        rev_id=job.rev_id,
        title=job.title or "",
        dossier_id=fetched.dossier_id,
        seed_citation=fetched.seed_citation,
        related_citations=fetched.related_citations,
        section_citations=fetched.section_citations,
        citation_of=fetched.citation_of,
        related_nodes=fetched.related_nodes,
        parsed=fetched.parsed,
        stage_seconds={"build": build_seconds},
        result_url=result,
    )
    DOSSIER_BUILD_SECONDS.labels(outcome="degraded", analysis="structural").observe(build_seconds)


def assemble_dossier(
    job: Job,
    fetched: Fetched,
    analysis_result: dict[str, Any],
    *,
    pipeline_version: str,
    summary_sections: int,
    build_seconds: float,
) -> tuple[Dossier, list[str]]:
    """Build the partial ML dossier from the parsed article and wke-ml output.

    Args:
        job: the running job.
        fetched: the output of the fetch, parse and related stages.
        analysis_result: the AnalyzeResponse payload.
        pipeline_version: PIPELINE_VERSION setting.
        summary_sections: SUMMARY_SECTIONS setting.
        build_seconds: wall time spent so far, recorded in BuildInfo.

    Returns:
        tuple[Dossier, list[str]]: the dossier and the ids of the sections
        selected for summarisation.
    """
    parsed, title = fetched.parsed, job.title or ""
    chunks = list(parsed.chunks)
    edges = apply_analysis(chunks, analysis_result)
    seed_node = GraphNode(
        id=job.page_id, title=title, role="seed", section_ids=[s.id for s in parsed.sections]
    )
    sections, selected_ids = assemble_sections(
        parsed, chunks, title, fetched.citation_of, summary_sections
    )
    JOB_STAGE_SECONDS.labels(stage="build").observe(build_seconds)
    dossier = Dossier(
        id=fetched.dossier_id,
        topic=DossierTopic(page_id=job.page_id, title=title, url=fetched.seed_citation.pin.url),
        build=BuildInfo(
            state="partial",
            built_at=datetime.now(UTC),
            pipeline_version=pipeline_version,
            analysis="ml",
            summaries_done=0,
            summaries_total=len(selected_ids),
            truncated=parsed.truncated,
            stage_seconds={"build": build_seconds},
        ),
        citations=[fetched.seed_citation, *fetched.related_citations, *fetched.section_citations],
        sections=sections,
        chunks=chunks,
        graph=DossierGraph(nodes=[seed_node, *fetched.related_nodes], edges=edges),
        license_notice=LICENSE_NOTICE,
    )
    return dossier, selected_ids
