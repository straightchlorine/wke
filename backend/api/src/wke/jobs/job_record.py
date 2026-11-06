"""Job record helpers: deterministic ids, fresh queued Jobs and poll pacing."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from wke.core.models import Job, JobProgress
from wke.logging_setup import request_id_var

TOTAL_STAGES = 8
INITIAL_POLL_AFTER_MS = 1000
BUSY_POLL_AFTER_MS = 3000
BUSY_QUEUE_DEPTH_THRESHOLD = 10


def make_job_id(page_id: int, rev_id: int, pipeline_version: str) -> str:
    """Build the idempotent job id.

    Args:
        page_id: Wikipedia page id.
        rev_id: pinned revision id.
        pipeline_version: PIPELINE_VERSION setting.

    Returns:
        str: deterministic 16-char hex hash of the input tuple.
    """
    payload = f"{page_id}:{rev_id}:{pipeline_version}".encode()
    return hashlib.sha256(payload).hexdigest()[:16]


def poll_after_ms(depth_before_admission: int) -> int:
    """Pick the client's first poll delay from the queue depth.

    Args:
        depth_before_admission: the combined queue depth before admission.

    Returns:
        int: milliseconds before the first status poll.
    """
    if depth_before_admission > BUSY_QUEUE_DEPTH_THRESHOLD:
        return BUSY_POLL_AFTER_MS
    return INITIAL_POLL_AFTER_MS


def new_queued_job(job_id: str, page_id: int, rev_id: int, title: str, depth: int) -> Job:
    """Build the queued Job record for a fresh admission.

    Args:
        job_id: the deterministic job id.
        page_id: Wikipedia page id.
        rev_id: pinned revision id.
        title: normalized article title.
        depth: the combined queue depth before this admission.

    Returns:
        Job: status "queued", stage "resolve".
    """
    now = datetime.now(UTC)
    return Job(
        id=job_id,
        page_id=page_id,
        rev_id=rev_id,
        title=title,
        status="queued",
        stage="resolve",
        # done=0: the build run counts "resolve" as its own first completed stage;
        # every Job starts at 0, with total being the placeholder until run
        # gets the real summary section count and widens it.
        progress=JobProgress(done=0, total=TOTAL_STAGES),
        queue_position=depth + 1,
        poll_after_ms=poll_after_ms(depth),
        partial_available=False,
        created_at=now,
        updated_at=now,
        request_id=request_id_var.get(),
    )
