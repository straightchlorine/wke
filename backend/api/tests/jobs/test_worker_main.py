"""The standalone worker entry point builds the worker from the settings."""

from __future__ import annotations

from typing import Any

import pytest

from tests.support.workers import make_worker
from wke.clients.redis import RedisClient
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
    assert call["kwargs"] == {"public_host": "wke.example.test", "public_scheme": "http"}
