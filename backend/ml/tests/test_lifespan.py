"""Tests for lifespan startup failures and the /healthz and /readyz probes."""

from __future__ import annotations

import time
from collections.abc import Sequence

import httpx
import numpy as np
import pytest
from fastapi import FastAPI

from wke_ml.backends import Embedder, FloatArray
from wke_ml.main import create_app, lifespan
from wke_ml.settings import Settings


def _raising_embedder_factory(_settings: Settings) -> Embedder:
    raise RuntimeError("embedder failed to load")


class _FailingBackend:
    """Embedder and summarizer whose warm-up call fails for one of the two."""

    def __init__(self, failing: str) -> None:
        self._failing = failing

    def embed(self, texts: Sequence[str]) -> FloatArray:
        if self._failing == "embed":
            raise RuntimeError("boom")
        return np.zeros((len(texts), 1), dtype=np.float32)

    def summarize(
        self, text: str, num_beams: int, min_length: int, max_length: int
    ) -> tuple[str, int, bool]:
        raise RuntimeError("boom")


@pytest.mark.parametrize("failing", ["factory", "embed", "summarize"])
async def test_lifespan_exits_1_on_startup_failure(failing: str, settings_stub: Settings) -> None:
    app = create_app(settings_stub)
    if failing == "factory":
        app.state.embedder_factory = _raising_embedder_factory
    else:
        backend = _FailingBackend(failing)

        def factory(_settings: Settings) -> _FailingBackend:
            return backend

        app.state.embedder_factory = factory
        app.state.summarizer_factory = factory

    with pytest.raises(SystemExit) as exc_info:
        async with lifespan(app):
            pass
    assert exc_info.value.code == 1


async def test_healthz_and_readyz_are_200_once_reachable(client: httpx.AsyncClient) -> None:
    healthz = await client.get("/healthz")
    readyz = await client.get("/readyz")

    assert healthz.status_code == 200
    assert healthz.json() == {"status": "ok"}
    assert readyz.status_code == 200
    assert readyz.json() == {"status": "ready"}


async def test_healthz_fails_when_a_job_holds_the_slot_too_long(
    running_app: FastAPI, client: httpx.AsyncClient
) -> None:
    app = running_app
    app.state.gate._running_since = time.monotonic() - app.state.settings.stuck_after_seconds - 1

    healthz = await client.get("/healthz")
    readyz = await client.get("/readyz")

    assert healthz.status_code == 503
    assert healthz.json() == {"status": "stuck"}
    assert readyz.status_code == 200
