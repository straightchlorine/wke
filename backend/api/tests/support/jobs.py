"""Job factories for queue and worker tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from tests.support.constants import FIXTURE_PAGE_ID, FIXTURE_REV_ID, FIXTURE_TITLE
from wke.core.models import Job, JobProgress


def make_job(**overrides: Any) -> Job:
    """Build a queued Job for the recorded article; keyword overrides replace any field.

    Args:
        **overrides: Job fields to replace on the defaults.

    Returns:
        Job: a validated job stamped with the current time.
    """
    now = datetime.now(UTC)
    fields: dict[str, Any] = {
        "id": "aaaaaaaaaaaaaaaa",
        "page_id": FIXTURE_PAGE_ID,
        "rev_id": FIXTURE_REV_ID,
        "title": FIXTURE_TITLE,
        "status": "queued",
        "stage": "resolve",
        "progress": JobProgress(done=0, total=8),
        "poll_after_ms": 1000,
        "partial_available": False,
        "created_at": now,
        "updated_at": now,
    }
    fields.update(overrides)
    return Job(**fields)
