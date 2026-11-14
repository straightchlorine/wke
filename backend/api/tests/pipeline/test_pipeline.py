"""Build pipeline: partial persistence, summary failure, ML-down structural mode, progress."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from tests.support.builds import (
    build_only,
    make_queue,
    queued_summary_items,
    run_queued_summaries,
    run_summary,
    stored_dossier,
)
from tests.support.constants import (
    FIXTURE_PAGE_ID,
    FIXTURE_REV_ID,
    FIXTURE_REV_TIMESTAMP,
    FIXTURE_TITLE,
    PIPELINE_VERSION,
)
from tests.support.jobs import make_job
from tests.support.ml_clients import (
    analyze_down_client,
    make_ml_client,
    summarize_down_client,
)
from tests.support.ml_payloads import analyze_response_json
from tests.support.wikimedia import WmFixtures
from wke.clients.ml import MLClient
from wke.clients.redis import RedisClient
from wke.clients.wikimedia import WikimediaClient
from wke.core import keys, pack
from wke.core.models import Chunk, MachineSummary, MachineSummaryParams, Section
from wke.jobs.build.constants import (
    ANALYZE_MAX_EDGES,
    SUMMARY_MAX_LENGTH,
    SUMMARY_MIN_LENGTH,
    SUMMARY_MODEL,
    SUMMARY_MODEL_REVISION,
)
from wke.jobs.build.run import run_build
from wke.jobs.build.summarize import summarize_section


async def test_partial_persisted_before_any_summary(
    redis_client: RedisClient, wikimedia_client: WikimediaClient, ml_client_ok: MLClient
) -> None:
    job = make_job()
    await build_only(redis_client, wikimedia_client, ml_client_ok, job, summary_sections=3)

    dossier = await stored_dossier(redis_client, job)
    assert dossier.build.state == "partial"
    assert dossier.sections
    for section in dossier.sections:
        assert section.summary_state == ("pending" if section.chunk_ids else "no_prose")
        for chunk in (c for c in dossier.chunks if c.id in section.chunk_ids):
            assert chunk.heading_path == section.heading_path
        assert bool(section.heading_path) == (section.label_source != "article_title")
    assert any(s.summary_state == "no_prose" for s in dossier.sections)
    scores = pack.section_importance(dossier.sections, dossier.chunks)
    for section in dossier.sections:
        assert section.importance == pytest.approx(scores[section.id])
    assert any(s.importance > 0 for s in dossier.sections)

    queued = await queued_summary_items(redis_client)
    assert len(queued) == dossier.build.summaries_total
    assert dossier.build.summaries_total > 0

    seed_pin = next(c.pin for c in dossier.citations if c.role == "seed")
    assert seed_pin.rev_timestamp != seed_pin.retrieved_at
    assert seed_pin.rev_timestamp == datetime.fromisoformat(FIXTURE_REV_TIMESTAMP)


async def test_summary_failure_marks_unavailable_and_job_done(
    redis_client: RedisClient, wikimedia_client: WikimediaClient, ml_client_ok: MLClient
) -> None:
    job = make_job()
    queue = await build_only(redis_client, wikimedia_client, ml_client_ok, job)
    [item] = await queued_summary_items(redis_client)

    await run_summary(redis_client, queue, summarize_down_client(), item)

    dossier = await stored_dossier(redis_client, job)
    section = next(s for s in dossier.sections if s.id == item.split(":", 1)[1])
    assert section.summary_state == "unavailable"
    assert section.summary is None
    assert dossier.build.state == "complete"
    updated_job = await queue.get_job(job.id)
    assert updated_job is not None
    assert updated_job.status == "done"


async def test_ml_down_falls_back_to_structural_with_short_ttl(
    redis_client: RedisClient, wikimedia_client: WikimediaClient
) -> None:
    job = make_job()
    queue = await build_only(
        redis_client,
        wikimedia_client,
        analyze_down_client(),
        job,
        public_host="wke.example.test",
        public_scheme="http",
    )

    dossier = await stored_dossier(redis_client, job)
    assert dossier.build.analysis == "structural"
    assert dossier.build.state == "complete"
    assert dossier.graph.edges == []
    assert all(
        s.summary_state == ("unavailable" if s.chunk_ids else "no_prose") for s in dossier.sections
    )
    ttl = await redis_client.ttl(keys.dossier(job.page_id, FIXTURE_REV_ID, PIPELINE_VERSION))
    assert 0 < ttl <= keys.DOSSIER_STRUCTURAL_TTL_SECONDS

    final = await queue.get_job(job.id)
    assert final is not None
    assert final.status == "done"
    assert final.progress.done == final.progress.total > 0
    assert (
        str(final.result_url)
        == f"http://wke.example.test/api/v1/dossiers/{job.page_id}?budget=8000"
    )


async def test_finalize_records_stage_seconds(
    redis_client: RedisClient, wikimedia_client: WikimediaClient, ml_client_ok: MLClient
) -> None:
    job = make_job()
    queue = await build_only(redis_client, wikimedia_client, ml_client_ok, job)
    await run_queued_summaries(redis_client, queue, ml_client_ok)

    dossier = await stored_dossier(redis_client, job)
    assert dossier.build.state == "complete"
    stage_seconds = dossier.build.stage_seconds
    assert stage_seconds is not None
    assert stage_seconds["total"] == pytest.approx(
        stage_seconds["build"] + stage_seconds["summarize"]
    )


async def test_summary_item_ignores_ml_reported_input_chunk_ids(
    redis_client: RedisClient, wikimedia_client: WikimediaClient, ml_client_ok: MLClient
) -> None:
    """wke-ml gets raw text, so the chunk ids it reports back are replaced by the local ones."""
    job = make_job()
    queue = await build_only(redis_client, wikimedia_client, ml_client_ok, job)
    [item] = await queued_summary_items(redis_client)
    await run_summary(redis_client, queue, ml_client_ok, item)

    dossier = await stored_dossier(redis_client, job)
    section = next(s for s in dossier.sections if s.id == item.split(":", 1)[1])
    assert section.summary is not None
    assert section.summary.input_chunk_ids != ["ml-reported-1"]
    assert section.summary.input_chunk_ids
    assert set(section.summary.input_chunk_ids) <= set(section.chunk_ids)


async def test_cached_summary_hit_gets_current_input_chunk_ids(
    redis_client: RedisClient,
) -> None:
    """A cache hit carries ids of another revision's chunks; they are replaced."""
    chunk = Chunk(
        id="9999999999:career:0",
        citation_id="c1",
        heading_path=["Career"],
        order=0,
        text="Turing worked at Bletchley Park.",
        est_tokens=8,
        relevance=1.0,
    )
    section = Section(
        id="s1",
        label="Career",
        label_source="heading",
        chunk_ids=[chunk.id],
        summary_state="pending",
    )
    params_str = f"beams=1|min={SUMMARY_MIN_LENGTH}|max={SUMMARY_MAX_LENGTH}"
    cache_key = keys.sum_key(chunk.text, SUMMARY_MODEL, SUMMARY_MODEL_REVISION, params_str)
    stale_summary = MachineSummary(
        text="A stale cached summary.",
        model=SUMMARY_MODEL,
        model_revision=SUMMARY_MODEL_REVISION,
        params=MachineSummaryParams(num_beams=1, min_length=30, max_length=96),
        input_chunk_ids=["1111111111:career:0"],
        generated_at=datetime.now(UTC),
    )
    await redis_client.set(cache_key, stale_summary.model_dump_json(), ex=keys.SUMMARY_TTL_SECONDS)

    def never_called(request: httpx.Request) -> httpx.Response:
        pytest.fail(f"wke-ml called on a cache hit: {request.url}")

    await summarize_section(
        redis_client, make_ml_client(never_called), section, [chunk], num_beams=1
    )

    assert section.summary_state == "done"
    assert section.summary is not None
    assert section.summary.input_chunk_ids == [chunk.id]
    assert section.summary.text == "A stale cached summary."


