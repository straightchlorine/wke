"""Build job models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, HttpUrl

from wke.core.models.base import WkeModel
from wke.core.models.catalog import ApiError


class JobProgress(WkeModel):
    """Completed and total stages of a build job."""

    done: int
    total: int


class Job(WkeModel):
    """A dossier build job and its progress."""

    id: str = Field(pattern=r"^[0-9a-f]{16}$")
    page_id: int
    rev_id: int | None = None
    title: str | None = None
    status: Literal["queued", "running", "done", "failed"]
    stage: Literal[
        "resolve", "fetch", "parse", "related", "embed", "cluster", "summarize", "persist"
    ]
    progress: JobProgress
    queue_position: int | None = None
    poll_after_ms: int
    partial_available: bool
    result_url: HttpUrl | None = None
    error: ApiError | None = None
    created_at: datetime
    started_at: datetime | None = None
    updated_at: datetime
    finished_at: datetime | None = None
    # Submitting request's X-Request-ID, kept for log correlation across services.
    # Never served, only JobQueue.set_job re-adds it to the Redis record.
    request_id: str | None = Field(default=None, exclude=True)
