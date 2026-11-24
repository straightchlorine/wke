"""Change D's analyze deadline and retry belong to the build's analyze call alone.

The Rater has its own wke-ml client and its own timeouts; neither follows the ANALYZE_* settings,
and a rating call never moves a build's analyze deadline or retry.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest

from tests.support.builds import build_only, make_queue
from tests.support.constants import PIPELINE_VERSION
from tests.support.jobs import make_job
from tests.support.ml_clients import make_ml_client
from tests.support.ml_payloads import analyze_response_json
from tests.support.workers import make_worker
from wke.api.lifespan import _build_rater, _build_worker
from wke.clients.ml import MLClient
from wke.clients.redis import RedisClient
from wke.clients.wikimedia import WikimediaClient
from wke.core import keys
from wke.jobs import rater as rater_module
from wke.jobs.build.constants import RATING_CALL_ATTEMPTS, RATING_MODEL_FILE, RATING_PROMPT_SHA256
from wke.jobs.build.rating import RatingConfig
from wke.jobs.rater import Rater
from wke.settings import Settings

RATING = RatingConfig(enabled=True, deadline_seconds=60, call_timeout_seconds=77)
ANALYZE = {
    "analyze_deadline_ms": 1234,
    "analyze_retries": 1,
    "analyze_retry_pause_ms": 0,
    "analyze_retry_on_timeout": False,
}


@pytest.fixture(autouse=True)
def _no_pauses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rater_module, "RATING_RETRY_PAUSE_SECONDS", 0)
    monkeypatch.setattr(rater_module, "REDIS_ERROR_PAUSE_SECONDS", 0)


class _Ml:
    """A wke-ml that fails the first calls of each route as told and keeps every request."""

    def __init__(self, analyze_failures: int = 0, rate_failures: int = 0) -> None:
        self.requests: list[httpx.Request] = []
        self._analyze_failures = analyze_failures
        self._rate_failures = rate_failures

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == "/v1/analyze":
            if self._analyze_failures:
                self._analyze_failures -= 1
                return httpx.Response(500)
            return httpx.Response(200, json=analyze_response_json())
        if self._rate_failures:
            self._rate_failures -= 1
            return httpx.Response(503, json={"code": "rating_unavailable"})
        [passage] = json.loads(request.content)["passages"]
        return httpx.Response(
            200,
            json={
                "model": RATING_MODEL_FILE,
                "prompt_sha256": RATING_PROMPT_SHA256,
                "scores": {passage["id"]: 2.0},
                "fallback_ids": [],
                "infer_seconds": 0.1,
            },
        )

    def calls(self, path: str) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.path == path]


async def _drain(rater: Rater, redis_client: RedisClient) -> None:
    task = asyncio.create_task(rater.run_forever())
    try:
        for _ in range(500):
            await asyncio.sleep(0.01)
            if not await redis_client.llen(keys.QUEUE_RATE) and not await redis_client.llen(
                keys.QUEUE_RATE_PROCESSING
            ):
                break
        else:
            pytest.fail("the rating loop did not finish")
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


async def test_the_analyze_deadline_and_retry_stay_on_analyze_and_the_rating_keeps_its_own(
    redis_client: RedisClient, wikimedia_client: WikimediaClient
) -> None:
    build_ml, rate_ml = _Ml(analyze_failures=1), _Ml(rate_failures=1)

    await build_only(
        redis_client,
        wikimedia_client,
        make_ml_client(build_ml),
        make_job(),
        rating=RATING,
        **ANALYZE,  # type: ignore[arg-type]
    )
    await _drain(
        Rater(redis_client, make_ml_client(rate_ml), RATING, PIPELINE_VERSION), redis_client
    )

    # the build: one retry of analyze, each attempt on the analyze deadline, never a rating call
    assert [r.headers["X-Deadline-Ms"] for r in build_ml.calls("/v1/analyze")] == ["1234"] * 2
    assert build_ml.calls("/v1/rate") == []
    # the rater: the call timeout, not the analyze deadline; its one failed call is tried again
    # although ANALYZE_RETRIES counts analyze only (here 1, and ANALYZE_RETRY_ON_TIMEOUT is off)
    rate_calls = rate_ml.calls("/v1/rate")
    assert rate_ml.calls("/v1/analyze") == []
    assert {r.headers["X-Deadline-Ms"] for r in rate_calls} == {"77000"}
    first_passage = json.loads(rate_calls[0].content)["passages"][0]["id"]
    assert [json.loads(r.content)["passages"][0]["id"] for r in rate_calls[:2]] == [
        first_passage
    ] * 2


async def test_a_rating_call_is_retried_by_the_ratings_rule_whatever_the_analyze_retries(
    redis_client: RedisClient, wikimedia_client: WikimediaClient
) -> None:
    no_retry = {**ANALYZE, "analyze_retries": 0}
    rate_ml = _Ml(rate_failures=RATING_CALL_ATTEMPTS - 1)

    await build_only(
        redis_client,
        wikimedia_client,
        make_ml_client(_Ml()),
        make_job(),
        rating=RATING,
        **no_retry,  # type: ignore[arg-type]
    )
    await _drain(
        Rater(redis_client, make_ml_client(rate_ml), RATING, PIPELINE_VERSION), redis_client
    )

    first = json.loads(rate_ml.calls("/v1/rate")[0].content)["passages"][0]["id"]
    same = [
        r for r in rate_ml.calls("/v1/rate") if json.loads(r.content)["passages"][0]["id"] == first
    ]
    assert len(same) == RATING_CALL_ATTEMPTS


async def test_a_rating_timeout_is_retried_although_analyze_timeouts_are_not(
    redis_client: RedisClient, wikimedia_client: WikimediaClient
) -> None:
    calls: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        raise httpx.ReadTimeout("slow")

    await build_only(
        redis_client,
        wikimedia_client,
        make_ml_client(_Ml()),
        make_job(),
        rating=RATING,
        **ANALYZE,  # type: ignore[arg-type]
    )
    rater = Rater(redis_client, make_ml_client(handle), RATING, PIPELINE_VERSION)
    task = asyncio.create_task(rater.run_forever())
    try:
        for _ in range(500):
            await asyncio.sleep(0.01)
            if calls.count("/v1/rate") >= RATING_CALL_ATTEMPTS:
                break
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    # the three tries of one passage, then the stage ends and waits out its backoff
    assert calls.count("/v1/rate") == RATING_CALL_ATTEMPTS


async def test_a_worker_with_a_rater_passes_it_the_analyze_settings_separately(
    redis_client: RedisClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, Any] = {}

    async def fake_run_build(_job: object, **kwargs: Any) -> None:
        seen.update(kwargs)

    monkeypatch.setattr("wke.jobs.worker.run_build", fake_run_build)
    queue = make_queue(redis_client)
    rater = Rater(redis_client, make_ml_client(_Ml()), RATING, PIPELINE_VERSION)
    worker = make_worker(redis_client, queue, rating=rater, **ANALYZE)
    job = make_job()
    await queue.set_job(job)

    await worker._process(keys.QUEUE_INTERACTIVE, job.id)

    for name, value in ANALYZE.items():
        assert seen[name] == value
    assert seen["rating"] == RATING
    # no rating field reaches the analyze settings and none of them reaches the rating's
    assert not {"analyze_deadline_ms", "analyze_retries"} & set(RatingConfig.__dataclass_fields__)


async def test_the_lifespan_gives_the_worker_the_analyze_settings_and_the_rater_its_own_client(
    redis_client: RedisClient,
) -> None:
    cfg = Settings.model_validate(
        {
            "selection_rating": True,
            "analyze_deadline_ms": 1234,
            "analyze_retries": 1,
            "rating_call_timeout_seconds": 77,
            "rating_deadline_seconds": 60,
        }
    )
    ml = MLClient(httpx.AsyncClient(base_url="http://wke-ml.test"))
    worker = _build_worker(cfg, redis_client, make_queue(redis_client), None, ml)  # type: ignore[arg-type]

    rater = worker._rating
    assert worker._ml is ml
    assert worker._analyze_deadline_ms == 1234 and worker._analyze_retries == 1
    assert rater is not None and rater._ml is not ml
    assert rater._ml._semaphore is not ml._semaphore
    assert rater.config.call_timeout_seconds == 77 and rater.config.deadline_seconds == 60
    # off, no rater exists and the analyze settings are the same
    off = Settings.model_validate({"analyze_deadline_ms": 1234})
    assert _build_rater(off, redis_client, ml) is None
    assert _build_worker(off, redis_client, make_queue(redis_client), None, ml)._rating is None  # type: ignore[arg-type]