def _fake_relevance(i: int, n: int) -> float:
    """Return a strictly decreasing relevance in (0, 1] for chunk i of n."""
    return round(1.0 - i / (n + 1), 4)


async def test_analyze_request_and_response_are_wired(
    redis_client: RedisClient, wikimedia_client: WikimediaClient, wm_fixtures: WmFixtures
) -> None:
    """The request carries page id and edge cap; the response maps onto chunks by id."""
    related_id = wm_fixtures.json("morelike.json")["query"]["pages"][0]["pageid"]
    job = make_job()
    captured: dict[str, Any] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path != "/v1/analyze":
            return httpx.Response(404)
        payload = json.loads(request.content)
        captured["payload"] = payload
        chunk_ids = [c["id"] for c in payload["chunks"]]
        body: dict[str, Any] = analyze_response_json()
        body["relevance"] = {
            cid: _fake_relevance(i, len(chunk_ids)) for i, cid in enumerate(chunk_ids)
        }
        body["cluster_ids"] = {cid: i % 3 for i, cid in enumerate(chunk_ids)}
        body["edges"] = [{"source": job.page_id, "target": related_id, "weight": 0.42}]
        return httpx.Response(200, json=body)

    await build_only(redis_client, wikimedia_client, make_ml_client(handle), job)

    payload = captured["payload"]
    assert payload["page_id"] == job.page_id
    assert payload["max_edges"] == ANALYZE_MAX_EDGES
    dossier = await stored_dossier(redis_client, job)
    sent_chunk_ids = [c["id"] for c in payload["chunks"]]
    assert sent_chunk_ids, "fixture must have parsed at least one chunk"
    by_id = {chunk.id: chunk for chunk in dossier.chunks}
    for i, chunk_id in enumerate(sent_chunk_ids):
        assert by_id[chunk_id].relevance == _fake_relevance(i, len(sent_chunk_ids))
        assert by_id[chunk_id].cluster_id == i % 3
    [edge] = dossier.graph.edges
    assert (edge.source, edge.target, edge.weight) == (job.page_id, related_id, 0.42)


