"""Probe helpers behind /api/v1/status and /metrics: edge cases the route tests do not reach."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, tzinfo
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI

from tests.support.snapshots import make_snapshot
from wke.api import probes
from wke.clients.ml import MLClient
from wke.clients.redis import RedisClient
from wke.core import keys
from wke.core.models import TrendingSnapshot
from wke.metrics import TRENDING_LAST_SUCCESS_TIMESTAMP


@pytest.mark.parametrize("stored", [None, "not json", json.dumps({"topics": "wrong shape"})])
async def test_read_trending_snapshot_is_none_without_a_usable_snapshot(
    redis_client: RedisClient, stored: str | None
) -> None:
    if stored is not None:
        await redis_client.set(keys.TRENDING_LATEST, stored)

    assert await probes.read_trending_snapshot(redis_client) is None


async def test_read_trending_snapshot_parses_the_stored_snapshot(redis_client: RedisClient) -> None:
    await redis_client.set(keys.TRENDING_LATEST, json.dumps(make_snapshot()))

    snapshot = await probes.read_trending_snapshot(redis_client)

    assert isinstance(snapshot, TrendingSnapshot)
    assert snapshot.date.isoformat() == "2026-09-27"


async def test_wikimedia_budget_is_unknown_when_redis_is_down(redis_client: RedisClient) -> None:
    assert await probes.wikimedia_budget_remaining(redis_client, 100, redis_ok=False) is None


async def test_wikimedia_budget_never_goes_below_zero(
    redis_client: RedisClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> datetime:
            return datetime(2026, 9, 27, 3, 0, 30, tzinfo=UTC)

    monkeypatch.setattr(probes, "datetime", FrozenDatetime)
    minute = int(datetime(2026, 9, 27, 3, 0, tzinfo=UTC).timestamp() // 60)
    await redis_client.set(keys.wm_budget(minute), "130")

    assert await probes.wikimedia_budget_remaining(redis_client, 100, redis_ok=True) == 0
    assert await probes.wikimedia_budget_remaining(redis_client, 200, redis_ok=True) == 70


async def test_unparseable_trending_snapshot_leaves_the_gauge_alone(
    redis_client: RedisClient,
) -> None:
    TRENDING_LAST_SUCCESS_TIMESTAMP.set(42.0)
    await redis_client.set(keys.TRENDING_LATEST, "not json")
    app = FastAPI()
    app.state.redis = redis_client

    await probes.sample_redis_gauges(app)

    assert list(TRENDING_LAST_SUCCESS_TIMESTAMP.collect())[0].samples[0].value == 42.0


async def test_ml_probe_loop_keeps_re_probing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(probes, "ML_PROBE_INTERVAL_SECONDS", 0)
    ml = AsyncMock(spec=MLClient)
    ml.readyz.side_effect = [True, False, True]
    app = FastAPI()
    app.state.ml = ml

    task = asyncio.create_task(probes.ml_probe_loop(app))
    try:
        async with asyncio.timeout(2):
            while ml.readyz.await_count < 3:
                await asyncio.sleep(0)
    finally:
        task.cancel()

    assert app.state.ml_ready is True
    assert app.state.ml_ready_checked_at is not None
