"""Summarising one section: cache use, unusable model output and the items of a job."""

from __future__ import annotations

import logging

import httpx
import pytest
from pydantic import ValidationError

from tests.factories.dossier import make_fixture_dossier
from tests.support.builds import (
    build_only,
    make_queue,
    queued_summary_items,
    run_summary,
    stored_dossier,
)
from tests.support.constants import JOB_ID, PIPELINE_VERSION
from tests.support.jobs import make_job
from tests.support.ml_clients import make_ml_client
from tests.support.ml_payloads import summarize_response_json
from wke.clients.ml import MLClient
from wke.clients.redis import RedisClient
from wke.clients.wikimedia import WikimediaClient
from wke.core import keys
from wke.core.models import Chunk, ChunkKind, Section
from wke.jobs.build.constants import SUMMARY_INPUT_CHAR_CAP
from wke.jobs.build.payload import dossier_payload
from wke.jobs.build.summarize import summarize_section, summary_input


def _chunk(order: int, text: str, kind: ChunkKind = "prose") -> Chunk:
    return Chunk(
        id=f"1:s:{order}",
        citation_id="c1",
        heading_path=["Career"],
        order=order,
        text=text,
        est_tokens=max(1, len(text) // 4),
        relevance=0.5,
        kind=kind,
    )


def _section(*chunks: Chunk) -> Section:
    return Section(
        id="s1",
        label="Career",
        label_source="heading",
        chunk_ids=[c.id for c in chunks],
        heading_path=["Career"],
        summary_state="pending",
    )


def _counting_ml(calls: list[str], **body: object) -> MLClient:
    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json=summarize_response_json() | body)

    return make_ml_client(handle)


def test_summary_input_reads_prose_in_order_up_to_the_character_cap() -> None:
    first = _chunk(0, "First passage.")
    table = _chunk(1, "A table row", kind="table")
    huge = _chunk(2, "x" * SUMMARY_INPUT_CHAR_CAP)
    last = _chunk(3, "Last passage.")
    section = _section(last, table, huge, first)

    text, ids = summary_input(section, [first, table, huge, last])

    assert (text, ids) == ("First passage.", [first.id])


@pytest.mark.parametrize(("truncated", "ml_calls"), [(False, 1), (True, 2)])
async def test_only_a_complete_summary_is_cached(
    redis_client: RedisClient, truncated: bool, ml_calls: int
) -> None:
    chunk = _chunk(0, "Turing worked at Bletchley Park.")
    calls: list[str] = []
    ml = _counting_ml(calls, text="Turing worked at Bletchley Park.", truncated=truncated)

    for _ in range(2):
        await summarize_section(redis_client, ml, _section(chunk), [chunk], num_beams=1)

    assert len(calls) == ml_calls


@pytest.mark.parametrize("missing", ["text", "model", "model_revision"])
async def test_ml_answer_missing_its_provenance_gives_no_summary(
    redis_client: RedisClient, missing: str
) -> None:
    chunk = _chunk(0, "Turing worked at Bletchley Park.")
    section = _section(chunk)
    calls: list[str] = []
    ml = _counting_ml(calls, **{missing: ""})

    await summarize_section(redis_client, ml, section, [chunk], num_beams=1)
    await summarize_section(redis_client, ml, _section(chunk), [chunk], num_beams=1)

    assert (section.summary, section.summary_state) == (None, "unavailable")
    assert len(calls) == 2


async def test_section_without_prose_is_skipped_without_calling_the_model(
    redis_client: RedisClient,
) -> None:
    table = _chunk(0, "A table row", kind="table")
    section = _section(table)

    def never_called(request: httpx.Request) -> httpx.Response:
        pytest.fail(f"wke-ml called for a section without prose: {request.url}")

    await summarize_section(redis_client, make_ml_client(never_called), section, [table], 1)

    assert (section.summary, section.summary_state) == (None, "skipped")


@pytest.mark.parametrize("case", ["job", "dossier", "section"])
async def test_item_for_something_missing_is_dropped_without_failing_the_job(
    redis_client: RedisClient,
    wikimedia_client: WikimediaClient,
    ml_client_ok: MLClient,
    caplog: pytest.LogCaptureFixture,
    case: str,
) -> None:
    caplog.set_level(logging.WARNING, logger="wke.jobs.build.summarize")
    queue = make_queue(redis_client)
    job = make_job()
    if case == "job":
        item = f"{JOB_ID}:s1"
    else:
        queue = await build_only(redis_client, wikimedia_client, ml_client_ok, job)
        [real_item] = await queued_summary_items(redis_client)
        if case == "dossier":
            assert job.rev_id is not None
            await redis_client.delete(keys.dossier(job.page_id, job.rev_id, PIPELINE_VERSION))
        item = real_item if case == "dossier" else f"{job.id}:no-such-section"

    await run_summary(redis_client, queue, ml_client_ok, item)

    assert "summary item for" in caplog.text
    stored = await queue.get_job(job.id)
    assert stored is None or stored.status != "failed"


