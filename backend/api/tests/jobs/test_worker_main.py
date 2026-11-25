"""The standalone worker entry point builds the worker from the settings."""

from __future__ import annotations

from typing import Any

import pytest

from tests.support.workers import make_worker
from wke.clients.redis import RedisClient
from wke.jobs.build.rating import RatingConfig
from wke.jobs.rater import Rater
from wke.jobs.worker import Worker
from wke.settings import settings
from wke.worker import __main__ as worker_main


async def test_worker_process_passes_the_public_url_settings_to_the_worker(
    fake_redis: Any, redis_client: RedisClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    built: list[dict[str, Any]] = []

    def fake_worker(*args: Any, **kwargs: Any) -> Worker:
        built.append({"args": args, "kwargs": kwargs})
        return make_worker(redis_client, args[1])

    async def no_loop(_worker: Worker) -> None:
        return None

    def fake_redis_factory(_url: str) -> Any:
        return fake_redis

    monkeypatch.setattr(worker_main, "default_redis_factory", fake_redis_factory)
    monkeypatch.setattr(worker_main, "Worker", fake_worker)
    monkeypatch.setattr(worker_main, "_run_until_sigterm", no_loop)
    monkeypatch.setattr(settings, "public_host", "wke.example.test")
    monkeypatch.setattr(settings, "public_scheme", "http")

    await worker_main._run()

    [call] = built
    assert call["args"][5:] == (
        settings.summary_sections,
        settings.num_beams,
        str(settings.wikipedia_api_url),
    )
    assert call["kwargs"] == {
        "public_host": "wke.example.test",
        "public_scheme": "http",
        "analyze_deadline_ms": settings.analyze_deadline_ms,
        "analyze_retries": settings.analyze_retries,
        "analyze_retry_pause_ms": settings.analyze_retry_pause_ms,
        "analyze_retry_on_timeout": settings.analyze_retry_on_timeout,
        "structural_ttl_seconds": settings.dossier_structural_ttl_seconds,
        "rating": None,
    }


async def test_worker_process_builds_a_rater_only_when_selection_rating_is_on(
    fake_redis: Any, redis_client: RedisClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    built: list[dict[str, Any]] = []

    def fake_worker(*args: Any, **kwargs: Any) -> Worker:
        built.append(kwargs)
        return make_worker(redis_client, args[1])

    async def no_loop(_worker: Worker) -> None:
        return None

    monkeypatch.setattr(worker_main, "default_redis_factory", lambda _url: fake_redis)
    monkeypatch.setattr(worker_main, "Worker", fake_worker)
    monkeypatch.setattr(worker_main, "_run_until_sigterm", no_loop)
    monkeypatch.setattr(settings, "selection_rating", True)
    monkeypatch.setattr(settings, "rating_deadline_seconds", 90)
    monkeypatch.setattr(settings, "summary_sections", 5)

    await worker_main._run()

    [kwargs] = built
    assert isinstance(kwargs["rating"], Rater)
    assert kwargs["rating"].config == RatingConfig(
        enabled=True, deadline_seconds=90, call_timeout_seconds=120, summary_sections=5
    )


async def test_worker_process_gives_the_rater_a_client_of_its_own(
    fake_redis: Any, redis_client: RedisClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    built: list[tuple[Any, Any]] = []

    def fake_worker(*args: Any, **kwargs: Any) -> Worker:
        built.append((args[3], kwargs["rating"]))
        return make_worker(redis_client, args[1])

    async def no_loop(_worker: Worker) -> None:
        return None

    monkeypatch.setattr(worker_main, "default_redis_factory", lambda _url: fake_redis)
    monkeypatch.setattr(worker_main, "Worker", fake_worker)
    monkeypatch.setattr(worker_main, "_run_until_sigterm", no_loop)
    monkeypatch.setattr(settings, "selection_rating", True)

    await worker_main._run()

    [(workers_ml, rater)] = built
    assert rater._ml is not workers_ml  # pyright: ignore[reportPrivateUsage]
    assert rater._ml._semaphore is not workers_ml._semaphore  # pyright: ignore[reportPrivateUsage]
