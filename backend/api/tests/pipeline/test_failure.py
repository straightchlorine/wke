"""The error a failed job carries and what failing a job cleans up."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tests.support.builds import make_queue
from tests.support.constants import FIXTURE_REV_ID, JOB_ID, PIPELINE_VERSION
from tests.support.jobs import make_job
from wke.clients.redis import RedisClient
from wke.core import keys
from wke.core.errors import ApiException
from wke.jobs.build.failure import fail_job, job_failure_error
from wke.jobs.build.payload import ptr_json


def test_failure_error_of_an_api_exception_keeps_its_status_code_and_detail() -> None:
    error = job_failure_error(
        ApiException(502, "upstream_unavailable", "Wikimedia is down"), JOB_ID
    )
    assert (error.status, error.code, error.detail) == (
        502,
        "upstream_unavailable",
        "Wikimedia is down",
    )
    assert error.type.endswith("/upstream_unavailable")


@pytest.mark.parametrize(
    ("request_id", "expected"), [("req-12345678", "req-12345678"), (None, None)]
)
def test_failure_error_of_a_bug_hides_the_message_and_keeps_a_request_id(
    request_id: str | None, expected: str | None
) -> None:
    error = job_failure_error(RuntimeError("boom"), JOB_ID, request_id)
    assert (error.status, error.code) == (500, "internal")
    assert "boom" not in (error.detail or "")
    if expected is None:
        assert len(error.request_id) >= 8
    else:
        assert error.request_id == expected


@pytest.mark.parametrize(
    ("ptr_rev_id", "ptr_version", "ptr_survives"),
    [
        (FIXTURE_REV_ID, PIPELINE_VERSION, False),
        (FIXTURE_REV_ID + 1, PIPELINE_VERSION, True),
        (FIXTURE_REV_ID, "another-pipeline-version", True),
    ],
)
async def test_fail_job_cleans_up_its_own_build_and_spares_other_builds(
    redis_client: RedisClient, ptr_rev_id: int, ptr_version: str, ptr_survives: bool
) -> None:
    job = make_job(status="running", stage="persist")
    queue = make_queue(redis_client)
    await queue.set_job(job)
    dossier_key = keys.dossier(job.page_id, FIXTURE_REV_ID, PIPELINE_VERSION)
    await redis_client.set(dossier_key, "{}")
    await redis_client.set(
        keys.ptr(job.page_id), ptr_json(ptr_rev_id, ptr_version, datetime.now(UTC))
    )
    await redis_client.set(keys.jobkey(job.page_id, FIXTURE_REV_ID), job.id)

    await fail_job(job, redis_client, queue, PIPELINE_VERSION, RuntimeError("boom"))

    stored = await queue.get_job(job.id)
    assert stored is not None
    assert (stored.status, stored.queue_position) == ("failed", None)
    assert stored.error is not None
    assert stored.finished_at == stored.updated_at
    assert await redis_client.get(dossier_key) is None
    assert await redis_client.get(keys.jobkey(job.page_id, FIXTURE_REV_ID)) is None
    assert (await redis_client.get(keys.ptr(job.page_id)) is not None) is ptr_survives
