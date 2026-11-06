"""wke-ml log lines carry the fixed fields and the request id, in JSON and on the console."""

from __future__ import annotations

import json
import logging
import re
import sys

import pytest
import structlog

from wke_ml.logging_setup import build_formatter, configure_logging, request_id_var

ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


def _record() -> logging.LogRecord:
    return logging.LogRecord("wke_ml.main", logging.INFO, __file__, 1, "POST %s", ("/v1/x",), None)


def test_json_line_has_the_fixed_fields_and_the_request_id() -> None:
    token = request_id_var.set("caller-12345678")
    try:
        payload = json.loads(build_formatter("json").format(_record()))
    finally:
        request_id_var.reset(token)
    assert list(payload) == ["ts", "level", "logger", "msg", "request_id"]
    assert (payload["level"], payload["msg"]) == ("info", "POST /v1/x")
    assert payload["request_id"] == "caller-12345678"


def test_json_line_keeps_an_explicit_request_id_and_renders_exceptions() -> None:
    token = request_id_var.set("from-the-context")
    try:
        try:
            raise ValueError("bad input")
        except ValueError:
            record = logging.LogRecord(
                "wke_ml.main", logging.ERROR, __file__, 1, "failed", (), sys.exc_info()
            )
        record.request_id = "explicit-1234"
        payload = json.loads(build_formatter("json").format(record))
    finally:
        request_id_var.reset(token)
    assert payload["request_id"] == "explicit-1234"
    assert "ValueError: bad input" in payload["exception"]


def test_json_line_has_no_request_id_outside_a_request() -> None:
    payload = json.loads(build_formatter("json").format(_record()))
    assert "request_id" not in payload


def test_configure_logging_routes_structlog_and_stdlib_through_one_format(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("INFO", "json")
    try:
        structlog.get_logger("wke_ml.test").info("from structlog", extra_field=1)
        logging.getLogger("wke_ml.test").info("from stdlib")
    finally:
        logging.getLogger().handlers.clear()
    lines = [json.loads(line) for line in capsys.readouterr().err.splitlines()]
    assert [(line["logger"], line["msg"]) for line in lines] == [
        ("wke_ml.test", "from structlog"),
        ("wke_ml.test", "from stdlib"),
    ]
    assert lines[0]["extra_field"] == 1


def test_console_line_is_colored_text() -> None:
    line = build_formatter("console").format(_record())
    assert ANSI_ESCAPE.search(line)
    assert re.match(r"\d\d:\d\d:\d\d \[info\s*\] POST /v1/x", ANSI_ESCAPE.sub("", line))
