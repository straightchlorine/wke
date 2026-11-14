"""Rebuild stored dossiers in place from their pinned revisions, in-process.

Purpose: re-run the build pipeline for dossiers already in Redis, keeping the
same key and pinned revision, so a pipeline change shows up without waiting for
a revision bump. The API is not involved.

Cost: Wikimedia calls only when the 24 h wm:* caches are cold, at most 3 per
dossier. Summaries run here one at a time against wke-ml and are never pushed
to the live queues. The pipeline runs in a scratch Redis db (15); the finished
dossier is the only thing written back to the shared db. Sidecar copies go to
native/ (the stored dossier), after_cache/ (the 32000-token view with
summaries, the input of scripts/eval/fidelity_check.py) and md_after/ (the
8000-token Markdown with summaries) under <repo>/.run/dossier-quality/
(gitignored), or under --out.

Usage, from backend/api with the live-stack env loaded:

    uv run python scripts/rebuild_dossiers.py --ids 69304 82893793
    uv run python scripts/rebuild_dossiers.py --all --dry-run
    uv run python scripts/rebuild_dossiers.py --ids 69304 --compat

By default the new schema is stored as is (--native, the default). --compat,
the same as --no-native, stores a copy an API running older code can validate
(no heading_path or dropped_non_prose, no_prose stored as skipped).
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from pydantic import HttpUrl, TypeAdapter
from redis.asyncio import Redis

from wke.clients.ml import MLClient
from wke.clients.redis import RedisClient, default_redis_factory
from wke.clients.user_agent import build_user_agent
from wke.clients.wikimedia import WikimediaClient
from wke.core import keys, render
from wke.core.models import Dossier, DossierLinks, Freshness, Job, JobProgress
from wke.core.models.budgets import BudgetTokens
from wke.jobs.build.run import run_build
from wke.jobs.build.summarize import run_summary_item
from wke.jobs.job_record import TOTAL_STAGES, make_job_id
from wke.jobs.queue import JobQueue
from wke.services import freshness as freshness_mod
from wke.settings import settings

DEFAULT_OUT = Path(__file__).resolve().parents[3] / ".run" / "dossier-quality"
SCRATCH_DB = 15
MARKER = "rebuild_sample:marker"
PATIENT_DEADLINE_MS = 60000
SIDECAR_BUDGETS: tuple[tuple[str, BudgetTokens], ...] = (("after_cache", 32000), ("md_after", 8000))
_HTTP_URL = TypeAdapter(HttpUrl)


class PatientML(MLClient):
    """MLClient with a 60 s deadline: the shared wke-ml is busy and the 8 s default times out."""

    async def summarize(
        self,
        text: str,
        num_beams: int = 1,
        min_length: int = 30,
        max_length: int = 96,
        deadline_ms: int = PATIENT_DEADLINE_MS,
    ) -> dict[str, Any]:
        """Summarise with the patient deadline unless the caller sets one.

        Args:
            text: the text to summarise.
            num_beams: beam count.
            min_length: minimum summary tokens.
            max_length: maximum summary tokens.
            deadline_ms: deadline in milliseconds.

        Returns:
            dict[str, Any]: the wke-ml response.
        """
        return await super().summarize(text, num_beams, min_length, max_length, deadline_ms)

    async def analyze(
        self,
        lead: str,
        chunks: list[dict[str, str]],
        related_leads: list[dict[str, Any]] | None = None,
        max_clusters: int = 6,
        max_edges: int = 20,
        page_id: int | None = None,
        deadline_ms: int = PATIENT_DEADLINE_MS,
    ) -> dict[str, Any]:
        """Analyse with the patient deadline unless the caller sets one.

        Args:
            lead: the lead text.
            chunks: chunk dicts with id and text.
            related_leads: leads of related articles.
            max_clusters: cluster cap.
            max_edges: related-edge cap.
            page_id: page id of the seed article.
            deadline_ms: deadline in milliseconds.

        Returns:
            dict[str, Any]: the wke-ml response.
        """
        return await super().analyze(
            lead, chunks, related_leads, max_clusters, max_edges, page_id, deadline_ms
        )


class CaptureQueue(JobQueue):
    """JobQueue that records summary items instead of pushing them live."""

    def __init__(
        self,
        redis: RedisClient,
        pipeline_version: str,
        queue_cap: int,
        background_queue_cap: int | None = None,
    ) -> None:
        super().__init__(redis, pipeline_version, queue_cap, background_queue_cap)
        self.selected: list[str] = []

    async def enqueue_summary_item(
        self, job_id: str, section_id: str, background: bool = False
    ) -> None:
        """Remember the section instead of queueing it.

        Args:
            job_id: id of the build job.
            section_id: the section selected for a summary.
            background: unused; the queue is private to this run.
        """
        self.selected.append(section_id)


@dataclass(frozen=True)
class Rebuild:
    """The clients and options one run shares across dossiers."""

    shared: RedisClient
    scratch: RedisClient
    scratch_raw: Redis
    wm: WikimediaClient
    ml: MLClient
    calls: list[int]
    out_dir: Path
    native: bool
    dry_run: bool


def scratch_url(url: str) -> str:
    """Point a Redis URL at the scratch database.

    Args:
        url: the Redis URL of the shared database, with or without a db path.

    Returns:
        str: the same URL with the scratch db as its path.
    """
    return urlsplit(url)._replace(path=f"/{SCRATCH_DB}").geturl()


def compat_payload(dossier: Dossier) -> str:
    """Serialise a dossier the way an API running older code can validate it.

    Args:
        dossier: the rebuilt dossier.

    Returns:
        str: JSON without heading_path and dropped_non_prose, with no_prose
        sections stored as skipped.
    """
    data = json.loads(dossier.model_dump_json(exclude_none=True))
    for section in data["sections"]:
        section.pop("heading_path", None)
        section.pop("dropped_non_prose", None)
        if section["summary_state"] == "no_prose":
            section["summary_state"] = "skipped"
    return json.dumps(data)


def write_sidecars(out_dir: Path, dossier: Dossier, links: DossierLinks, fresh: Freshness) -> None:
    """Write the native dossier and the rendered views the other scripts read.

    The views are packed with summaries: scripts/eval/fidelity_check.py reads
    the summaries from after_cache, and md_after is read with them.

    Args:
        out_dir: the sidecar root.
        dossier: the rebuilt dossier.
        links: the links of the rendered views.
        fresh: the dossier's Freshness.
    """
    pid = dossier.topic.page_id
    (out_dir / "native").mkdir(parents=True, exist_ok=True)
    (out_dir / "native" / f"{pid}.json").write_text(dossier.model_dump_json(exclude_none=True))
    for name, budget in SIDECAR_BUDGETS:
        view = render.build_view(dossier, budget, fresh, links, include_summaries=True)
        (out_dir / name).mkdir(parents=True, exist_ok=True)
        if name == "after_cache":
            payload = json.dumps(view.model_dump(mode="json", by_alias=True, exclude_none=True))
            (out_dir / name / f"{pid}.json").write_text(payload)
        else:
            markdown = render.render_markdown(view, include_summaries=True)
            (out_dir / name / f"{pid}.md").write_text(markdown)


async def _rebuild(pid: int, ctx: Rebuild) -> dict[str, Any]:
    """Rebuild one dossier and store it unless dry_run is set.

    Args:
        pid: Wikipedia page id.
        ctx: the run's clients and options.

    Returns:
        dict[str, Any]: a summary printed as one JSON line.
    """
    shared, scratch = ctx.shared, ctx.scratch
    pv = settings.pipeline_version
    raw_ptr = await shared.get(keys.ptr(pid))
    if raw_ptr is None:
        return {"page_id": pid, "skipped": "no pointer to a stored revision"}
    rev = int(json.loads(raw_ptr)["rev_id"])
    dossier_key = keys.dossier(pid, rev, pv)
    raw = await shared.get(dossier_key)
    if raw is None:
        return {"page_id": pid, "rev_id": rev, "skipped": "no stored dossier at pinned revision"}
    old = Dossier.model_validate_json(raw)
    title = old.topic.title
    # redis-py leaves the **kwargs of flushdb and dbsize unannotated: unknown in strict mode.
    await ctx.scratch_raw.flushdb()  # pyright: ignore[reportUnknownMemberType]
    await scratch.set(MARKER, "1")
    for key in (keys.wm_html(rev), keys.wm_revts(rev), keys.wm_related(pid)):
        value = await shared.get(key)
        if value is not None:
            await scratch.set(key, value, ex=3600)
    queue = CaptureQueue(scratch, pv, settings.queue_cap, settings.background_queue_cap)
    now = datetime.now(UTC)
    job = Job(
        id=make_job_id(pid, rev, pv),
        page_id=pid,
        rev_id=rev,
        title=title,
        status="queued",
        stage="resolve",
        progress=JobProgress(done=0, total=TOTAL_STAGES),
        poll_after_ms=1000,
        partial_available=False,
        created_at=now,
        updated_at=now,
    )
    await queue.set_job(job)
    before_calls = ctx.calls[0]
    await run_build(
        job,
        redis=scratch,
        wikimedia=ctx.wm,
        ml=ctx.ml,
        job_queue=queue,
        pipeline_version=pv,
        summary_sections=settings.summary_sections,
        wikipedia_api_url=str(settings.wikipedia_api_url),
        background=True,
        public_host=settings.public_host,
        public_scheme=settings.public_scheme,
    )
    for section_id in list(queue.selected):
        await run_summary_item(
            job.id,
            section_id,
            redis=scratch,
            job_queue=queue,
            ml=ctx.ml,
            pipeline_version=pv,
            num_beams=settings.num_beams,
        )
    new = Dossier.model_validate_json(await scratch.get(dossier_key) or "")
    fresh = await freshness_mod.compute_freshness(shared, pid, rev, new.build.built_at)
    base = f"{settings.public_scheme}://{settings.public_host}/api/v1/dossiers/{pid}"
    links = DossierLinks(
        self=_HTTP_URL.validate_python(base),
        pinned=_HTTP_URL.validate_python(f"{base}/rev/{rev}"),
        markdown=_HTTP_URL.validate_python(f"{base}.md"),
        wikipedia=new.topic.url,
    )
    write_sidecars(ctx.out_dir, new, links, fresh)
    stored = new.model_dump_json(exclude_none=True) if ctx.native else compat_payload(new)
    if not ctx.dry_run:
        await shared.set(dossier_key, stored, ex=keys.DOSSIER_TTL_SECONDS)
    return {
        "page_id": pid,
        "title": title,
        "rev_id": rev,
        "wikimedia_calls": ctx.calls[0] - before_calls,
        "chunks_before": len(old.chunks),
        "chunks_after": len(new.chunks),
        "sections": len(new.sections),
        "states": {
            s: sum(1 for x in new.sections if x.summary_state == s)
            for s in sorted({x.summary_state for x in new.sections})
        },
        "stored": "dry-run" if ctx.dry_run else ("native" if ctx.native else "compat"),
    }


def _parse_args() -> argparse.Namespace:
    """Parse the command line.

    Returns:
        argparse.Namespace: the parsed command line.
    """
    parser = argparse.ArgumentParser(
        description="Rebuild stored dossiers in place from their pinned revisions."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ids", type=int, nargs="+", metavar="PAGE_ID", help="page ids to rebuild")
    group.add_argument("--all", action="store_true", help="rebuild every id in the tracked set")
    parser.add_argument(
        "--native",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="store the new schema as is (default); --no-native or --compat stores a compat copy",
    )
    parser.add_argument("--compat", dest="native", action="store_false", help="same as --no-native")
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="directory for the native, after_cache and md_after copies",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="run the pipeline and write sidecar files, but do not write back to the shared db",
    )
    return parser.parse_args()


async def main() -> None:
    """Rebuild the selected dossiers and print one JSON line per page."""
    opts = _parse_args()
    url = str(settings.redis_url)
    scratch_target = scratch_url(url)
    if scratch_target == url:
        raise SystemExit(f"redis db {SCRATCH_DB} is the shared db; aborting")
    shared_raw = default_redis_factory(url)
    scratch_raw = default_redis_factory(scratch_target)
    shared = RedisClient(shared_raw)
    scratch = RedisClient(scratch_raw)
    # redis-py leaves the **kwargs of dbsize unannotated: unknown in strict mode.
    if await scratch_raw.dbsize() and not await scratch.exists(MARKER):  # pyright: ignore[reportUnknownMemberType]
        raise SystemExit(f"redis db {SCRATCH_DB} is in use by something else; aborting")
    ids: list[int] = (
        sorted(int(x) for x in await shared.smembers(keys.TRACKED)) if opts.all else opts.ids
    )
    calls = [0]

    async def count(_request: httpx.Request) -> None:
        # httpx event hook: the request itself is not inspected, only counted.
        calls[0] += 1

    wm_http = httpx.AsyncClient(
        headers={"User-Agent": build_user_agent()},
        timeout=15.0,
        event_hooks={"request": [count]},
    )
    wm = WikimediaClient(
        wm_http,
        shared,
        str(settings.wikipedia_api_url),
        str(settings.wikipedia_rest_url),
        settings.wm_budget_per_minute,
    )
    ml_http = httpx.AsyncClient(base_url=str(settings.ml_url), timeout=60.0)
    ctx = Rebuild(
        shared=shared,
        scratch=scratch,
        scratch_raw=scratch_raw,
        wm=wm,
        ml=PatientML(ml_http),
        calls=calls,
        out_dir=opts.out,
        native=opts.native,
        dry_run=opts.dry_run,
    )
    try:
        for pid in ids:
            print(json.dumps(await _rebuild(pid, ctx)))
            await asyncio.sleep(1.0)
    finally:
        await scratch_raw.flushdb()  # pyright: ignore[reportUnknownMemberType]
        await wm_http.aclose()
        await ml_http.aclose()
        await shared.aclose()
        await scratch.aclose()


if __name__ == "__main__":
    asyncio.run(main())