async def test_progress_advances_monotonically_and_completes_at_done(
    redis_client: RedisClient, wikimedia_client: WikimediaClient, ml_client_ok: MLClient
) -> None:
    job = make_job()
    assert job.progress.done == 0
    queue = await build_only(redis_client, wikimedia_client, ml_client_ok, job, summary_sections=2)

    after_build = await queue.get_job(job.id)
    assert after_build is not None
    assert 0 < after_build.progress.done < after_build.progress.total
    assert after_build.result_url is None

    base = after_build.progress.done
    seen = [base]
    items = await queued_summary_items(redis_client)
    assert items
    for item in items:
        await run_summary(redis_client, queue, ml_client_ok, item)
        current = await queue.get_job(job.id)
        assert current is not None
        seen.append(current.progress.done)

    # One step per summary item; the last item also completes the finalize step.
    assert seen == [base + i for i in range(len(items))] + [base + len(items) + 1]
    final = await queue.get_job(job.id)
    assert final is not None
    assert final.status == "done"
    assert final.progress.done == final.progress.total


async def test_result_url_is_set_on_partial_and_final_persist(
    redis_client: RedisClient, wikimedia_client: WikimediaClient, ml_client_ok: MLClient
) -> None:
    job = make_job()
    expected = f"http://wke.example.test/api/v1/dossiers/{job.page_id}?budget=8000"
    queue = await build_only(
        redis_client,
        wikimedia_client,
        ml_client_ok,
        job,
        public_host="wke.example.test",
        public_scheme="http",
    )
    after_build = await queue.get_job(job.id)
    assert after_build is not None
    assert str(after_build.result_url) == expected

    await run_queued_summaries(redis_client, queue, ml_client_ok)

    final = await queue.get_job(job.id)
    assert final is not None
    assert final.status == "done"
    assert str(final.result_url) == expected


async def test_invalid_analyze_relevance_fails_job_and_leaves_no_dossier(
    redis_client: RedisClient, wikimedia_client: WikimediaClient, caplog: pytest.LogCaptureFixture
) -> None:
    """Relevance past [0, 1] fails the job and cleans up without persisting."""
    caplog.set_level("WARNING", logger="wke.jobs.build.failure")

    def handle(request: httpx.Request) -> httpx.Response:
        body: dict[str, Any] = analyze_response_json()
        chunk_ids = [c["id"] for c in json.loads(request.content)["chunks"]]
        body["relevance"] = {cid: 1.5 for cid in chunk_ids}
        return httpx.Response(200, json=body)

    queue = make_queue(redis_client)
    first = await queue.admit(FIXTURE_PAGE_ID, FIXTURE_REV_ID, FIXTURE_TITLE)
    assert first != "ready"

    with pytest.raises(ValidationError):
        await run_build(
            first,
            redis=redis_client,
            wikimedia=wikimedia_client,
            ml=make_ml_client(handle),
            job_queue=queue,
            pipeline_version=PIPELINE_VERSION,
            summary_sections=1,
            wikipedia_api_url="https://en.wikipedia.org/w/api.php",
            background=False,
        )

    failed_job = await queue.get_job(first.id)
    assert failed_job is not None
    assert failed_job.status == "failed"
    assert failed_job.error is not None
    # A non-ApiException exception is a bug: its message never reaches the polling client.
    assert failed_job.error.detail == "Build failed; see server logs with this request_id."
    assert failed_job.error.code == "internal"
    assert (
        await redis_client.get(keys.dossier(FIXTURE_PAGE_ID, FIXTURE_REV_ID, PIPELINE_VERSION))
        is None
    )
    assert await redis_client.get(keys.jobkey(FIXTURE_PAGE_ID, FIXTURE_REV_ID)) is None

    [record] = [r for r in caplog.records if r.message.startswith("job_failed ")]
    assert record.message == (
        f"job_failed job_id={first.id} page_id={FIXTURE_PAGE_ID} "
        f"rev_id={FIXTURE_REV_ID} code=internal"
    )

    second = await queue.admit(FIXTURE_PAGE_ID, FIXTURE_REV_ID, FIXTURE_TITLE)
    assert second != "ready"
    assert (second.status, second.error, second.progress.done) == ("queued", None, 0)


async def test_background_build_queues_its_summary_items_on_the_background_list(
    redis_client: RedisClient, wikimedia_client: WikimediaClient, ml_client_ok: MLClient
) -> None:
    await build_only(redis_client, wikimedia_client, ml_client_ok, make_job(), background=True)

    assert await redis_client.lrange(keys.QUEUE_SUM_BACKGROUND, 0, -1)
    assert await queued_summary_items(redis_client) == []
