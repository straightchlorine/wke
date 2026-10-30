"""Logging shared by every wke-api entrypoint: JSON lines or console lines.

Both formats carry ts, level, logger, msg and, when set, request_id, job_id
and any extra fields.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Literal

import structlog
from structlog.typing import EventDict, Processor, WrappedLogger

LogFormat = Literal["json", "console"]

# Bound per request (API) and per queue item (worker):
# every log line, and the outbound wke-ml call, carries the caller's ids
# without threading them through each function signature.
request_id_var: ContextVar[str | None] = ContextVar("wke_request_id", default=None)
job_id_var: ContextVar[str | None] = ContextVar("wke_job_id", default=None)

# log request URLs, titles included, at INFO.
QUIET_LOGGERS = ("httpx", "mcp.server.streamable_http")


def add_context_ids(_logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
    """Fill request_id and job_id from the context when the event did not set them.

    Args:
        _logger: the wrapped logger (unused).
        _method: the log method name (unused).
        event_dict: the event being built.

    Returns:
        EventDict: the event, with the ids the context holds.
    """
    for key, var in (("request_id", request_id_var), ("job_id", job_id_var)):
        if event_dict.get(key) is None and (value := var.get()) is not None:
            event_dict[key] = value
    return event_dict


_LEADING_KEYS = ("ts", "level", "logger", "msg")


def lead_with_fixed_keys(_logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
    """Order an event so ts, level, logger and msg come first in its JSON line.

    Args:
        _logger: the wrapped logger (unused).
        _method: the log method name (unused).
        event_dict: the event being rendered.

    Returns:
        EventDict: the same keys, the fixed ones first.
    """
    leading = {key: event_dict.pop(key) for key in _LEADING_KEYS if key in event_dict}
    return {**leading, **event_dict}


# Run for every event, whether it came from structlog or a standard-library logger.
_PRE_CHAIN: list[Processor] = [
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.stdlib.ExtraAdder(),
    add_context_ids,
]


def build_formatter(fmt: LogFormat) -> logging.Formatter:
    """Build the root handler's formatter for one output format.

    Args:
        fmt: "json" for one JSON object per line (ts in UTC), "console" for
            colored, aligned lines with readable tracebacks (local time).

    Returns:
        logging.Formatter: renders structlog and standard-library records alike.
    """
    if fmt == "console":
        render: list[Processor] = [
            structlog.processors.TimeStamper(fmt="%H:%M:%S", utc=False, key="ts"),
            structlog.dev.ConsoleRenderer(colors=True, timestamp_key="ts"),
        ]
    else:
        render = [
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="ts"),
            structlog.processors.format_exc_info,
            structlog.processors.EventRenamer("msg"),
            lead_with_fixed_keys,
            structlog.processors.JSONRenderer(),
        ]
    return structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=_PRE_CHAIN,
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, *render],
    )


def configure_logging(level: str, fmt: LogFormat = "json") -> None:
    """Install the shared root handler and quiet noisy third-party loggers.

    Args:
        level: a Python logging level name, e.g. "INFO".
        fmt: the output format, see `build_formatter`.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(build_formatter(fmt))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    for name in QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    structlog.configure(
        processors=[
            *_PRE_CHAIN,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
    )
