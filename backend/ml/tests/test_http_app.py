"""Tests for the HTTP surface of wke-ml: request ids, metrics, response contract."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx
import pytest
from prometheus_client import REGISTRY

from wke_ml.logging_setup import build_formatter
from wke_ml.metrics import SHED_REASONS


async def test_analyze_response_contract(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/v1/analyze",
        json={"lead": "A short lead.", "chunks": [{"id": "c1", "text": "some text"}]},
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "model",
        "model_revision",
        "relevance",
        "cluster_ids",
        "representatives",
        "edges",
        "infer_seconds",
    }
    assert isinstance(body["model"], str) and body["model"]
    assert isinstance(body["model_revision"], str) and body["model_revision"]
    assert 0.0 <= body["relevance"]["c1"] <= 1.0
    assert isinstance(body["cluster_ids"]["c1"], int)
    assert body["representatives"] == ["c1"]
    assert body["edges"] == []
    assert body["infer_seconds"] > 0


@pytest.mark.parametrize(
    ("path", "body", "op"),
    [
        ("/v1/analyze", {"lead": "a", "chunks": [{"id": "c1", "text": "a"}]}, "analyze"),
        ("/v1/summarize", {"text": "Some text."}, "summarize"),
    ],
)
async def test_inference_latency_is_observed_per_operation(
    client: httpx.AsyncClient, path: str, body: dict[str, Any], op: str
) -> None:
    labels = {"op": op}
    before = REGISTRY.get_sample_value("wke_ml_infer_seconds_count", labels) or 0.0

    await client.post(path, json=body)

    assert REGISTRY.get_sample_value("wke_ml_infer_seconds_count", labels) == before + 1


async def test_valid_request_id_is_echoed(client: httpx.AsyncClient) -> None:
    response = await client.get("/healthz", headers={"X-Request-ID": "caller-12345678"})

    assert response.headers["X-Request-ID"] == "caller-12345678"


@pytest.mark.parametrize(
    "sent",
    ["short", "bad chars here!", "a" * 65],
    ids=["too_short", "bad_characters", "too_long"],
)
async def test_invalid_request_id_is_replaced(client: httpx.AsyncClient, sent: str) -> None:
    response = await client.get("/healthz", headers={"X-Request-ID": sent})

    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["X-Request-ID"])


async def test_request_id_is_generated_when_absent(client: httpx.AsyncClient) -> None:
    response = await client.get("/healthz")

    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["X-Request-ID"])


async def test_unparseable_deadline_header_is_ignored(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/v1/analyze",
        json={"lead": "a", "chunks": [{"id": "c1", "text": "a"}]},
        headers={"X-Deadline-Ms": "soon"},
    )

    assert response.status_code == 200


async def test_metrics_endpoint_precreates_shed_labels(client: httpx.AsyncClient) -> None:
    response = await client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    text = response.text
    assert "wke_ml_infer_seconds" in text
    assert "wke_ml_inflight" in text
    for reason in SHED_REASONS:
        assert f'wke_ml_shed_total{{reason="{reason}"}}' in text
        assert REGISTRY.get_sample_value("wke_ml_shed_total", {"reason": reason}) is not None


async def test_request_id_is_logged_on_the_access_line(
    client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="wke_ml.main"):
        await client.post(
            "/v1/summarize",
            json={"text": "Some text to summarise."},
            headers={"X-Request-ID": "caller-12345678"},
        )
    formatter = build_formatter("json")
    lines = [json.loads(formatter.format(r)) for r in caplog.records]
    assert any(
        line.get("request_id") == "caller-12345678" and "/v1/summarize" in line["msg"]
        for line in lines
    )


async def test_probe_paths_are_not_logged_at_info(
    client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="wke_ml.main"):
        for path in ("/healthz", "/readyz", "/metrics"):
            await client.get(path)

    assert [r for r in caplog.records if r.name == "wke_ml.main"] == []
