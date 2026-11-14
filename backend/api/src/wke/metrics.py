"""Every Prometheus metric the wke-api processes export.

The api and the watcher each serve `/metrics` and set only the metrics of
their own work; the trending job leaves its timestamp in Redis for the api.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUESTS_TOTAL = Counter(
    "wke_http_requests_total",
    "HTTP requests handled, by route template, method and status class.",
    ["route", "method", "status_class"],
)
HTTP_REQUESTS_SECONDS = Histogram(
    "wke_http_requests_seconds",
    "HTTP request duration in seconds, by route template, method and status class.",
    ["route", "method", "status_class"],
)
JOB_STAGE_SECONDS = Histogram(
    "wke_job_stage_seconds",
    "Duration of one named pipeline stage, in seconds.",
    ["stage"],
)
JOBS_QUEUED = Gauge(
    "wke_jobs_queued",
    "Items currently waiting in a job queue, sampled at scrape time.",
    ["queue"],
)
WIKIMEDIA_REQUESTS_TOTAL = Counter(
    "wke_wikimedia_requests_total",
    "Outbound Wikimedia HTTP calls, by operation and response status.",
    ["op", "status"],
)
WIKIMEDIA_BUDGET_REJECTIONS_TOTAL = Counter(
    "wke_wikimedia_budget_rejections_total",
    "Calls rejected because the shared per-minute Wikimedia budget was exhausted.",
)
CACHE_REQUESTS_TOTAL = Counter(
    "wke_cache_requests_total",
    "Redis-backed cache lookups, by cache kind and hit/miss result.",
    ["kind", "result"],
)
TRENDING_LAST_SUCCESS_TIMESTAMP = Gauge(
    "wke_trending_last_success_timestamp",
    "Unix timestamp of generated_at on the stored trending:latest snapshot.",
)

DOSSIER_BUILD_SECONDS = Histogram(
    "wke_dossier_build_seconds",
    "Build seconds: to the persisted dossier for outcome partial or degraded, "
    "through the last summary for outcome complete.",
    ["outcome", "analysis"],
)
SUMMARY_STATE_TOTAL = Counter(
    "wke_summary_state_total",
    "Section summaries by terminal state.",
    ["state"],
)
WATCHER_CONNECTED = Gauge(
    "wke_watcher_connected",
    "1 while the recentchange SSE stream is connected.",
)
WATCHER_EVENTS_TOTAL = Counter(
    "wke_watcher_events_total",
    "Recentchange events processed, by outcome.",
    ["kind"],
)
WATCHER_LAST_EVENT_TIMESTAMP = Gauge(
    "wke_watcher_last_event_timestamp",
    "Unix timestamp of the last kept event.",
)
