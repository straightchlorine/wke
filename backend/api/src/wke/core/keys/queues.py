"""Names of the job queues, in the order a worker polls them."""

from __future__ import annotations

QUEUE_INTERACTIVE = "q:interactive"
QUEUE_SUM_INTERACTIVE = "q:sum:interactive"
QUEUE_BACKGROUND = "q:background"
QUEUE_SUM_BACKGROUND = "q:sum:background"
QUEUE_PROCESSING = "q:processing"
QUEUE_PRIORITY_ORDER = (
    QUEUE_INTERACTIVE,
    QUEUE_SUM_INTERACTIVE,
    QUEUE_BACKGROUND,
    QUEUE_SUM_BACKGROUND,
)
