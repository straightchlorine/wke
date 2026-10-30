"""Log lines carry the fixed fields and the context ids, in JSON and on the console."""

from __future__ import annotations

import json
import logging
import re
import sys
from collections.abc import Iterator

import pytest
import structlog

from tests.support.constants import JOB_ID
from wke.logging_setup import (
    QUIET_LOGGERS,
    build_formatter,
    configure_logging,
    job_id_var,
    request_id_var,
)

ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


def _record(msg: str = "hello", level: int = logging.INFO, **extra: object) -> logging.LogRecord:
    record = logging.LogRecord("wke.x", level, __file__, 1, msg, None, None)
    record.__dict__.update(extra)
    return record


@pytest.fixture
def restore_logging() -> Iterator[None]:
    """Put back the root handlers, the levels and structlog's defaults after a test."""
    root = logging.getLogger()
    quieted = [logging.getLogger(name) for name in QUIET_LOGGERS]
    saved = (root.handlers[:], root.level, [logger.level for logger in quieted])
    yield
    root.handlers[:] = saved[0]
    root.setLevel(saved[1])
    for logger, level in zip(quieted, saved[2], strict=True):
        logger.setLevel(level)
    structlog.reset_defaults()


def test_json_line_falls_back_to_context_ids() -> None:
    t1, t2 = request_id_var.set("req-12345678"), job_id_var.set(JOB_ID)
    try:
        payload = json.loads(build_formatter("json").format(_record()))
    finally:
        request_id_var.reset(t1)
        job_id_var.reset(t2)
    assert payload["request_id"] == "req-12345678"
    assert payload["job_id"] == JOB_ID


def test_json_line_explicit_extra_wins_over_context() -> None:
    token = request_id_var.set("req-12345678")
    try:
        payload = json.loads(build_formatter("json").format(_record(request_id="explicit-1234")))
    finally:
        request_id_var.reset(token)
    assert payload["request_id"] == "explicit-1234"
    assert "job_id" not in payload


def test_json_line_has_the_fixed_fields_first_and_the_traceback() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        record = logging.LogRecord(
            "wke.x", logging.ERROR, __file__, 1, "failed %s", ("job",), sys.exc_info()
        )
    line = build_formatter("json").format(record)
    payload = json.loads(line)
    assert list(payload)[:4] == ["ts", "level", "logger", "msg"]
    assert set(payload) == {"ts", "level", "logger", "msg", "exception"}
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z", payload["ts"])
    assert (payload["level"], payload["logger"], payload["msg"]) == ("error", "wke.x", "failed job")
    assert "ValueError: boom" in payload["exception"]
    assert "\n" not in line


def test_json_line_turns_extra_fields_into_keys() -> None:
    payload = json.loads(build_formatter("json").format(_record("slow stage", stage="parse")))
    assert payload["stage"] == "parse"


def test_console_line_is_colored_text_with_the_same_fields() -> None:
    token = request_id_var.set("req-12345678")
    try:
        line = build_formatter("console").format(_record("slow stage", stage="parse"))
    finally:
        request_id_var.reset(token)
    assert ANSI_ESCAPE.search(line)
    plain = ANSI_ESCAPE.sub("", line)
    assert re.match(r"\d\d:\d\d:\d\d \[info\s*\] slow stage", plain)
    assert "[wke.x]" in plain
    assert "request_id=req-12345678" in plain
    assert "stage=parse" in plain


@pytest.mark.usefixtures("restore_logging")
def test_configure_logging_installs_one_handler_and_quiets_url_loggers() -> None:
    configure_logging("DEBUG", "json")
    root = logging.getLogger()
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0].formatter, structlog.stdlib.ProcessorFormatter)
    assert root.level == logging.DEBUG

    # These log request URLs, titles included, at INFO: they stay at WARNING
    # even when the app itself runs at DEBUG.
    assert [logging.getLogger(name).level for name in QUIET_LOGGERS] == [logging.WARNING] * 2


@pytest.mark.usefixtures("restore_logging")
def test_structlog_and_stdlib_loggers_share_the_handler(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("INFO", "json")
    structlog.get_logger("wke.build").info("build started", page_id=7)
    logging.getLogger("wke.worker").info("job done")
    structlog.get_logger("wke.build").debug("below the level")
    lines = [json.loads(line) for line in capsys.readouterr().err.splitlines()]
    assert [(line["logger"], line["msg"]) for line in lines] == [
        ("wke.build", "build started"),
        ("wke.worker", "job done"),
    ]
    assert lines[0]["page_id"] == 7
