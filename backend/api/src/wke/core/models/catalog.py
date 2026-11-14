"""API error, search candidate, catalog list item and service status models."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from wke.core.models.base import WkeModel
from wke.core.models.budgets import BudgetTokens

DossierState = Literal["ready", "partial", "building", "none"]
FreshnessState = Literal["fresh", "stale", "unknown"]
ErrorCode = Literal[
    "not_found",
    "not_article",
    "disambiguation",
    "validation_error",
    "rate_limited",
    "queue_full",
    "upstream_rate_limited",
    "upstream_budget",
    "upstream_unavailable",
    "not_built",
    "internal",
]


class TopicCandidate(WkeModel):
    """A search candidate with the state of its dossier."""

    page_id: int
    title: str
    description: str | None = None
    dossier_state: DossierState


class ApiError(WkeModel):
    """An RFC 9457 error body."""

    type: str
    title: str
    status: int
    detail: str | None = None
    code: ErrorCode
    request_id: str
    retry_after: int | None = None
    candidates: list[TopicCandidate] | None = None


class DossierListItem(WkeModel):
    """One built dossier in the catalog listing."""

    page_id: int
    title: str
    rev_id: int
    pinned_at: datetime
    freshness_state: FreshnessState
    edits_since_pin: int
    largest_budget_filled: BudgetTokens
    sections: int
    built_at: datetime


class Status(WkeModel):
    """Service status: queue depth, readiness and counters."""

    version: str
    pipeline_version: str | None = None
    redis: bool
    ml_ready: bool
    watcher_connected: bool
    trending_date: date | None = None
    trending_age_seconds: int | None = None
    queue_depth: int
    wikimedia_budget_remaining: int | None = None
