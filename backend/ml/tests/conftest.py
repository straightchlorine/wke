"""Shared fixtures for wke-ml tests."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Callable

os.environ.setdefault("WKE_ML_BACKEND", "stub")

import httpx
import pytest
from fastapi import FastAPI
from prometheus_client import REGISTRY

from wke_ml.backends import HashEmbedder
from wke_ml.main import create_app, lifespan
from wke_ml.settings import Settings


@pytest.fixture
def settings_stub() -> Settings:
    return Settings(backend="stub")


@pytest.fixture
def embedder() -> HashEmbedder:
    return HashEmbedder()


@pytest.fixture
def shed_count() -> Callable[[str], float]:
    """Reader for the current wke_ml_shed_total value of one reason."""

    def read(reason: str) -> float:
        value = REGISTRY.get_sample_value("wke_ml_shed_total", {"reason": reason})
        assert value is not None
        return value

    return read


@pytest.fixture
async def running_app(settings_stub: Settings) -> AsyncIterator[FastAPI]:
    """A wke-ml app with lifespan startup (weight load + warm-up) run."""
    app = create_app(settings_stub)
    async with lifespan(app):
        yield app


@pytest.fixture
async def client(running_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=running_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
