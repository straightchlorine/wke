"""GET /api/v1/status: ml_ready reflects a real, throttled wke-ml probe."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from tests.support.apps import app_client, make_app
from tests.support.snapshots import make_snapshot
from wke.api.constants import ML_PROBE_MIN_INTERVAL_SECONDS, PACKAGE_VERSION
from wke.api.probes import ml_probe_is_stale, probe_ml_ready
from wke.clients.ml import MLClient
from wke.core import keys


def _app_with_ml_readyz(fake_redis, settings, wikimedia_client, status_code: int) -> FastAPI:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/readyz":
            return httpx.Response(status_code, json={"status": "ready"})
        return httpx.Response(404)

    ml_http = httpx.AsyncClient(
        transport=httpx.MockTransport(handle), base_url="http://wke-ml.test"
    )

    return make_app(
        fake_redis,
        settings,
        wikimedia_http=wikimedia_client._http,
        ml_http=ml_http,
        start_worker=True,
    )


async def test_status_ml_ready_true_when_wke_ml_answers_200(
    fake_redis, settings, wikimedia_client
) -> None:
    app = _app_with_ml_readyz(fake_redis, settings, wikimedia_client, 200)

    async with app_client(app) as client:
        response = await client.get("/api/v1/status")

    assert response.status_code == 200
    assert response.json()["ml_ready"] is True


async def test_status_ml_ready_false_when_wke_ml_unavailable(
    fake_redis, settings, wikimedia_client
) -> None:
    app = _app_with_ml_readyz(fake_redis, settings, wikimedia_client, 503)

    async with app_client(app) as client:
        response = await client.get("/api/v1/status")

    assert response.status_code == 200
    assert response.json()["ml_ready"] is False


async def test_probe_ml_ready_records_result_and_checked_at() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "ready"})

    ml_http = httpx.AsyncClient(transport=httpx.MockTransport(handle), base_url="http://x.test")
    fake_app = FastAPI()
    fake_app.state.ml = MLClient(ml_http)

    before = datetime.now(UTC)
    await probe_ml_ready(fake_app)
    after = datetime.now(UTC)

    assert fake_app.state.ml_ready is True
    assert before <= fake_app.state.ml_ready_checked_at <= after
    await ml_http.aclose()


@pytest.mark.parametrize(
    ("seconds_ago", "expected"),
    [
        pytest.param(None, True, id="no_prior_probe"),
        pytest.param(ML_PROBE_MIN_INTERVAL_SECONDS - 1, False, id="just_under_the_throttle_window"),
        pytest.param(ML_PROBE_MIN_INTERVAL_SECONDS, True, id="at_the_throttle_window"),
    ],
)
def test_ml_probe_is_stale(seconds_ago: int | None, expected: bool) -> None:
    now = datetime.now(UTC)
    checked_at = None if seconds_ago is None else now - timedelta(seconds=seconds_ago)
    assert ml_probe_is_stale(checked_at, now) is expected


async def test_status_reports_idle_defaults(app, settings) -> None:
    """With nothing seeded, every field is its idle value; ml_ready is a real probe.

    The default ml mock has no /readyz handler, so ml_ready is False rather than a
    hardcoded True.
    """
    async with app_client(app) as client:
        response = await client.get("/api/v1/status")

    assert response.status_code == 200
    assert response.json() == {
        "version": PACKAGE_VERSION,
        "pipeline_version": settings.pipeline_version,
        "redis": True,
        "ml_ready": False,
        "watcher_connected": False,
        "trending_date": None,
        "trending_age_seconds": None,
        "queue_depth": 0,
        "wikimedia_budget_remaining": settings.wm_budget_per_minute,
    }


async def test_status_without_redis_has_no_wikimedia_budget(app) -> None:
    async with app_client(app) as client:
        app.state.redis.ping = AsyncMock(return_value=False)
        body = (await client.get("/api/v1/status")).json()

    assert body["redis"] is False
    assert body["wikimedia_budget_remaining"] is None


async def test_status_trending_age_never_goes_negative(app, redis_client) -> None:
    ahead = datetime.now(UTC) + timedelta(hours=1)
    snapshot = make_snapshot(topics=[], generated_at=ahead.isoformat())
    await redis_client.set(keys.TRENDING_LATEST, json.dumps(snapshot))

    async with app_client(app) as client:
        body = (await client.get("/api/v1/status")).json()

    assert body["trending_age_seconds"] == 0


async def test_status_reports_populated_state(app, redis_client, settings, monkeypatch) -> None:
    """Heartbeat, stored snapshot and counted Wikimedia calls show up in the status body."""
    frozen = datetime(2026, 9, 28, 12, 0, 30, tzinfo=UTC)

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen

    monkeypatch.setattr("wke.api.routes.status.datetime", FrozenDatetime)
    monkeypatch.setattr("wke.api.probes.datetime", FrozenDatetime)
    calls = 7
    await redis_client.set(
        keys.WATCHER_HEARTBEAT, frozen.isoformat(), ex=keys.WATCHER_HEARTBEAT_TTL_SECONDS
    )
    snapshot = make_snapshot(topics=[], generated_at=(frozen - timedelta(hours=2)).isoformat())
    await redis_client.set(keys.TRENDING_LATEST, json.dumps(snapshot))
    epoch_minute = int(frozen.timestamp() // 60)
    for _ in range(calls):
        await redis_client.incr(keys.wm_budget(epoch_minute))

    async with app_client(app) as client:
        body = (await client.get("/api/v1/status")).json()

    assert body["watcher_connected"] is True
    assert body["trending_date"] == "2026-09-27"
    assert body["trending_age_seconds"] == 7200
    assert body["wikimedia_budget_remaining"] == settings.wm_budget_per_minute - calls
