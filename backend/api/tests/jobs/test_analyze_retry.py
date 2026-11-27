"""The build's call to wke-ml analyze has its own deadline and retries, and logs each attempt."""

from __future__ import annotations

import json
import logging

import httpx
import pytest
from fakeredis.aioredis import FakeRedis

from tests.factories.dossier import make_fixture_dossier
from tests.support.builds import build_only, make_queue, stored_dossier
from tests.support.constants import FIXTURE_PAGE_ID, FIXTURE_REV_ID, PIPELINE_VERSION
from tests.support.jobs import make_job
from tests.support.metrics import metric_sample
from tests.support.ml_clients import analyze_down_client, make_ml_client
from tests.support.ml_payloads import analyze_response_json
from tests.support.services import make_service
from tests.support.workers import make_worker
from wke.clients.ml import MLUnavailable
from wke.clients.redis import RedisClient
from wke.clients.wikimedia import WikimediaClient
from wke.core import keys
from wke.core.citations import seed_pin
from wke.core.models import Job
from wke.jobs.build.run import _analyze_with_retries
from wke.settings import settings

RETRY = {"analyze_retries": 1, "analyze_retry_pause_ms": 0}
OLD_DOSSIER = make_fixture_dossier()
OLD_REV_ID = seed_pin(OLD_DOSSIER).rev_id
STRUCTURAL_TTL = 90
OLD_BODY = OLD_DOSSIER.model_dump_json()


def _flaky_client(failures: list[httpx.Response | Exception]) -> tuple[list[httpx.Request], object]:
    seen: list[httpx.Request] = []
    pending = list(failures)

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/v1/analyze" and pending:
            outcome = pending.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        return httpx.Response(200, json=analyze_response_json())

    return seen, make_ml_client(handle)


def _analyze_calls(seen: list[httpx.Request]) -> list[httpx.Request]:
    return [r for r in seen if r.url.path == "/v1/analyze"]


async def test_worker_deadline_is_sent_in_x_deadline_ms(
    redis_client: RedisClient, wikimedia_client: WikimediaClient
) -> None:
    seen, ml = _flaky_client([])

    await build_only(redis_client, wikimedia_client, ml, make_job(), analyze_deadline_ms=30000)  # type: ignore[arg-type]

    assert _analyze_calls(seen)[0].headers["X-Deadline-Ms"] == "30000"


async def test_default_deadline_is_8000(
    redis_client: RedisClient, wikimedia_client: WikimediaClient
) -> None:
    seen, ml = _flaky_client([])

    await build_only(redis_client, wikimedia_client, ml, make_job())  # type: ignore[arg-type]

    assert _analyze_calls(seen)[0].headers["X-Deadline-Ms"] == "8000"
    assert settings.analyze_deadline_ms == 8000
    assert settings.analyze_retries == 0


