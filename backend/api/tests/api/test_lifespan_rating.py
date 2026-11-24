"""The lifespan creates the rating loop only while SELECTION_RATING is on."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from tests.support.ml_clients import analyze_down_client, make_ml_client
from tests.support.ml_payloads import analyze_response_json
from wke.api.lifespan import _build_rater, _build_service, _build_worker
from wke.clients.redis import RedisClient
from wke.jobs.build.rating import RatingConfig
from wke.jobs.rater import Rater
from wke.settings import Settings


def test_no_rater_while_the_switch_is_off(settings: Settings, redis_client: RedisClient) -> None:
    assert _build_rater(settings, redis_client, analyze_down_client()) is None


def test_a_rater_with_the_settings_while_the_switch_is_on(
    settings: Settings, redis_client: RedisClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "selection_rating", True)
    monkeypatch.setattr(settings, "rating_deadline_seconds", 77)

    rater = _build_rater(settings, redis_client, analyze_down_client())

    assert isinstance(rater, Rater)
    assert rater.config == RatingConfig(True, 77, 120, settings.summary_sections)


def test_the_service_and_the_worker_are_wired_with_the_rating(
    settings: Settings, redis_client: RedisClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import httpx

    monkeypatch.setattr(settings, "selection_rating", True)
    wikimedia, job_queue, service = _build_service(settings, redis_client, httpx.AsyncClient())
    worker = _build_worker(settings, redis_client, job_queue, wikimedia, analyze_down_client())

    assert service._rating.enabled is True  # pyright: ignore[reportPrivateUsage]
    assert worker._rating is not None  # pyright: ignore[reportPrivateUsage]


async def test_an_analyze_through_the_workers_client_starts_while_a_rating_call_is_in_flight(
    settings: Settings, redis_client: RedisClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "selection_rating", True)
    rating_started, release = asyncio.Event(), asyncio.Event()
    paths: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/v1/rate":
            rating_started.set()
            await release.wait()
            return httpx.Response(500)
        return httpx.Response(200, json=analyze_response_json())

    workers_ml = make_ml_client(handler)
    rater = _build_rater(settings, redis_client, workers_ml)
    assert rater is not None
    rating = asyncio.create_task(rater._ml.rate("T", "L", [{"id": "c1", "text": "x"}], 120_000))  # pyright: ignore[reportPrivateUsage]
    try:
        await rating_started.wait()

        await asyncio.wait_for(workers_ml.analyze("lead", [{"id": "c1", "text": "x"}]), timeout=2)

        assert paths == ["/v1/rate", "/v1/analyze"]
    finally:
        release.set()
        await asyncio.gather(rating, return_exceptions=True)


def test_the_worker_gets_a_rater_with_a_client_of_its_own(
    settings: Settings, redis_client: RedisClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "selection_rating", True)
    ml = analyze_down_client()
    _, job_queue, _ = _build_service(settings, redis_client, httpx.AsyncClient())

    worker = _build_worker(settings, redis_client, job_queue, None, ml)  # type: ignore[arg-type]

    rater_ml = worker._rating._ml  # type: ignore[union-attr]  # pyright: ignore[reportPrivateUsage]
    assert rater_ml is not ml
    assert rater_ml._http is ml._http  # pyright: ignore[reportPrivateUsage]
