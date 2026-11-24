"""The build's analyze call: its own deadline, retries, and one log line per attempt."""

from __future__ import annotations

import logging

import httpx
import pytest

from tests.support.builds import build_only, make_queue, stored_dossier
from tests.support.constants import FIXTURE_REV_ID, PIPELINE_VERSION
from tests.support.jobs import make_job
from tests.support.metrics import metric_sample
from tests.support.ml_clients import analyze_down_client, make_ml_client
from tests.support.ml_payloads import analyze_response_json
from tests.support.workers import make_worker
from wke.clients.ml import MLUnavailable
from wke.clients.redis import RedisClient
from wke.clients.wikimedia import WikimediaClient
from wke.core import keys
from wke.jobs.build.run import _analyze_with_retries
from wke.settings import settings

RETRY = {"analyze_retries": 1, "analyze_retry_pause_ms": 0}


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
