"""Time to live of every Redis key family."""

from __future__ import annotations

MINUTE = 60
HOUR = 60 * MINUTE
DAY = 24 * HOUR

WM_SEARCH_TTL_SECONDS = HOUR
WM_RESOLVE_TTL_SECONDS = 10 * MINUTE
WM_HTML_TTL_SECONDS = DAY
WM_RELATED_TTL_SECONDS = DAY
SUMMARY_TTL_SECONDS = 30 * DAY
DOSSIER_TTL_SECONDS = 7 * DAY
DOSSIER_STRUCTURAL_TTL_SECONDS = 10 * MINUTE
JOB_TTL_SECONDS = HOUR
JOBKEY_TTL_SECONDS = HOUR
JOB_HEARTBEAT_TTL_SECONDS = 2 * MINUTE
TRENDING_SNAPSHOT_TTL_SECONDS = 3 * DAY
LATEST_REV_TTL_SECONDS = 7 * DAY
PAGEEDITS_TTL_SECONDS = 7 * DAY
RC_COUNTER_TTL_SECONDS = 2 * HOUR
# Worst-case hold time of a single _call:
#
# three 15s HTTP timeouts
#   + two 8s full-jitter retry sleeps (5xx or network-error path),
#   or two 15s timeouts
#       + one clamped 30s Retry-After sleep (rate-limit path), with margin.
#
# The lock is released as soon as the call finishes, so this is a ceiling.
WM_LOCK_TTL_MS = 90_000
WM_PACE_TTL_SECONDS = 5
WM_BUDGET_TTL_SECONDS = 2 * MINUTE
REBUILD_DEBOUNCE_TTL_SECONDS = 30 * MINUTE
WATCHER_HEARTBEAT_TTL_SECONDS = 30
# The resume cursor outlives a restart; a stale one only replays events.
WATCHER_LAST_ID_TTL_SECONDS = HOUR