async def test_worker_passes_the_analyze_settings_to_run_build(
    redis_client: RedisClient,
    wikimedia_client: WikimediaClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    async def fake_run_build(_job: object, **kwargs: object) -> None:
        seen.update(kwargs)

    monkeypatch.setattr("wke.jobs.worker.run_build", fake_run_build)
    job_queue = make_queue(redis_client)
    worker = make_worker(
        redis_client,
        job_queue,
        analyze_deadline_ms=30000,
        analyze_retries=2,
        analyze_retry_pause_ms=5,
        analyze_retry_on_timeout=True,
        structural_ttl_seconds=90,
    )
    job = make_job()
    await job_queue.set_job(job)

    await worker._process(keys.QUEUE_INTERACTIVE, job.id)

    assert seen["analyze_deadline_ms"] == 30000
    assert seen["analyze_retries"] == 2
    assert seen["analyze_retry_pause_ms"] == 5
    assert seen["analyze_retry_on_timeout"] is True
    assert seen["structural_ttl_seconds"] == 90


async def test_one_retry_after_connect_error_then_ml_dossier(
    redis_client: RedisClient, wikimedia_client: WikimediaClient
) -> None:
    seen, ml = _flaky_client([httpx.ConnectError("refused")])
    job = make_job()

    await build_only(redis_client, wikimedia_client, ml, job, **RETRY)  # type: ignore[arg-type]

    assert len(_analyze_calls(seen)) == 2
    assert (await stored_dossier(redis_client, job)).build.analysis == "ml"


async def test_no_retry_after_4xx(
    redis_client: RedisClient, wikimedia_client: WikimediaClient
) -> None:
    seen, ml = _flaky_client([httpx.Response(422)])
    job = make_job()

    await build_only(redis_client, wikimedia_client, ml, job, **RETRY)  # type: ignore[arg-type]

    assert len(_analyze_calls(seen)) == 1
    assert (await stored_dossier(redis_client, job)).build.analysis == "structural"


async def test_timeout_is_not_retried_unless_set(
    redis_client: RedisClient, wikimedia_client: WikimediaClient
) -> None:
    seen, ml = _flaky_client([httpx.ReadTimeout("slow")])
    await build_only(redis_client, wikimedia_client, ml, make_job(), **RETRY)  # type: ignore[arg-type]
    assert len(_analyze_calls(seen)) == 1

    seen, ml = _flaky_client([httpx.ReadTimeout("slow")])
    job = make_job()
    await build_only(
        redis_client,
        wikimedia_client,
        ml,  # type: ignore[arg-type]
        job,
        analyze_retry_on_timeout=True,
        **RETRY,
    )
    assert len(_analyze_calls(seen)) == 2
    assert (await stored_dossier(redis_client, job)).build.analysis == "ml"


async def test_two_failures_store_the_structural_dossier(
    redis_client: RedisClient, wikimedia_client: WikimediaClient
) -> None:
    job = make_job()

    await build_only(redis_client, wikimedia_client, analyze_down_client(), job, **RETRY)

    assert (await stored_dossier(redis_client, job)).build.analysis == "structural"


async def test_log_line_carries_chunks_chars_elapsed_reason(
    redis_client: RedisClient,
    wikimedia_client: WikimediaClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    job = make_job()

    with caplog.at_level(logging.INFO, logger="wke.jobs.build.run"):
        await build_only(redis_client, wikimedia_client, analyze_down_client(), job, **RETRY)

    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("analyze_attempt")]
    assert len(lines) == 2
    for number, line in enumerate(lines, start=1):
        assert f"job_id={job.id} chunks=" in line
        assert " text_chars=" in line and " deadline_ms=8000 " in line and " elapsed_ms=" in line
        assert f"outcome=http_500 attempt={number}" in line


async def test_pause_runs_once_between_attempts() -> None:
    pauses: list[float] = []
    calls: list[int] = []

    async def fake_sleep(seconds: float) -> None:
        pauses.append(seconds)

    class FlakyML:
        async def analyze(self, **_kwargs: object) -> dict[str, object]:
            calls.append(1)
            if len(calls) == 1:
                raise MLUnavailable("connect_error")
            return {"ok": True}

    result = await _analyze_with_retries(
        FlakyML(),  # type: ignore[arg-type]
        make_job(),
        lead="",
        chunks=[],
        related_leads=[],
        page_id=1,
        deadline_ms=8000,
        retries=1,
        pause_ms=1500,
        retry_on_timeout=False,
        sleep=fake_sleep,
    )

    assert result == {"ok": True}
    assert pauses == [1.5]


async def test_each_attempt_is_counted_by_outcome(
    redis_client: RedisClient, wikimedia_client: WikimediaClient
) -> None:
    labels = {"outcome": "connect_error"}
    ok = {"outcome": "ok"}
    before = metric_sample("wke_analyze_attempts_total", labels)
    before_ok = metric_sample("wke_analyze_attempts_total", ok)
    _, ml = _flaky_client([httpx.ConnectError("refused")])

    await build_only(redis_client, wikimedia_client, ml, make_job(), **RETRY)  # type: ignore[arg-type]

    assert metric_sample("wke_analyze_attempts_total", labels) == before + 1
    assert metric_sample("wke_analyze_attempts_total", ok) == before_ok + 1


async def test_structural_ttl_setting_is_the_stored_ttl(
    redis_client: RedisClient, wikimedia_client: WikimediaClient
) -> None:
    job = make_job()

    await build_only(
        redis_client, wikimedia_client, analyze_down_client(), job, structural_ttl_seconds=90
    )

    ttl = await redis_client.ttl(keys.dossier(job.page_id, FIXTURE_REV_ID, PIPELINE_VERSION))
    assert 0 < ttl <= 90
    assert settings.dossier_structural_ttl_seconds == keys.DOSSIER_STRUCTURAL_TTL_SECONDS


@pytest.mark.parametrize(
    "failure",
    [
        httpx.ReadTimeout("slow"),
        httpx.Response(503),
        httpx.ConnectError("refused"),
    ],
)
async def test_defaults_make_one_call_and_store_structural(
    redis_client: RedisClient,
    wikimedia_client: WikimediaClient,
    failure: httpx.Response | Exception,
) -> None:
    seen, ml = _flaky_client([failure, failure])
    job = make_job()

    await build_only(redis_client, wikimedia_client, ml, job)  # type: ignore[arg-type]

    assert len(_analyze_calls(seen)) == 1
    assert (await stored_dossier(redis_client, job)).build.analysis == "structural"


async def _store_old(
    redis_client: RedisClient,
    fake_redis: FakeRedis,
    *,
    left: int | None,
    rev_id: int = OLD_REV_ID,
    pointer_version: str = PIPELINE_VERSION,
    dossier: bool = True,
) -> None:
    """Store an older revision's dossier and the page pointer naming it.

    Args:
        redis_client: the RedisClient to write through.
        fake_redis: the fakeredis behind it, for the expiry.
        left: seconds the dossier has left; None for no expiry.
        rev_id: the revision the pointer and the dossier carry.
        pointer_version: the pipeline version the pointer carries.
        dossier: False to leave the pointer without a dossier.
    """
    pointer = {"rev_id": rev_id, "pipeline_version": pointer_version, "built_at": "2026-01-01"}
    await redis_client.set(keys.ptr(FIXTURE_PAGE_ID), json.dumps(pointer))
    if dossier:
        key = keys.dossier(FIXTURE_PAGE_ID, rev_id, PIPELINE_VERSION)
        await redis_client.set(key, OLD_BODY)
        if left is not None:
            await fake_redis.expire(key, left)


async def _degraded_build(
    redis_client: RedisClient, wikimedia_client: WikimediaClient
) -> tuple[Job, Job]:
    """Run a build with wke-ml down and the short structural lifetime.

    Args:
        redis_client: the Redis client.
        wikimedia_client: the Wikimedia client over the recorded article.

    Returns:
        tuple: the job as run and the job as the queue stored it.
    """
    job = make_job()
    queue = await build_only(
        redis_client,
        wikimedia_client,
        analyze_down_client(),
        job,
        public_host="wke.example",
        structural_ttl_seconds=STRUCTURAL_TTL,
    )
    stored = await queue.get_job(job.id)
    assert stored is not None
    return job, stored


async def _pointed_rev(redis_client: RedisClient) -> int | None:
    """Read the revision the page pointer names.

    Args:
        redis_client: the Redis client.

    Returns:
        int | None: the pointed revision, or None when there is no pointer.
    """
    raw = await redis_client.get(keys.ptr(FIXTURE_PAGE_ID))
    return None if raw is None else json.loads(raw)["rev_id"]


async def test_longer_lived_dossier_keeps_the_pointer(
    redis_client: RedisClient,
    fake_redis: FakeRedis,
    wikimedia_client: WikimediaClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    await _store_old(redis_client, fake_redis, left=3 * 86_400)
    await fake_redis.sadd(keys.TRACKED, str(FIXTURE_PAGE_ID))
    await fake_redis.hset(keys.TRACKED_PAGE_IDS, "old title", str(FIXTURE_PAGE_ID))
    await fake_redis.zadd(keys.BUILT, {str(FIXTURE_PAGE_ID): 1.0})
    before = await redis_client.get(keys.ptr(FIXTURE_PAGE_ID))
    tracked = await fake_redis.smembers(keys.TRACKED)
    titles = await fake_redis.hgetall(keys.TRACKED_PAGE_IDS)
    labels = {"outcome": "degraded", "analysis": "structural"}
    built = metric_sample("wke_dossier_build_seconds_count", labels)
    caplog.set_level(logging.INFO, logger="wke.jobs.build.structural")

    job, stored = await _degraded_build(redis_client, wikimedia_client)

    assert await redis_client.get(keys.ptr(FIXTURE_PAGE_ID)) == before
    old_key = keys.dossier(FIXTURE_PAGE_ID, OLD_REV_ID, PIPELINE_VERSION)
    assert await redis_client.get(old_key) == OLD_BODY
    assert await redis_client.ttl(old_key) > STRUCTURAL_TTL
    view = await make_service(redis_client).get_dossier_view(FIXTURE_PAGE_ID, 8000, "json", False)
    assert view.id == OLD_DOSSIER.id
    assert seed_pin(view).rev_id == OLD_REV_ID
    assert view.build.analysis != "structural"
    new_key = keys.dossier(FIXTURE_PAGE_ID, FIXTURE_REV_ID, PIPELINE_VERSION)
    assert await redis_client.exists(new_key)
    assert 0 < await redis_client.ttl(new_key) <= STRUCTURAL_TTL
    assert tracked == {str(FIXTURE_PAGE_ID)}
    assert titles == {"old title": str(FIXTURE_PAGE_ID)}
    assert await fake_redis.smembers(keys.TRACKED) == tracked
    assert await fake_redis.hgetall(keys.TRACKED_PAGE_IDS) == titles
    assert await fake_redis.zscore(keys.BUILT, str(FIXTURE_PAGE_ID)) == 1.0
    assert await fake_redis.zcard(keys.BUILT) == 1
    assert stored.status == "done"
    assert stored.stage == "persist"
    assert stored.partial_available is True
    assert stored.result_url is not None
    assert not await redis_client.exists(keys.jobkey(FIXTURE_PAGE_ID, job.rev_id))
    assert metric_sample("wke_dossier_build_seconds_count", labels) == built + 1
    assert any(
        f"kept_rev_id={OLD_REV_ID} new_rev_id={FIXTURE_REV_ID}" in r.getMessage()
        for r in caplog.records
    )


async def test_dossier_without_expiry_is_kept(
    redis_client: RedisClient, fake_redis: FakeRedis, wikimedia_client: WikimediaClient
) -> None:
    await _store_old(redis_client, fake_redis, left=None)

    await _degraded_build(redis_client, wikimedia_client)

    assert await _pointed_rev(redis_client) == OLD_REV_ID
    old_key = keys.dossier(FIXTURE_PAGE_ID, OLD_REV_ID, PIPELINE_VERSION)
    assert await redis_client.get(old_key) == OLD_BODY
    assert await fake_redis.ttl(old_key) == -1
    new_key = keys.dossier(FIXTURE_PAGE_ID, FIXTURE_REV_ID, PIPELINE_VERSION)
    assert 0 < await fake_redis.ttl(new_key) <= STRUCTURAL_TTL


async def test_shorter_lived_dossier_is_replaced(
    redis_client: RedisClient, fake_redis: FakeRedis, wikimedia_client: WikimediaClient
) -> None:
    await _store_old(redis_client, fake_redis, left=STRUCTURAL_TTL)

    job, stored = await _degraded_build(redis_client, wikimedia_client)

    assert await _pointed_rev(redis_client) == FIXTURE_REV_ID
    assert (await stored_dossier(redis_client, job)).build.analysis == "structural"
    assert stored.status == "done"


async def test_no_pointer_writes_the_structural_dossier(
    redis_client: RedisClient, wikimedia_client: WikimediaClient
) -> None:
    job, _ = await _degraded_build(redis_client, wikimedia_client)

    assert await _pointed_rev(redis_client) == FIXTURE_REV_ID
    assert (await stored_dossier(redis_client, job)).build.analysis == "structural"


async def test_pointer_to_a_gone_dossier_is_replaced(
    redis_client: RedisClient, fake_redis: FakeRedis, wikimedia_client: WikimediaClient
) -> None:
    await _store_old(redis_client, fake_redis, left=None, dossier=False)

    await _degraded_build(redis_client, wikimedia_client)

    assert await _pointed_rev(redis_client) == FIXTURE_REV_ID


async def test_unreadable_pointer_is_replaced(
    redis_client: RedisClient, wikimedia_client: WikimediaClient
) -> None:
    await redis_client.set(keys.ptr(FIXTURE_PAGE_ID), "not json")

    await _degraded_build(redis_client, wikimedia_client)

    assert await _pointed_rev(redis_client) == FIXTURE_REV_ID


async def test_pointer_of_another_pipeline_version_is_replaced(
    redis_client: RedisClient, fake_redis: FakeRedis, wikimedia_client: WikimediaClient
) -> None:
    await _store_old(redis_client, fake_redis, left=None, pointer_version="other-pv")

    await _degraded_build(redis_client, wikimedia_client)

    assert await _pointed_rev(redis_client) == FIXTURE_REV_ID


@pytest.mark.parametrize(("left", "kept"), [(STRUCTURAL_TTL, False), (STRUCTURAL_TTL + 1, True)])
async def test_boundary_of_the_structural_lifetime(
    redis_client: RedisClient,
    fake_redis: FakeRedis,
    wikimedia_client: WikimediaClient,
    monkeypatch: pytest.MonkeyPatch,
    left: int,
    kept: bool,
) -> None:
    await _store_old(redis_client, fake_redis, left=None)
    old_key = keys.dossier(FIXTURE_PAGE_ID, OLD_REV_ID, PIPELINE_VERSION)
    real_ttl = RedisClient.ttl

    async def ttl(self: RedisClient, key: str) -> int:
        return left if key == old_key else await real_ttl(self, key)

    monkeypatch.setattr(RedisClient, "ttl", ttl)

    await _degraded_build(redis_client, wikimedia_client)

    assert await _pointed_rev(redis_client) == (OLD_REV_ID if kept else FIXTURE_REV_ID)


async def test_same_revision_is_not_overwritten(
    redis_client: RedisClient,
    fake_redis: FakeRedis,
    wikimedia_client: WikimediaClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    await _store_old(redis_client, fake_redis, left=3 * 86_400, rev_id=FIXTURE_REV_ID)
    key = keys.dossier(FIXTURE_PAGE_ID, FIXTURE_REV_ID, PIPELINE_VERSION)
    caplog.set_level(logging.INFO, logger="wke.jobs.build.structural")

    job, stored = await _degraded_build(redis_client, wikimedia_client)

    assert await redis_client.get(key) == OLD_BODY
    assert await redis_client.ttl(key) > STRUCTURAL_TTL
    assert await _pointed_rev(redis_client) == FIXTURE_REV_ID
    assert stored.status == "done"
    assert any(
        f"kept_rev_id={FIXTURE_REV_ID} new_rev_id={FIXTURE_REV_ID}" in r.getMessage()
        for r in caplog.records
    )
