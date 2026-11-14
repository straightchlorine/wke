"""Job id hashing, poll pacing and the fresh queued Job record."""

from __future__ import annotations

import re

import pytest

from tests.support.constants import FIXTURE_PAGE_ID, FIXTURE_REV_ID, FIXTURE_TITLE
from wke.jobs.job_record import make_job_id, new_queued_job, poll_after_ms
from wke.logging_setup import request_id_var


def test_make_job_id_is_a_stable_16_hex_digest() -> None:
    job_id = make_job_id(FIXTURE_PAGE_ID, FIXTURE_REV_ID, "pv-1")

    assert re.fullmatch(r"[0-9a-f]{16}", job_id)
    assert job_id == make_job_id(FIXTURE_PAGE_ID, FIXTURE_REV_ID, "pv-1")


@pytest.mark.parametrize(
    ("page_id", "rev_id", "pipeline_version"),
    [(2, 7, "pv-1"), (1, 8, "pv-1"), (1, 7, "pv-2"), (17, 1, "pv-1")],
)
def test_make_job_id_changes_with_every_input(
    page_id: int, rev_id: int, pipeline_version: str
) -> None:
    assert make_job_id(page_id, rev_id, pipeline_version) != make_job_id(1, 7, "pv-1")


@pytest.mark.parametrize(
    ("depth", "expected"),
    [(0, 1000), (10, 1000), (11, 3000)],
)
def test_poll_after_ms_slows_down_only_above_ten_waiting_jobs(depth: int, expected: int) -> None:
    assert poll_after_ms(depth) == expected


@pytest.mark.parametrize(
    ("depth", "position", "poll_ms"),
    [(3, 4, 1000), (11, 12, 3000)],
)
def test_new_queued_job_is_queued_behind_the_depth_and_carries_the_request_id(
    depth: int, position: int, poll_ms: int
) -> None:
    token = request_id_var.set("req-abc12345")
    try:
        job = new_queued_job("a" * 16, FIXTURE_PAGE_ID, FIXTURE_REV_ID, FIXTURE_TITLE, depth=depth)
    finally:
        request_id_var.reset(token)

    assert (job.status, job.stage, job.progress.done) == ("queued", "resolve", 0)
    assert job.queue_position == position
    assert job.poll_after_ms == poll_ms
    assert job.request_id == "req-abc12345"
    assert job.created_at == job.updated_at