async def test_item_that_is_not_the_last_keeps_the_dossier_partial(
    redis_client: RedisClient, wikimedia_client: WikimediaClient, ml_client_ok: MLClient
) -> None:
    job = make_job()
    queue = await build_only(redis_client, wikimedia_client, ml_client_ok, job, summary_sections=3)
    items = await queued_summary_items(redis_client)
    assert len(items) > 1

    await run_summary(redis_client, queue, ml_client_ok, items[0])

    dossier = await stored_dossier(redis_client, job)
    assert dossier.build.state == "partial"
    assert dossier.build.summaries_done == 1
    stored = await queue.get_job(job.id)
    assert stored is not None
    assert stored.status == "running"


async def test_item_that_raises_fails_the_job_and_reraises(
    redis_client: RedisClient, wikimedia_client: WikimediaClient, ml_client_ok: MLClient
) -> None:
    job = make_job()
    queue = await build_only(redis_client, wikimedia_client, ml_client_ok, job)
    [item] = await queued_summary_items(redis_client)
    assert job.rev_id is not None
    await redis_client.set(keys.dossier(job.page_id, job.rev_id, PIPELINE_VERSION), "not json")

    with pytest.raises(ValidationError):
        await run_summary(redis_client, queue, ml_client_ok, item)

    stored = await queue.get_job(job.id)
    assert stored is not None
    assert stored.status == "failed"
    assert await redis_client.get(keys.jobkey(job.page_id, job.rev_id)) is None


async def test_summary_that_passes_the_check_clears_an_earlier_withheld_reason(
    redis_client: RedisClient,
) -> None:
    chunk = _chunk(0, "Turing worked at Bletchley Park.")
    section = _section(chunk)
    section.summary_state = "withheld"
    section.withheld_reason = "the text names an article that is not in the source"
    ml = _counting_ml([], text="Turing worked at Bletchley Park.")

    await summarize_section(redis_client, ml, section, [chunk], num_beams=1)

    assert (section.summary_state, section.withheld_reason) == ("done", None)


async def test_a_table_only_section_is_not_a_settled_summary(
    redis_client: RedisClient, ml_client_ok: MLClient
) -> None:
    """A section without prose is skipped from the start; it is no settled summary."""
    base = make_fixture_dossier()
    table = _chunk(0, "A table row", kind="table")
    table_only = Section(
        id="s9",
        label="Table",
        label_source="heading",
        chunk_ids=[table.id],
        heading_path=["Table"],
        summary_state="skipped",
    )
    for section in base.sections:
        section.summary_state = "pending"
        section.summary = None
    dossier = base.model_copy(
        update={"sections": [*base.sections, table_only], "chunks": [*base.chunks, table]}
    )
    dossier.build.state = "partial"
    dossier.build.summaries_total = 2
    dossier.build.summaries_done = 0
    job = make_job(page_id=dossier.topic.page_id, rev_id=7, status="running", stage="summarize")
    queue = make_queue(redis_client)
    await queue.set_job(job)
    await redis_client.set(keys.dossier(job.page_id, 7, PIPELINE_VERSION), dossier_payload(dossier))
    selected = [
        s.id
        for s in base.sections
        if any(c.kind == "prose" for c in base.chunks if c.id in s.chunk_ids)
    ]

    await run_summary(redis_client, queue, ml_client_ok, f"{job.id}:{selected[0]}")

    stored = await stored_dossier(redis_client, job)
    assert (stored.build.state, stored.build.summaries_done) == ("partial", 1)
    running = await queue.get_job(job.id)
    assert running is not None
    assert running.status == "running"

    await run_summary(redis_client, queue, ml_client_ok, f"{job.id}:{selected[1]}")

    assert (await stored_dossier(redis_client, job)).build.state == "complete"


async def test_selected_section_with_blank_text_is_skipped_and_still_settles_the_job(
    redis_client: RedisClient, ml_client_ok: MLClient
) -> None:
    blank = _chunk(0, "  ")
    section = _section(blank)
    dossier = make_fixture_dossier().model_copy(update={"sections": [section], "chunks": [blank]})
    dossier.build.state = "partial"
    dossier.build.summaries_total = 1
    job = make_job(page_id=dossier.topic.page_id, rev_id=7, status="running", stage="summarize")
    queue = make_queue(redis_client)
    await queue.set_job(job)
    await redis_client.set(keys.dossier(job.page_id, 7, PIPELINE_VERSION), dossier_payload(dossier))

    await run_summary(redis_client, queue, ml_client_ok, f"{job.id}:{section.id}")

    stored = await stored_dossier(redis_client, job)
    assert (stored.sections[0].summary_state, stored.build.state) == ("skipped", "complete")
