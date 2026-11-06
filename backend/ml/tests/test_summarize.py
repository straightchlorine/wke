"""Tests for /v1/summarize: schema shape and request validation."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi import FastAPI


async def test_summarize_matches_machine_summary_schema(
    client: httpx.AsyncClient, running_app: FastAPI
) -> None:
    response = await client.post(
        "/v1/summarize",
        json={"text": "Short article text.", "min_length": 5, "max_length": 20},
    )
    assert response.status_code == 200
    body = response.json()
    settings = running_app.state.settings

    assert body["kind"] == "machine_summary"
    assert isinstance(body["text"], str) and body["text"]
    assert body["model"] == settings.summarize_model
    assert body["model_revision"] == settings.summarize_model_revision
    assert body["params"]["num_beams"] == 4
    assert body["params"]["min_length"] == 5
    assert body["params"]["max_length"] == 20
    assert body["params"]["input_tokens"] == 3  # whitespace tokens of the stub backend
    assert isinstance(body["generated_at"], str)
    assert body["truncated"] is False


async def test_summarize_defaults_allow_a_sentence_to_finish(client: httpx.AsyncClient) -> None:
    response = await client.post("/v1/summarize", json={"text": "Some article text."})

    params = response.json()["params"]
    assert (params["num_beams"], params["min_length"], params["max_length"]) == (4, 30, 128)


async def test_summarize_reports_length_limit_stop(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/v1/summarize",
        json={"text": "word " * 100, "min_length": 5, "max_length": 20},
    )

    assert response.json()["truncated"] is True


@pytest.mark.parametrize(
    "payload",
    [
        {"text": ""},
        {"text": "x" * 20_001},
        {"text": "ok", "min_length": 50, "max_length": 40},
        {"text": "ok", "min_length": 0},
        {"text": "ok", "max_length": 257},
        {"text": "ok", "num_beams": 5},
    ],
    ids=["empty", "oversized", "min_over_max", "min_length_0", "max_length_257", "num_beams_5"],
)
async def test_summarize_rejects_invalid(
    client: httpx.AsyncClient, payload: dict[str, Any]
) -> None:
    response = await client.post("/v1/summarize", json=payload)

    assert response.status_code == 422


@pytest.mark.parametrize("chunk_ids", [[], ["c1", "c2"]])
async def test_summarize_input_chunk_ids_round_trip(
    client: httpx.AsyncClient, chunk_ids: list[str]
) -> None:
    payload: dict[str, Any] = {"text": "Some article text."}
    if chunk_ids:
        payload["input_chunk_ids"] = chunk_ids

    response = await client.post("/v1/summarize", json=payload)

    assert response.json()["input_chunk_ids"] == chunk_ids


async def test_summarize_accepts_equal_min_and_max_length(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/v1/summarize", json={"text": "ok", "min_length": 40, "max_length": 40}
    )

    assert response.status_code == 200
