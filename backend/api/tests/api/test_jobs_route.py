"""GET /api/v1/jobs/{job_id}: job status, Retry-After and the polling rate limit."""

from __future__ import annotations

import limits
import pytest

from tests.support.apps import app_client
from tests.support.constants import PIPELINE_VERSION
from tests.support.jobs import make_job
from wke.api.ratelimit import GET_READS_RATE_LIMIT, JOB_POLL_RATE_LIMIT
from wke.core.models import JobProgress
from wke.jobs.queue import JobQueue


@pytest.mark.parametrize(
    ("status", "poll_after_ms", "retry_after"),
    [
        pytest.param("running", 3000, "3", id="running"),
        pytest.param("queued", 3000, "3", id="queued"),
        pytest.param("queued", 400, "1", id="floor-of-one-second"),
        pytest.param("done", 3000, None, id="finished-has-none"),
    ],
)
async def test_get_job_returns_status_with_retry_after(
    app, redis_client, status: str, poll_after_ms: int, retry_after: str | None
) -> None:
    job = make_job(
        id="bbbbbbbbbbbbbbbb",
        status=status,
        stage="embed",
        progress=JobProgress(done=4, total=8),
        poll_after_ms=poll_after_ms,
    )
    job_queue = JobQueue(redis_client, PIPELINE_VERSION, queue_cap=20)
    await job_queue.set_job(job)

    async with app_client(app) as client:
        response = await client.get(f"/api/v1/jobs/{job.id}")

    assert response.status_code == 200
    assert response.headers.get("retry-after") == retry_after
    body = response.json()
    assert body["id"] == job.id
    assert body["status"] == status


async def test_get_unknown_job_is_404_problem(app) -> None:
    async with app_client(app) as client:
        response = await client.get("/api/v1/jobs/0000000000000000")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "not_found"


@pytest.mark.parametrize(
    "job_id", ["not-a-valid-id", "000000000000000", "00000000000000000", "ABCDEF0123456789"]
)
async def test_get_job_bad_id_shape_is_422(app, job_id: str) -> None:
    async with app_client(app) as client:
        response = await client.get(f"/api/v1/jobs/{job_id}")

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


async def test_finished_build_stamps_started_and_finished(app, built_page) -> None:
    async with app_client(app) as client:
        response = await client.get("/api/v1/jobs/aaaaaaaaaaaaaaaa")

    body = response.json()
    assert body["status"] == "done"
    assert body["queue_position"] is None
    assert body["started_at"] is not None
    assert body["finished_at"] is not None
    assert body["finished_at"] >= body["started_at"]
    assert "retry-after" not in response.headers


def _spend_bucket(app, path: str, rate: str, hits: int) -> None:
    """Draw `hits` requests from the limiter bucket slowapi keys by the request path."""
    item = limits.parse(rate)
    for _ in range(hits):
        assert app.state.limiter.limiter.hit(item, "127.0.0.1", path)


async def test_job_polling_has_its_own_600_per_minute_bucket(app, redis_client) -> None:
    job = make_job(id="dddddddddddddddd", queue_position=3)
    await JobQueue(redis_client, PIPELINE_VERSION, queue_cap=20).set_job(job)
    _spend_bucket(app, "/api/v1/dossiers", GET_READS_RATE_LIMIT, 120)
    _spend_bucket(app, f"/api/v1/jobs/{job.id}", JOB_POLL_RATE_LIMIT, 599)

    async with app_client(app) as client:
        reads_exhausted = await client.get("/api/v1/dossiers?limit=1")
        last_allowed_poll = await client.get(f"/api/v1/jobs/{job.id}")
        over_limit = await client.get(f"/api/v1/jobs/{job.id}")

    assert reads_exhausted.status_code == 429
    assert last_allowed_poll.status_code == 200
    assert over_limit.status_code == 429
