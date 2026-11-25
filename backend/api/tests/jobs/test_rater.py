"""The rating loop: one wke-ml call per prose passage, saving the stored rating after each."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from prometheus_client import REGISTRY

from tests.factories.dossier import make_fixture_dossier
from tests.support.builds import make_queue
from tests.support.constants import PIPELINE_VERSION
from tests.support.ml_clients import make_ml_client
from tests.support.services import renamed, seed_dossier
from wke.clients.ml import MLClient
from wke.clients.redis import RedisClient
from wke.core import keys
from wke.core.citations import seed_pin
from wke.jobs import rater as rater_module
from wke.jobs.build.constants import (
    RATING_MODEL,
    RATING_MODEL_FILE,
    RATING_PROMPT_SHA256,
)
from wke.jobs.build.rating import (
    RatingConfig,
    RatingDocument,
    parse_document,
    rating_key,
    rating_lock_key,
)
from wke.jobs.rater import Rater, RatingItem

DOSSIER = make_fixture_dossier()
PAGE_ID = DOSSIER.topic.page_id
REV_ID = seed_pin(DOSSIER).rev_id
ITEM = f"{PAGE_ID}:{REV_ID}"
PROSE = [c for c in DOSSIER.chunks if c.kind == "prose"]
KEY = rating_key(PAGE_ID, REV_ID, PIPELINE_VERSION)
CONFIG = RatingConfig(enabled=True, deadline_seconds=60, call_timeout_seconds=120)


def _reply(scores: dict[str, float | None], **overrides: Any) -> httpx.Response:
    body = {
        "model": RATING_MODEL_FILE,
        "prompt_sha256": RATING_PROMPT_SHA256,
        "scores": scores,
        "fallback_ids": [],
        "infer_seconds": 1.0,
        **overrides,
    }
    return httpx.Response(200, json=body)


class Ml:
    """A fake wke-ml whose n-th call scores n mod 4 unless `respond` is given; keeps requests."""

    def __init__(self, respond: Callable[[httpx.Request, int], httpx.Response] | None = None):
        self.requests: list[httpx.Request] = []
        self._respond = respond

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        body = json.loads(request.content)
        [passage] = body["passages"]
        if self._respond is not None:
            return self._respond(request, len(self.requests))
        return _reply({passage["id"]: float(len(self.requests) % 4)})

    def bodies(self) -> list[dict[str, Any]]:
        return [json.loads(r.content) for r in self.requests]


def _outcomes() -> dict[str, float]:
    names = ("done", "deadline", "ml_unavailable", "mismatch", "dossier_gone")
    return {
        n: REGISTRY.get_sample_value("wke_rating_stage_total", {"outcome": n}) or 0.0 for n in names
    }


async def _run(redis_client: RedisClient, ml: Ml, config: RatingConfig = CONFIG) -> None:
    """Run the loop until the queue q:rate and its in-progress list q:rate:processing are empty."""
    rater = Rater(redis_client, make_ml_client(ml), config, PIPELINE_VERSION)
    task = asyncio.create_task(rater.run_forever())
    try:
        for _ in range(500):
            await asyncio.sleep(0.01)
            queued = await redis_client.lrange(keys.QUEUE_RATE, 0, -1)
            if not await redis_client.llen(keys.QUEUE_RATE_PROCESSING) and not any(
                RatingItem.parse(v).due <= time.time() for v in queued
            ):
                break
        else:
            pytest.fail("the rating loop did not finish")
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.fixture(autouse=True)
def _no_retry_pause(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rater_module, "RATING_RETRY_PAUSE_SECONDS", 0)
    monkeypatch.setattr(rater_module, "REDIS_ERROR_PAUSE_SECONDS", 0)


async def _stored(redis_client: RedisClient) -> RatingDocument:
    document = parse_document(await redis_client.get(KEY))
    assert document is not None
    return document


async def test_every_prose_passage_is_rated_in_order_one_call_each(
    redis_client: RedisClient,
) -> None:
    await seed_dossier(redis_client, DOSSIER)
    await redis_client.rpush(keys.QUEUE_RATE, ITEM)
    ml = Ml()
    before = _outcomes()

    await _run(redis_client, ml)

    assert [b["passages"] for b in ml.bodies()] == [
        [{"id": c.id, "text": c.text.strip()}] for c in PROSE
    ]
    assert {b["title"] for b in ml.bodies()} == {DOSSIER.topic.title}
    lead = " ".join(c.text for c in PROSE if not c.heading_path)
    assert {b["lead"] for b in ml.bodies()} == {lead}
    document = await _stored(redis_client)
    assert document.done is True
    assert list(document.scores) == [c.id for c in PROSE]
    assert _outcomes()["done"] == before["done"] + 1
    assert await redis_client.ttl(KEY) > 6 * 24 * 3600


async def test_each_call_carries_the_call_timeout_as_its_deadline(
    redis_client: RedisClient,
) -> None:
    await seed_dossier(redis_client, DOSSIER)
    await redis_client.rpush(keys.QUEUE_RATE, ITEM)
    ml = Ml()

    await _run(redis_client, ml)

    assert {r.headers["X-Deadline-Ms"] for r in ml.requests} == {"120000"}
    assert {r.url.path for r in ml.requests} == {"/v1/rate"}


async def test_the_document_is_rewritten_after_each_passage(redis_client: RedisClient) -> None:
    await seed_dossier(redis_client, DOSSIER)
    await redis_client.rpush(keys.QUEUE_RATE, ITEM)
    stored_before_call: list[int | None] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        document = parse_document(await redis_client.get(KEY))
        stored_before_call.append(None if document is None else len(document.scores))
        [passage] = json.loads(request.content)["passages"]
        return _reply({passage["id"]: 2.0})

    http = httpx.AsyncClient(transport=httpx.MockTransport(respond), base_url="http://wke-ml.test")
    rater = Rater(redis_client, MLClient(http), CONFIG, PIPELINE_VERSION)
    task = asyncio.create_task(rater.run_forever())
    for _ in range(500):
        await asyncio.sleep(0.01)
        if not await redis_client.llen(keys.QUEUE_RATE_PROCESSING) and len(
            stored_before_call
        ) == len(PROSE):
            break
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert stored_before_call == [None, *range(1, len(PROSE))]


async def test_a_stage_resumes_from_the_passages_already_stored(
    redis_client: RedisClient,
) -> None:
    await seed_dossier(redis_client, DOSSIER)
    stored = {PROSE[0].id: 1.0, PROSE[1].id: None}
    await redis_client.set(
        KEY,
        RatingDocument(
            prompt_sha256=RATING_PROMPT_SHA256, model=RATING_MODEL, done=False, scores=stored
        ).model_dump_json(),
    )
    await redis_client.rpush(keys.QUEUE_RATE, ITEM)
    ml = Ml()

    await _run(redis_client, ml)

    assert [b["passages"][0]["id"] for b in ml.bodies()] == [c.id for c in PROSE[2:]]
    document = await _stored(redis_client)
    assert document.done is True
    assert document.scores[PROSE[0].id] == 1.0
    assert document.scores[PROSE[1].id] is None


async def test_a_second_attempt_does_not_write_its_partial_copy_over_a_finished_document(
    redis_client: RedisClient,
) -> None:
    await seed_dossier(redis_client, DOSSIER)
    await redis_client.rpush(keys.QUEUE_RATE, ITEM)
    finished = RatingDocument(
        prompt_sha256=RATING_PROMPT_SHA256,
        model=RATING_MODEL,
        done=True,
        scores={c.id: 3.0 for c in PROSE},
    )
    calls: list[int] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        await redis_client.set(KEY, finished.model_dump_json())
        [passage] = json.loads(request.content)["passages"]
        return _reply({passage["id"]: 0.0})

    http = httpx.AsyncClient(transport=httpx.MockTransport(respond), base_url="http://wke-ml.test")
    rater = Rater(redis_client, MLClient(http), CONFIG, PIPELINE_VERSION)
    task = asyncio.create_task(rater.run_forever())
    for _ in range(500):
        await asyncio.sleep(0.01)
        if calls and not await redis_client.llen(keys.QUEUE_RATE_PROCESSING):
            break
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert len(calls) == 1
    assert await _stored(redis_client) == finished


async def test_ids_of_a_document_that_are_no_prose_chunk_of_the_dossier_are_dropped(
    redis_client: RedisClient,
) -> None:
    await seed_dossier(redis_client, DOSSIER)
    scores = {c.id: 1.0 for c in PROSE} | {"gone:chunk": 3.0}
    await redis_client.set(
        KEY,
        RatingDocument(
            prompt_sha256=RATING_PROMPT_SHA256, model=RATING_MODEL, done=False, scores=scores
        ).model_dump_json(),
    )
    await redis_client.rpush(keys.QUEUE_RATE, ITEM)
    ml = Ml()

    await _run(redis_client, ml)

    assert ml.requests == []
    document = await _stored(redis_client)
    assert document.done is True
    assert set(document.scores) == {c.id for c in PROSE}


async def test_a_document_of_another_prompt_is_started_over(redis_client: RedisClient) -> None:
    await seed_dossier(redis_client, DOSSIER)
    await redis_client.set(
        KEY,
        RatingDocument(
            prompt_sha256="0" * 64, model=RATING_MODEL, done=True, scores={PROSE[0].id: 3.0}
        ).model_dump_json(),
    )
    await redis_client.rpush(keys.QUEUE_RATE, ITEM)
    ml = Ml()

    await _run(redis_client, ml)

    assert len(ml.requests) == len(PROSE)
    assert (await _stored(redis_client)).prompt_sha256 == RATING_PROMPT_SHA256


async def test_a_dossier_that_expired_is_dropped_and_counted(redis_client: RedisClient) -> None:
    await redis_client.rpush(keys.QUEUE_RATE, ITEM)
    ml = Ml()
    before = _outcomes()

    await _run(redis_client, ml)

    assert ml.requests == []
    assert await redis_client.get(KEY) is None
    assert _outcomes()["dossier_gone"] == before["dossier_gone"] + 1


async def test_a_failed_call_is_tried_three_times_then_the_stage_ends_keeping_the_passages(
    redis_client: RedisClient,
) -> None:
    await seed_dossier(redis_client, DOSSIER)
    await redis_client.rpush(keys.QUEUE_RATE, ITEM)

    def respond(request: httpx.Request, n: int) -> httpx.Response:
        if n <= 2:
            [passage] = json.loads(request.content)["passages"]
            return _reply({passage["id"]: 2.0})
        return httpx.Response(503)

    ml = Ml(respond)
    before = _outcomes()

    await _run(redis_client, ml)

    assert len(ml.requests) == 2 + 3
    document = await _stored(redis_client)
    assert document.done is False
    assert list(document.scores) == [PROSE[0].id, PROSE[1].id]
    assert _outcomes()["ml_unavailable"] == before["ml_unavailable"] + 1
    assert await redis_client.llen(keys.QUEUE_RATE_PROCESSING) == 0


async def test_a_call_that_fails_twice_and_then_answers_is_kept(
    redis_client: RedisClient,
) -> None:
    await seed_dossier(redis_client, DOSSIER)
    await redis_client.rpush(keys.QUEUE_RATE, ITEM)

    def respond(request: httpx.Request, n: int) -> httpx.Response:
        if n <= 2:
            return httpx.Response(503)
        [passage] = json.loads(request.content)["passages"]
        return _reply({passage["id"]: 2.0})

    ml = Ml(respond)

    await _run(redis_client, ml)

    assert len(ml.requests) == 2 + len(PROSE)
    assert (await _stored(redis_client)).done is True


async def test_a_prompt_that_does_not_fit_scores_null_without_a_retry(
    redis_client: RedisClient,
) -> None:
    await seed_dossier(redis_client, DOSSIER)
    await redis_client.rpush(keys.QUEUE_RATE, ITEM)

    def respond(request: httpx.Request, n: int) -> httpx.Response:
        if n == 2:
            return httpx.Response(422)
        [passage] = json.loads(request.content)["passages"]
        return _reply({passage["id"]: 1.0})

    ml = Ml(respond)

    await _run(redis_client, ml)

    assert len(ml.requests) == len(PROSE)
    document = await _stored(redis_client)
    assert document.scores[PROSE[1].id] is None
    assert document.done is True


async def test_a_null_score_from_wke_ml_is_stored_as_null(redis_client: RedisClient) -> None:
    await seed_dossier(redis_client, DOSSIER)
    await redis_client.rpush(keys.QUEUE_RATE, ITEM)

    def respond(request: httpx.Request, n: int) -> httpx.Response:
        [passage] = json.loads(request.content)["passages"]
        return _reply({passage["id"]: None}, fallback_ids=[passage["id"]])

    await _run(redis_client, Ml(respond))

    assert set((await _stored(redis_client)).scores.values()) == {None}


@pytest.mark.parametrize(
    "override",
    [{"prompt_sha256": "0" * 64}, {"model": "other-model.gguf"}],
    ids=["prompt", "model"],
)
async def test_an_answer_under_another_prompt_or_model_ends_the_stage(
    redis_client: RedisClient, override: dict[str, Any]
) -> None:
    await seed_dossier(redis_client, DOSSIER)
    await redis_client.rpush(keys.QUEUE_RATE, ITEM)

    def respond(request: httpx.Request, n: int) -> httpx.Response:
        [passage] = json.loads(request.content)["passages"]
        return _reply({passage["id"]: 2.0}, **(override if n == 2 else {}))

    ml = Ml(respond)
    before = _outcomes()

    await _run(redis_client, ml)

    assert len(ml.requests) == 2
    document = await _stored(redis_client)
    assert list(document.scores) == [PROSE[0].id]
    assert document.done is False
    assert _outcomes()["mismatch"] == before["mismatch"] + 1


async def test_an_attempt_over_the_deadline_stops_and_keeps_what_it_has(
    redis_client: RedisClient,
) -> None:
    await seed_dossier(redis_client, DOSSIER)
    await redis_client.rpush(keys.QUEUE_RATE, ITEM)
    transport_calls: list[int] = []

    async def slow(request: httpx.Request) -> httpx.Response:
        transport_calls.append(1)
        [passage] = json.loads(request.content)["passages"]
        if len(transport_calls) == 3:
            await asyncio.sleep(10)
        return _reply({passage["id"]: 2.0})

    http = httpx.AsyncClient(transport=httpx.MockTransport(slow), base_url="http://wke-ml.test")
    rater = Rater(
        redis_client,
        MLClient(http),
        RatingConfig(enabled=True, deadline_seconds=1, call_timeout_seconds=120),
        PIPELINE_VERSION,
    )
    before = _outcomes()
    task = asyncio.create_task(rater.run_forever())
    for _ in range(400):
        await asyncio.sleep(0.01)
        if _outcomes()["deadline"] > before["deadline"]:
            break
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert _outcomes()["deadline"] == before["deadline"] + 1
    document = await _stored(redis_client)
    assert document.done is False
    assert list(document.scores) == [PROSE[0].id, PROSE[1].id]


async def test_an_item_left_in_processing_by_a_stopped_rater_is_taken_again(
    redis_client: RedisClient,
) -> None:
    await seed_dossier(redis_client, DOSSIER)
    await redis_client.rpush(keys.QUEUE_RATE_PROCESSING, ITEM)
    ml = Ml()

    await _run(redis_client, ml)

    assert len(ml.requests) == len(PROSE)
    assert (await _stored(redis_client)).done is True


async def test_a_dossier_without_prose_is_done_without_a_call(redis_client: RedisClient) -> None:
    empty = DOSSIER.model_copy(update={"chunks": [c for c in DOSSIER.chunks if c.kind != "prose"]})
    await seed_dossier(redis_client, empty)
    await redis_client.rpush(keys.QUEUE_RATE, ITEM)
    ml = Ml()

    await _run(redis_client, ml)

    assert ml.requests == []
    document = await _stored(redis_client)
    assert (document.done, document.scores) == (True, {})


async def test_an_item_that_raises_is_logged_and_removed(
    redis_client: RedisClient, caplog: pytest.LogCaptureFixture
) -> None:
    await redis_client.rpush(keys.QUEUE_RATE, "not-an-item")

    await _run(redis_client, Ml())

    assert "rating item failed: not-an-item" in caplog.text


# --- a stage that ends before every passage is rated: lock released, item queued again ---

LOCK = rating_lock_key(PAGE_ID, REV_ID, PIPELINE_VERSION)
HEARTBEAT = keys.rating_heartbeat(PAGE_ID, REV_ID)
SAFETY_NET_SECONDS = 30  # upper bound on waits, so a broken test fails instead of hanging


async def _lock_and_queue(redis_client: RedisClient) -> None:
    """Queue the rating item, which also takes the per-revision rating lock, as a build does."""
    await make_queue(redis_client).enqueue_rating(PAGE_ID, REV_ID, 2400)
    assert await redis_client.get(LOCK) is not None


async def _until(predicate: Callable[[], Any], what: str) -> None:
    for _ in range(500):
        if await predicate():
            return
        await asyncio.sleep(0.01)
    pytest.fail(f"did not happen: {what}")


async def test_an_unavailable_ml_releases_the_lock_and_requeues_the_stage_with_a_backoff(
    redis_client: RedisClient,
) -> None:
    await seed_dossier(redis_client, DOSSIER)
    await _lock_and_queue(redis_client)
    before = time.time()

    await _run(redis_client, Ml(lambda _r, _n: httpx.Response(503)))

    assert await redis_client.get(LOCK) is None
    [queued] = await redis_client.lrange(keys.QUEUE_RATE, 0, -1)
    retry = RatingItem.parse(queued)
    assert (retry.page_id, retry.rev_id, retry.failures) == (PAGE_ID, REV_ID, 1)
    assert before + 59 < retry.due < time.time() + 61


async def test_a_retry_that_is_not_due_makes_no_call_and_stays_queued(
    redis_client: RedisClient,
) -> None:
    await seed_dossier(redis_client, DOSSIER)
    waiting = RatingItem(PAGE_ID, REV_ID, 1, time.time() + 3600).encode()
    await redis_client.rpush(keys.QUEUE_RATE, waiting)
    ml = Ml()

    await _run(redis_client, ml)

    assert ml.requests == []
    assert await redis_client.lrange(keys.QUEUE_RATE, 0, -1) == [waiting]


async def test_a_requeued_stage_is_tried_again_once_due_and_finishes(
    redis_client: RedisClient,
) -> None:
    await seed_dossier(redis_client, DOSSIER)
    await redis_client.rpush(keys.QUEUE_RATE, ITEM)

    def respond(request: httpx.Request, n: int) -> httpx.Response:
        if n <= 3:
            return httpx.Response(503)
        [passage] = json.loads(request.content)["passages"]
        return _reply({passage["id"]: 2.0})

    config = RatingConfig(enabled=True, retry_backoff_seconds=0)
    ml = Ml(respond)

    await _run(redis_client, ml, config)

    assert len(ml.requests) == 3 + len(PROSE)
    assert (await _stored(redis_client)).done is True


async def _is_done(redis_client: RedisClient) -> bool:
    document = parse_document(await redis_client.get(KEY))
    return document is not None and document.done


async def test_the_attempts_without_progress_are_capped_and_the_item_is_dropped(
    redis_client: RedisClient, caplog: pytest.LogCaptureFixture
) -> None:
    await seed_dossier(redis_client, DOSSIER)
    await _lock_and_queue(redis_client)
    await redis_client.lrem(keys.QUEUE_RATE, 0, ITEM)
    last = RatingItem(PAGE_ID, REV_ID, CONFIG.max_attempts - 1, time.time() - 1).encode()
    await redis_client.rpush(keys.QUEUE_RATE, last)

    await _run(redis_client, Ml(lambda _r, _n: httpx.Response(503)))

    assert await redis_client.llen(keys.QUEUE_RATE) == 0
    assert await redis_client.get(LOCK) is None
    assert "rating given up" in caplog.text


async def test_a_deadline_stage_releases_the_lock_and_the_retry_resumes_from_the_stored_scores(
    redis_client: RedisClient,
) -> None:
    await seed_dossier(redis_client, DOSSIER)
    await _lock_and_queue(redis_client)
    slow = [True]

    async def respond(request: httpx.Request) -> httpx.Response:
        [passage] = json.loads(request.content)["passages"]
        if slow[0] and passage["id"] == PROSE[2].id:
            slow[0] = False
            await asyncio.sleep(10)
        return _reply({passage["id"]: 2.0})

    ml_requests: list[str] = []

    async def counting(request: httpx.Request) -> httpx.Response:
        ml_requests.append(json.loads(request.content)["passages"][0]["id"])
        return await respond(request)

    http = httpx.AsyncClient(transport=httpx.MockTransport(counting), base_url="http://wke-ml.test")
    config = RatingConfig(enabled=True, deadline_seconds=1, retry_backoff_seconds=0)
    rater = Rater(redis_client, MLClient(http), config, PIPELINE_VERSION)
    before = _outcomes()
    task = asyncio.create_task(rater.run_forever())
    await _until(lambda: _deadline_counted(before), "the deadline")
    await _until(lambda: _is_done(redis_client), "the rating done")
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # Only the slow third passage is requested twice; the first two are not repeated.
    assert ml_requests == [c.id for c in PROSE[:3]] + [c.id for c in PROSE[2:]]
    assert await redis_client.get(LOCK) is None


async def _deadline_counted(before: dict[str, float]) -> bool:
    return _outcomes()["deadline"] > before["deadline"]


@pytest.mark.parametrize("outcome", ["dossier_gone", "mismatch", "superseded"])
async def test_a_final_outcome_releases_the_lock_and_queues_nothing(
    redis_client: RedisClient, outcome: str
) -> None:
    if outcome != "dossier_gone":
        await seed_dossier(redis_client, DOSSIER)
    await _lock_and_queue(redis_client)
    if outcome == "superseded":
        await redis_client.set(keys.ptr(PAGE_ID), json.dumps({"rev_id": REV_ID + 1}))
    ml = Ml(lambda r, n: _reply({json.loads(r.content)["passages"][0]["id"]: 1.0}, model="x"))

    await _run(redis_client, ml)

    assert await redis_client.get(LOCK) is None
    assert await redis_client.llen(keys.QUEUE_RATE) == 0


async def test_a_done_stage_keeps_its_lock(redis_client: RedisClient) -> None:
    await seed_dossier(redis_client, DOSSIER)
    await _lock_and_queue(redis_client)

    await _run(redis_client, Ml())

    assert await redis_client.get(LOCK) is not None


# --- an item whose revision is no longer the page's current one ---


async def test_an_item_whose_revision_is_no_longer_the_pointers_is_skipped_without_a_call(
    redis_client: RedisClient,
) -> None:
    await seed_dossier(redis_client, DOSSIER)
    await redis_client.set(keys.ptr(PAGE_ID), json.dumps({"rev_id": REV_ID + 1}))
    await redis_client.rpush(keys.QUEUE_RATE, ITEM)
    ml = Ml()
    before = REGISTRY.get_sample_value("wke_rating_stage_total", {"outcome": "superseded"}) or 0

    await _run(redis_client, ml)

    assert ml.requests == []
    assert await redis_client.get(KEY) is None
    after = REGISTRY.get_sample_value("wke_rating_stage_total", {"outcome": "superseded"})
    assert after == before + 1


async def test_the_queue_stays_first_in_first_out(redis_client: RedisClient) -> None:
    other = renamed(DOSSIER, PAGE_ID + 1, "Other")
    await seed_dossier(redis_client, DOSSIER)
    await seed_dossier(redis_client, other)
    await redis_client.rpush(keys.QUEUE_RATE, f"{PAGE_ID + 1}:{seed_pin(other).rev_id}", ITEM)
    ml = Ml()

    await _run(redis_client, ml)

    assert ml.bodies()[0]["title"] == "Other"
    assert ml.bodies()[-1]["title"] == DOSSIER.topic.title


# --- two raters: a heartbeat key marks a revision in work; a dead rater's items are requeued ---


async def test_a_revision_another_rater_holds_is_skipped(redis_client: RedisClient) -> None:
    await seed_dossier(redis_client, DOSSIER)
    await redis_client.set(HEARTBEAT, "now", ex=120)
    await redis_client.rpush(keys.QUEUE_RATE, ITEM)
    ml = Ml()

    await _run(redis_client, ml)

    assert ml.requests == []
    assert await redis_client.get(HEARTBEAT) == "now"
    assert await redis_client.llen(keys.QUEUE_RATE_PROCESSING) == 0


async def test_two_raters_on_one_revision_do_not_double_the_calls(
    redis_client: RedisClient,
) -> None:
    await seed_dossier(redis_client, DOSSIER)
    await redis_client.rpush(keys.QUEUE_RATE, ITEM, ITEM)

    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.005)
        [passage] = json.loads(request.content)["passages"]
        calls.append(passage["id"])
        return _reply({passage["id"]: 2.0})

    calls: list[str] = []
    http = httpx.AsyncClient(transport=httpx.MockTransport(slow), base_url="http://wke-ml.test")
    raters = [Rater(redis_client, MLClient(http), CONFIG, PIPELINE_VERSION) for _ in range(2)]
    tasks = [asyncio.create_task(r.run_forever()) for r in raters]
    await _until(lambda: _is_done(redis_client), "the rating done")
    await asyncio.sleep(0.1)
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)

    assert sorted(calls) == sorted(c.id for c in PROSE)


async def test_an_item_whose_rater_holds_a_live_heartbeat_is_not_taken_at_start(
    redis_client: RedisClient,
) -> None:
    await seed_dossier(redis_client, DOSSIER)
    await redis_client.rpush(keys.QUEUE_RATE_PROCESSING, ITEM)
    await redis_client.set(HEARTBEAT, "now", ex=120)
    ml = Ml()
    task = asyncio.create_task(
        Rater(redis_client, make_ml_client(ml), CONFIG, PIPELINE_VERSION).run_forever()
    )
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert ml.requests == []
    assert await redis_client.lrange(keys.QUEUE_RATE_PROCESSING, 0, -1) == [ITEM]


async def test_an_item_whose_rater_died_is_found_while_the_loop_runs(
    redis_client: RedisClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await seed_dossier(redis_client, DOSSIER)
    monkeypatch.setattr(rater_module, "REAP_INTERVAL_SECONDS", 0.05)
    ml = Ml()
    task = asyncio.create_task(
        Rater(redis_client, make_ml_client(ml), CONFIG, PIPELINE_VERSION).run_forever()
    )
    await asyncio.sleep(0.1)
    await redis_client.rpush(keys.QUEUE_RATE_PROCESSING, ITEM)
    await _until(lambda: _is_done(redis_client), "the dead rater's item rated")
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert len(ml.requests) == len(PROSE)


async def test_the_claim_is_refreshed_while_rating_and_released_after(
    redis_client: RedisClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await seed_dossier(redis_client, DOSSIER)
    await redis_client.rpush(keys.QUEUE_RATE, ITEM)
    seen: list[int] = []
    waiting: asyncio.Queue[None] = asyncio.Queue()
    ticks: asyncio.Queue[None] = asyncio.Queue()

    released = asyncio.Event()
    real_lrem = redis_client.lrem

    async def lrem(*args: Any, **kwargs: Any) -> Any:
        result = await real_lrem(*args, **kwargs)
        if args[0] == keys.QUEUE_RATE_PROCESSING:
            released.set()
        return result

    monkeypatch.setattr(redis_client, "lrem", lrem)

    async def heartbeat_sleep(_seconds: float) -> None:
        waiting.put_nowait(None)
        await ticks.get()

    async def respond(request: httpx.Request) -> httpx.Response:
        async with asyncio.timeout(SAFETY_NET_SECONDS):
            if not seen:
                await waiting.get()
            await redis_client.expire(HEARTBEAT, 1)
            ticks.put_nowait(None)
            await waiting.get()
        seen.append(await redis_client.ttl(HEARTBEAT))
        [passage] = json.loads(request.content)["passages"]
        return _reply({passage["id"]: 2.0})

    http = httpx.AsyncClient(transport=httpx.MockTransport(respond), base_url="http://wke-ml.test")
    task = asyncio.create_task(
        Rater(
            redis_client, MLClient(http), CONFIG, PIPELINE_VERSION, heartbeat_sleep=heartbeat_sleep
        ).run_forever()
    )
    # The item leaves the processing list after the heartbeat key is deleted; cancelling
    # earlier could leave the key behind.
    async with asyncio.timeout(SAFETY_NET_SECONDS):
        await released.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert await _is_done(redis_client)
    assert len(seen) == len(PROSE)
    assert min(seen) > 1
    assert await redis_client.get(HEARTBEAT) is None


async def test_a_stopped_rater_puts_its_item_back_first_and_lets_go_of_the_claim(
    redis_client: RedisClient,
) -> None:
    await seed_dossier(redis_client, DOSSIER)
    await redis_client.rpush(keys.QUEUE_RATE, ITEM, "9:9")
    started = asyncio.Event()

    async def hang(_request: httpx.Request) -> httpx.Response:
        started.set()
        await asyncio.sleep(30)
        raise AssertionError

    http = httpx.AsyncClient(transport=httpx.MockTransport(hang), base_url="http://wke-ml.test")
    task = asyncio.create_task(
        Rater(redis_client, MLClient(http), CONFIG, PIPELINE_VERSION).run_forever()
    )
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert await redis_client.lrange(keys.QUEUE_RATE, 0, -1) == [ITEM, "9:9"]
    assert await redis_client.llen(keys.QUEUE_RATE_PROCESSING) == 0
    assert await redis_client.get(HEARTBEAT) is None


# --- a Redis error must not end the loop; an item whose heartbeat cannot be kept is given up ---


def _fail(
    redis_client: RedisClient, monkeypatch: pytest.MonkeyPatch, name: str, times: int
) -> None:
    """Make the first `times` calls of one RedisClient method raise."""
    real = getattr(redis_client, name)
    left = [times]

    async def flaky(*args: Any, **kwargs: Any) -> Any:
        if left[0] > 0:
            left[0] -= 1
            raise OSError("redis is down")
        return await real(*args, **kwargs)

    monkeypatch.setattr(redis_client, name, flaky)


async def test_a_redis_error_in_the_reap_is_logged_and_the_loop_goes_on(
    redis_client: RedisClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    await seed_dossier(redis_client, DOSSIER)
    monkeypatch.setattr(rater_module, "REAP_INTERVAL_SECONDS", 0.05)
    _fail(redis_client, monkeypatch, "lrange", 2)
    task = asyncio.create_task(
        Rater(redis_client, make_ml_client(Ml()), CONFIG, PIPELINE_VERSION).run_forever()
    )
    await asyncio.sleep(0.3)
    await redis_client.rpush(keys.QUEUE_RATE, ITEM)
    await _until(lambda: _is_done(redis_client), "the item rated after the failed reaps")
    assert not task.done()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert "rating reap failed" in caplog.text


async def test_a_redis_error_removing_an_item_is_logged_and_the_loop_goes_on(
    redis_client: RedisClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    await seed_dossier(redis_client, DOSSIER)
    await redis_client.rpush(keys.QUEUE_RATE, ITEM, "9:9")
    _fail(redis_client, monkeypatch, "lrem", 1)
    task = asyncio.create_task(
        Rater(redis_client, make_ml_client(Ml()), CONFIG, PIPELINE_VERSION).run_forever()
    )
    await _until(lambda: _queue_empty(redis_client), "the second item taken")
    await _until(lambda: _processing_is(redis_client, [ITEM]), "the second item removed")
    assert not task.done()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert "could not be removed from processing" in caplog.text
    assert await _is_done(redis_client)


async def _queue_empty(redis_client: RedisClient) -> bool:
    return await redis_client.llen(keys.QUEUE_RATE) == 0


async def _processing_is(redis_client: RedisClient, expected: list[str]) -> bool:
    return await redis_client.lrange(keys.QUEUE_RATE_PROCESSING, 0, -1) == expected


async def test_an_item_that_fails_unexpectedly_releases_its_lock(
    redis_client: RedisClient, caplog: pytest.LogCaptureFixture
) -> None:
    await seed_dossier(redis_client, DOSSIER)
    await _lock_and_queue(redis_client)

    def boom(_request: httpx.Request, _n: int) -> httpx.Response:
        raise RuntimeError("not a wke-ml error")

    await _run(redis_client, Ml(boom))

    assert f"rating item failed: {ITEM}" in caplog.text
    assert await redis_client.get(LOCK) is None
    assert await redis_client.llen(keys.QUEUE_RATE_PROCESSING) == 0


@pytest.mark.parametrize("mode", ["answers_false", "raises"])
async def test_a_claim_that_cannot_be_refreshed_gives_the_item_back_instead_of_rating_on(
    redis_client: RedisClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    mode: str,
) -> None:
    await seed_dossier(redis_client, DOSSIER)
    monkeypatch.setattr(rater_module, "HEARTBEAT_INTERVAL_SECONDS", 0.01)
    config = RatingConfig(enabled=True, deadline_seconds=60, retry_backoff_seconds=0)
    await redis_client.rpush(keys.QUEUE_RATE, ITEM)
    broken = [True]
    real_set = redis_client.set

    async def set_(key: str, value: str, **kwargs: Any) -> bool:
        if key == HEARTBEAT and not kwargs.get("nx") and broken[0]:
            if mode == "raises":
                raise OSError("redis is down")
            return False
        return await real_set(key, value, **kwargs)

    monkeypatch.setattr(redis_client, "set", set_)
    calls: list[int] = []
    cancelled = asyncio.Event()

    async def respond(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                cancelled.set()
                broken[0] = False
                raise
        [passage] = json.loads(request.content)["passages"]
        return _reply({passage["id"]: 2.0})

    http = httpx.AsyncClient(transport=httpx.MockTransport(respond), base_url="http://wke-ml.test")
    task = asyncio.create_task(
        Rater(redis_client, MLClient(http), config, PIPELINE_VERSION).run_forever()
    )
    try:
        await _until(lambda: _is_done(redis_client), "the item rated after it was given back")
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert cancelled.is_set()
    assert len(calls) == 1 + len(PROSE)
    assert "rating heartbeat lost" in caplog.text
    assert await redis_client.llen(keys.QUEUE_RATE_PROCESSING) == 0


async def test_a_claim_that_stays_unwritable_is_given_back_once_with_a_backoff(
    redis_client: RedisClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await seed_dossier(redis_client, DOSSIER)
    await redis_client.rpush(keys.QUEUE_RATE, ITEM)
    real_set = redis_client.set

    async def set_(key: str, value: str, **kwargs: Any) -> bool:
        if key == HEARTBEAT and not kwargs.get("nx"):
            return False
        return await real_set(key, value, **kwargs)

    monkeypatch.setattr(redis_client, "set", set_)
    calls: list[int] = []
    cancelled = asyncio.Event()

    async def respond(_request: httpx.Request) -> httpx.Response:
        calls.append(1)
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return httpx.Response(503)

    async def heartbeat_sleep(_seconds: float) -> None:
        await asyncio.sleep(0)

    http = httpx.AsyncClient(transport=httpx.MockTransport(respond), base_url="http://wke-ml.test")
    before = time.time()
    task = asyncio.create_task(
        Rater(
            redis_client, MLClient(http), CONFIG, PIPELINE_VERSION, heartbeat_sleep=heartbeat_sleep
        ).run_forever()
    )
    try:
        await _until(lambda: _queued_retry(redis_client), "the item given back with a backoff")
        await asyncio.sleep(0.3)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert cancelled.is_set()
    assert len(calls) == 1
    [queued] = await redis_client.lrange(keys.QUEUE_RATE, 0, -1)
    retry = RatingItem.parse(queued)
    assert (retry.page_id, retry.rev_id, retry.failures) == (PAGE_ID, REV_ID, 1)
    assert before + 59 < retry.due < time.time() + 61
    assert await redis_client.llen(keys.QUEUE_RATE_PROCESSING) == 0
    assert await redis_client.get(HEARTBEAT) is None


async def _queued_retry(redis_client: RedisClient) -> bool:
    return await redis_client.llen(keys.QUEUE_RATE) == 1


async def test_a_claim_that_cannot_be_written_gives_the_item_back(
    redis_client: RedisClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    await seed_dossier(redis_client, DOSSIER)
    await redis_client.rpush(keys.QUEUE_RATE, ITEM)
    _fail(redis_client, monkeypatch, "set", 1)

    await _run(redis_client, Ml())

    assert "rating claim could not be written" in caplog.text
    assert await _is_done(redis_client)
