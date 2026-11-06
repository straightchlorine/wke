"""Logging for wke-ml: JSON lines or colored console lines, as wke-api writes them.

Both formats carry ts, level, logger, msg and, while a request is served,
request_id. Standard-library loggers (ours, uvicorn) and structlog loggers go
through one root handler, so every line has the same shape.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Literal

import structlog
from structlog.typing import EventDict, Processor, WrappedLogger

LogFormat = Literal["json", "console"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

# Set per request by the add_request_id middleware in main.py.
request_id_var: ContextVar[str | None] = ContextVar("wke_ml_request_id", default=None)

_LEADING_KEYS = ("ts", "level", "logger", "msg")


def add_request_id(_logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
    """Fill request_id from the context when the event did not set it.

    Args:
        _logger: the wrapped logger (unused).
        _method: the log method name (unused).
        event_dict: the event being built.

    Returns:
        EventDict: the event, with the request id the context holds.
    """
    if event_dict.get("request_id") is None and (value := request_id_var.get()) is not None:
        event_dict["request_id"] = value
    return event_dict


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
    add_request_id,
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


def configure_logging(level: LogLevel, fmt: LogFormat = "json") -> None:
    """Install the shared root handler.

    Args:
        level: a Python logging level name.
        fmt: the output format, see `build_formatter`.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(build_formatter(fmt))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    structlog.configure(
        processors=[*_PRE_CHAIN, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
    )
