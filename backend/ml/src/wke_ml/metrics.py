"""Every Prometheus metric wke-ml exports, defined once."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

SHED_REASONS = ("queue_full", "deadline", "disconnected")

INFER_SECONDS = Histogram(
    "wke_ml_infer_seconds",
    "Inference latency in seconds",
    ["op"],
)
INFLIGHT = Gauge(
    "wke_ml_inflight",
    "Inference jobs currently running",
)
SHED_TOTAL = Counter(
    "wke_ml_shed_total",
    "Inference jobs shed before running",
    ["reason"],
)
# Pre-create every reason so the series reads 0 (not "no data") before the first shed.
for _reason in SHED_REASONS:
    SHED_TOTAL.labels(reason=_reason)
