"""Queueing a stored dossier's rating stage, and the worker that runs the rating loop."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from tests.factories.dossier import make_fixture_dossier
from tests.support.builds import make_queue
from tests.support.constants import PIPELINE_VERSION
from tests.support.jobs import make_job
from tests.support.ml_clients import make_ml_client
from tests.support.workers import make_worker
from wke.clients.redis import RedisClient
from wke.core import keys
from wke.jobs import worker as worker_module
from wke.jobs.build.constants import RATING_MODEL, RATING_PROMPT_SHA256
from wke.jobs.build.rating import RatingConfig, RatingDocument, rating_key, rating_lock_key
from wke.jobs.rater import Rater

PAGE_ID, REV_ID = 7, 9
KEY = rating_key(PAGE_ID, REV_ID, PIPELINE_VERSION)
LOCK = rating_lock_key(PAGE_ID, REV_ID, PIPELINE_VERSION)


def _document(done: bool, **overrides: Any) -> str:
    fields: dict[str, Any] = {
        "prompt_sha256": RATING_PROMPT_SHA256,
        "model": RATING_MODEL,
        "done": done,
        "scores": {"a": 1.0},
    }
    return RatingDocument(**{**fields, **overrides}).model_dump_json()


async def test_a_dossier_without_a_rating_is_locked_and_queued(
    redis_client: RedisClient,
) -> None:
    await make_queue(redis_client).enqueue_rating(PAGE_ID, REV_ID, 2400)

    assert await redis_client.lrange(keys.QUEUE_RATE, 0, -1) == [f"{PAGE_ID}:{REV_ID}"]
    assert 2300 < await redis_client.ttl(LOCK) <= 2400


async def test_a_second_enqueue_while_the_lock_holds_queues_nothing(
    redis_client: RedisClient,
) -> None:
    queue = make_queue(redis_client)

    await queue.enqueue_rating(PAGE_ID, REV_ID, 2400)
    await queue.enqueue_rating(PAGE_ID, REV_ID, 2400)

    assert await redis_client.llen(keys.QUEUE_RATE) == 1


async def test_a_finished_rating_queues_nothing_and_takes_no_lock(
    redis_client: RedisClient,
) -> None:
    await redis_client.set(KEY, _document(done=True))

    await make_queue(redis_client).enqueue_rating(PAGE_ID, REV_ID, 2400)

    assert await redis_client.llen(keys.QUEUE_RATE) == 0
    assert await redis_client.get(LOCK) is None


@pytest.mark.parametrize(
    "stored",
    [
        _document(done=False),
        _document(done=True, prompt_sha256="0" * 64),
        _document(done=True, model="other"),
        "not json",
    ],
    ids=["unfinished", "other_prompt", "other_model", "corrupt"],
)
async def test_an_unfinished_or_foreign_document_is_queued_again(
    redis_client: RedisClient, stored: str
) -> None:
    await redis_client.set(KEY, stored)

    await make_queue(redis_client).enqueue_rating(PAGE_ID, REV_ID, 2400)

    assert await redis_client.llen(keys.QUEUE_RATE) == 1


async def test_a_finished_rating_lives_at_least_as_long_as_the_dossier_stored_again(
    redis_client: RedisClient,
) -> None:
    dossier_key = keys.dossier(PAGE_ID, REV_ID, PIPELINE_VERSION)
    await redis_client.set(dossier_key, "{}", ex=keys.DOSSIER_TTL_SECONDS)
    await redis_client.set(KEY, _document(done=True), ex=3600)

    await make_queue(redis_client).enqueue_rating(PAGE_ID, REV_ID, 2400)

    assert await redis_client.ttl(KEY) > keys.DOSSIER_TTL_SECONDS - 60


async def test_a_finished_rating_that_outlives_the_dossier_keeps_its_life(
    redis_client: RedisClient,
) -> None:
    await redis_client.set(keys.dossier(PAGE_ID, REV_ID, PIPELINE_VERSION), "{}", ex=600)
    await redis_client.set(KEY, _document(done=True), ex=3600)

    await make_queue(redis_client).enqueue_rating(PAGE_ID, REV_ID, 2400)

    assert 3500 < await redis_client.ttl(KEY) <= 3600


async def test_the_rating_queue_is_not_one_the_build_worker_polls() -> None:
    assert keys.QUEUE_RATE not in keys.QUEUE_PRIORITY_ORDER
    assert keys.QUEUE_RATE_PROCESSING not in keys.QUEUE_PRIORITY_ORDER
    assert (keys.QUEUE_RATE, keys.QUEUE_RATE_PROCESSING) == ("q:rate", "q:rate:processing")


async def test_an_error_while_queueing_is_logged_and_not_raised(
    redis_client: RedisClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def boom(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(redis_client, "rpush", boom)

    await make_queue(redis_client).enqueue_rating(PAGE_ID, REV_ID, 2400)

    assert f"rating enqueue failed for page {PAGE_ID} rev {REV_ID}" in caplog.text


def _rater(redis_client: RedisClient) -> Rater:
    ml = make_ml_client(lambda _request: pytest.fail("no call expected"))
    return Rater(redis_client, ml, RatingConfig(enabled=True), PIPELINE_VERSION)


async def _run_for(worker: worker_module.Worker, seconds: float) -> None:
    task = asyncio.create_task(worker.run_forever())
    await asyncio.sleep(seconds)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_a_worker_with_a_rater_runs_its_loop_and_stops_it_with_itself(
    redis_client: RedisClient,
) -> None:
    # No dossier is stored, so the item is taken, found to have no dossier, and dropped.
    await redis_client.rpush(keys.QUEUE_RATE, f"{PAGE_ID}:{REV_ID}")
    rater = _rater(redis_client)
    worker = make_worker(redis_client, make_queue(redis_client), rater)
    tasks_before = len(asyncio.all_tasks())

    await _run_for(worker, 0.3)

    assert await redis_client.llen(keys.QUEUE_RATE) == 0
    assert await redis_client.llen(keys.QUEUE_RATE_PROCESSING) == 0
    assert len(asyncio.all_tasks()) <= tasks_before


async def test_a_worker_without_a_rater_never_touches_the_rating_queue(
    redis_client: RedisClient,
) -> None:
    await redis_client.rpush(keys.QUEUE_RATE, f"{PAGE_ID}:{REV_ID}")

    await _run_for(make_worker(redis_client, make_queue(redis_client)), 0.3)

    assert await redis_client.lrange(keys.QUEUE_RATE, 0, -1) == [f"{PAGE_ID}:{REV_ID}"]
    assert await redis_client.llen(keys.QUEUE_RATE_PROCESSING) == 0


@pytest.mark.parametrize("with_rater", [False, True])
async def test_a_build_gets_the_rating_config_of_the_worker(
    redis_client: RedisClient, monkeypatch: pytest.MonkeyPatch, with_rater: bool
) -> None:
    seen: list[RatingConfig] = []

    async def fake_run_build(_job: Any, **kwargs: Any) -> None:
        seen.append(kwargs["rating"])

    monkeypatch.setattr(worker_module, "run_build", fake_run_build)
    queue = make_queue(redis_client)
    await queue.set_job(make_job(id="0123456789abcdef", rev_id=1, status="running"))
    await redis_client.rpush(keys.QUEUE_INTERACTIVE, "0123456789abcdef")
    rater = _rater(redis_client) if with_rater else None

    await make_worker(redis_client, make_queue(redis_client), rater)._run_once()

    assert seen == [rater.config if rater else RatingConfig()]


def test_the_fixture_dossier_has_the_prose_these_tests_name() -> None:
    assert sum(c.kind == "prose" for c in make_fixture_dossier().chunks) == 6
