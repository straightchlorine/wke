"""POST /v1/rate: contract, one gate hold per passage, and the errors."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from prometheus_client import REGISTRY

from tests.support.fakes import FakeRater, FakeRequest
from wke_ml import main as main_module
from wke_ml.main import InferenceGate, create_app, lifespan
from wke_ml.rating import PROMPT_SHA256, PromptTooLong, RatingAbandoned, RatingUnavailable
from wke_ml.settings import Settings


def _body(*texts: str) -> dict[str, Any]:
    return {
        "title": "Ada Lovelace",
        "lead": "Ada was a mathematician.",
        "passages": [{"id": f"c{i}", "text": text} for i, text in enumerate(texts, start=1)],
    }


async def test_rate_response_contract(running_app: FastAPI, client: httpx.AsyncClient) -> None:
    rater = FakeRater({"a": 2.5, "b": None, "c": 1.0}, fallback=frozenset({"b"}))
    running_app.state.rater = rater

    response = await client.post("/v1/rate", json=_body("a", "b", "c"))

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"model", "prompt_sha256", "scores", "fallback_ids", "infer_seconds"}
    assert body["model"] == "fake-model.gguf"
    assert body["prompt_sha256"] == PROMPT_SHA256
    assert body["scores"] == {"c1": 2.5, "c2": None, "c3": 1.0}
    assert body["fallback_ids"] == ["c2"]
    assert body["infer_seconds"] > 0
    assert rater.calls == [
        ("Ada Lovelace", "Ada was a mathematician.", "a"),
        ("Ada Lovelace", "Ada was a mathematician.", "b"),
        ("Ada Lovelace", "Ada was a mathematician.", "c"),
    ]


async def test_each_passage_holds_the_slot_once(
    running_app: FastAPI, client: httpx.AsyncClient
) -> None:
    running_app.state.rater = FakeRater()
    labels = {"op": "rate"}
    before = REGISTRY.get_sample_value("wke_ml_infer_seconds_count", labels) or 0.0

    await client.post("/v1/rate", json=_body("a", "b", "c"))

    assert REGISTRY.get_sample_value("wke_ml_infer_seconds_count", labels) == before + 3


async def test_an_analyze_does_not_wait_for_a_rating_call_that_is_running(
    running_app: FastAPI, client: httpx.AsyncClient
) -> None:
    started, release = threading.Event(), threading.Event()

    class Blocking(FakeRater):
        def rate(self, title: str, lead: str, passage: str, should_stop=None):  # noqa: ANN001, ANN202
            started.set()
            release.wait(timeout=5)
            return super().rate(title, lead, passage)

    running_app.state.rater = Blocking()
    rating = asyncio.create_task(client.post("/v1/rate", json=_body("a")))
    await asyncio.to_thread(started.wait)
    try:
        analyze = await asyncio.wait_for(
            client.post("/v1/analyze", json={"lead": "a", "chunks": [{"id": "c1", "text": "a"}]}),
            timeout=2,
        )
        rating_done = rating.done()
    finally:
        release.set()
    await rating

    assert analyze.status_code == 200
    assert rating_done is False  # the analyze answered while the rating call still ran


async def test_a_full_rating_queue_does_not_shed_an_analyze(
    running_app: FastAPI, client: httpx.AsyncClient
) -> None:
    running_app.state.rate_gate = InferenceGate(0)

    rating = await client.post("/v1/rate", json=_body("a"))
    analyze = await client.post(
        "/v1/analyze", json={"lead": "a", "chunks": [{"id": "c1", "text": "a"}]}
    )

    assert (rating.status_code, analyze.status_code) == (503, 200)


async def test_a_rating_call_the_client_abandoned_is_told_to_stop_and_frees_its_gate(
    running_app: FastAPI, client: httpx.AsyncClient
) -> None:
    started = threading.Event()
    seen_stop = threading.Event()

    class Polling(FakeRater):
        def rate(self, title: str, lead: str, passage: str, should_stop=None):  # noqa: ANN001, ANN202
            started.set()
            for _ in range(500):  # waits at most 5 s for the stop
                if should_stop():
                    seen_stop.set()
                    raise RatingAbandoned()
                time.sleep(0.01)
            return super().rate(title, lead, passage)

    running_app.state.rater = Polling()
    rating = asyncio.create_task(client.post("/v1/rate", json=_body("a", "b")))
    await asyncio.to_thread(started.wait)

    rating.cancel()  # the client gives up
    with pytest.raises(asyncio.CancelledError):
        await rating
    assert await asyncio.to_thread(seen_stop.wait, 2)

    running_app.state.rater = FakeRater()
    follow_up = await asyncio.wait_for(client.post("/v1/rate", json=_body("c")), timeout=2)
    assert follow_up.status_code == 200
    assert running_app.state.rate_gate.running_seconds() == 0.0


async def test_a_disconnected_client_stops_the_running_call_and_the_next_passage_never_starts(
    running_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main_module, "DISCONNECT_POLL_SECONDS", 0.01)
    gate: InferenceGate = running_app.state.rate_gate
    started, stopped = threading.Event(), threading.Event()
    gone = asyncio.Event()

    class Away:
        async def is_disconnected(self) -> bool:
            return gone.is_set()

    def work() -> str:
        started.set()
        for _ in range(500):
            if stopped.is_set():
                return "stopped"
            time.sleep(0.01)
        return "ran to the end"

    task = asyncio.create_task(gate.run(Away(), None, "rate", work, on_abandon=stopped.set))
    await asyncio.to_thread(started.wait)
    gone.set()
    result, _ = await asyncio.wait_for(task, timeout=2)

    assert result == "stopped"
    assert gate.running_seconds() == 0.0


async def test_the_slot_is_held_until_an_abandoned_job_returns(
    running_app: FastAPI,
) -> None:
    gate: InferenceGate = running_app.state.rate_gate
    started, release = threading.Event(), threading.Event()
    abandoned = threading.Event()

    def work() -> str:
        started.set()
        release.wait(timeout=5)
        return "done"

    task = asyncio.create_task(
        gate.run(FakeRequest(), None, "rate", work, on_abandon=abandoned.set)
    )
    await asyncio.to_thread(started.wait)
    second = asyncio.create_task(gate.run(FakeRequest(), None, "rate", lambda: "second"))
    await asyncio.sleep(0.05)
    task.cancel()
    await asyncio.sleep(0.05)

    assert abandoned.is_set()
    assert not second.done()  # the thread still runs, so the slot is not free
    release.set()
    assert (await second)[0] == "second"
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_the_liveness_check_sees_a_rating_call_that_holds_its_gate_too_long(
    running_app: FastAPI, client: httpx.AsyncClient
) -> None:
    running_app.state.settings = running_app.state.settings.model_copy(
        update={"stuck_after_seconds": 0.01}
    )
    running_app.state.rate_gate._running_since = time.monotonic() - 5  # pyright: ignore[reportPrivateUsage]

    response = await client.get("/healthz")

    assert response.status_code == 503


@pytest.mark.parametrize("passages", [0, 9])
async def test_zero_or_nine_passages_are_rejected(
    running_app: FastAPI, client: httpx.AsyncClient, passages: int
) -> None:
    running_app.state.rater = FakeRater()

    response = await client.post("/v1/rate", json=_body(*["x"] * passages))

    assert response.status_code == 422


async def test_eight_passages_are_accepted(running_app: FastAPI, client: httpx.AsyncClient) -> None:
    running_app.state.rater = FakeRater()

    response = await client.post("/v1/rate", json=_body(*[f"p{i}" for i in range(8)]))

    assert response.status_code == 200
    assert len(response.json()["scores"]) == 8


async def test_a_default_service_has_no_rating_model_and_answers_503_without_retry_after(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post("/v1/rate", json=_body("a"))

    assert response.status_code == 503
    assert response.json()["code"] == "rating_unavailable"
    assert response.json()["status"] == 503
    assert "Retry-After" not in response.headers
    assert "retry_after" not in response.json()
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_a_rater_that_cannot_load_answers_503_rating_unavailable(
    running_app: FastAPI, client: httpx.AsyncClient
) -> None:
    running_app.state.rater = FakeRater(error=RatingUnavailable("did not load"))

    response = await client.post("/v1/rate", json=_body("a"))

    assert response.status_code == 503
    assert response.json()["code"] == "rating_unavailable"
    assert "did not load" in response.json()["detail"]


async def test_a_prompt_over_the_context_answers_422(
    running_app: FastAPI, client: httpx.AsyncClient
) -> None:
    running_app.state.rater = FakeRater(error=PromptTooLong("too many tokens"))

    response = await client.post("/v1/rate", json=_body("a"))

    assert response.status_code == 422
    assert response.json()["code"] == "prompt_too_long"


async def test_a_rating_is_shed_by_the_gate_like_any_job(
    running_app: FastAPI, client: httpx.AsyncClient
) -> None:
    running_app.state.rater = FakeRater()
    running_app.state.rate_gate = InferenceGate(0)

    response = await client.post("/v1/rate", json=_body("a"))

    assert response.status_code == 503
    assert response.json()["code"] == "queue_full"
    assert response.headers["Retry-After"] == "2"


async def test_an_expired_deadline_is_shed(running_app: FastAPI, client: httpx.AsyncClient) -> None:
    running_app.state.rater = FakeRater()

    response = await client.post("/v1/rate", json=_body("a"), headers={"X-Deadline-Ms": "0"})

    assert response.status_code == 503
    assert response.json()["code"] == "queue_full"


async def test_the_rater_is_built_by_the_factory_without_loading_a_model(
    settings_stub: Settings,
) -> None:
    app = create_app(settings_stub)
    built: list[Settings] = []

    def factory(settings: Settings) -> FakeRater:
        built.append(settings)
        return FakeRater()

    app.state.rater_factory = factory
    async with lifespan(app):
        assert isinstance(app.state.rater, FakeRater)

    assert built == [settings_stub]


async def test_a_real_disconnect_stops_the_running_passage_and_starts_no_further_one(
    running_app: FastAPI,
) -> None:
    """Over a raw ASGI channel, as a server gives it: the receive answers http.disconnect."""
    started, stopped = threading.Event(), threading.Event()

    class Waiting(FakeRater):
        def rate(self, title: str, lead: str, passage: str, should_stop=None):  # noqa: ANN001, ANN202
            started.set()
            for _ in range(500):
                if should_stop is not None and should_stop():
                    stopped.set()
                    break
                time.sleep(0.01)
            return super().rate(title, lead, passage)

    rater = Waiting()
    running_app.state.rater = rater
    request_body = json.dumps(_body("a", "b", "c")).encode()
    client_gone = asyncio.Event()
    delivered = False

    async def receive() -> dict[str, Any]:
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": request_body, "more_body": False}
        await client_gone.wait()
        return {"type": "http.disconnect"}

    sent: list[dict[str, Any]] = []

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/v1/rate",
        "raw_path": b"/v1/rate",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"content-type", b"application/json")],
        "client": ("127.0.0.1", 1),
        "server": ("test", 80),
        "state": {},
    }
    call = asyncio.create_task(running_app(scope, receive, send))
    await asyncio.to_thread(started.wait)
    client_gone.set()
    await asyncio.wait_for(call, timeout=5)

    assert stopped.is_set()
    assert len(rater.calls) == 1  # the other two passages never started
    assert running_app.state.rate_gate.running_seconds() == 0.0
