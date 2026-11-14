"""Tests for the single-slot inference gate: shedding and deadlines."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable

import httpx
import pytest
from fastapi import FastAPI
from prometheus_client import REGISTRY

from tests.support.fakes import BlockingEmbedder, FakeRequest
from wke_ml.main import ClientDisconnectedError, DeadlineExceededError, InferenceGate

_ANALYZE_BODY = {"lead": "a", "chunks": [{"id": "c1", "text": "a"}]}


async def _wait_until(predicate: Callable[[], bool], timeout: float = 5.0) -> None:
    """Poll predicate until it is true, failing the test after timeout seconds."""
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        assert asyncio.get_running_loop().time() < deadline, "condition not reached in time"
        await asyncio.sleep(0.01)


async def _assert_gate_still_usable(gate: InferenceGate) -> None:
    """Check that a shed left no waiter counted and no slot held."""
    assert gate._waiting == 0  # pyright: ignore[reportPrivateUsage]
    result, _ = await gate.run(FakeRequest(), None, "analyze", lambda: "ok")
    assert result == "ok"


async def test_fifth_waiter_is_shed_with_503_and_retry_after(
    running_app: FastAPI,
    client: httpx.AsyncClient,
    shed_count: Callable[[str], float],
) -> None:
    gate = running_app.state.gate
    started = threading.Event()
    release = threading.Event()
    running_app.state.embedder = BlockingEmbedder(running_app.state.embedder, started, release)

    holder = asyncio.create_task(client.post("/v1/analyze", json=_ANALYZE_BODY))
    await asyncio.to_thread(started.wait)  # holder now holds the one slot

    waiters = [
        asyncio.create_task(client.post("/v1/analyze", json=_ANALYZE_BODY)) for _ in range(4)
    ]
    try:
        await _wait_until(lambda: gate._waiting == 4)
        before = shed_count("queue_full")

        response = await client.post("/v1/analyze", json=_ANALYZE_BODY)

        assert response.status_code == 503
        assert response.headers["Retry-After"] == "2"
        assert shed_count("queue_full") == before + 1
        body = response.json()
        assert body["code"] == "queue_full"
        assert body["status"] == 503
        assert REGISTRY.get_sample_value("wke_ml_inflight") == 1

        release.set()
        holder_response = await holder
        waiter_responses = await asyncio.gather(*waiters)
        assert holder_response.status_code == 200
        assert all(r.status_code == 200 for r in waiter_responses)
        assert REGISTRY.get_sample_value("wke_ml_inflight") == 0
    finally:
        release.set()
        for task in (holder, *waiters):
            task.cancel()
        await asyncio.gather(holder, *waiters, return_exceptions=True)


async def test_deadline_exceeded_while_slot_held_sheds_with_503(
    running_app: FastAPI, client: httpx.AsyncClient
) -> None:
    gate = running_app.state.gate
    await gate._semaphore.acquire()
    try:
        response = await client.post(
            "/v1/analyze",
            json=_ANALYZE_BODY,
            headers={"X-Deadline-Ms": "10"},
        )
        assert response.status_code == 503
        assert "Retry-After" in response.headers
    finally:
        gate._semaphore.release()


async def test_disconnected_client_sheds_without_running_fn(
    shed_count: Callable[[str], float],
) -> None:
    gate = InferenceGate(max_queue=4)
    ran = False

    def fn() -> str:
        nonlocal ran
        ran = True
        return "result"

    before = shed_count("disconnected")

    with pytest.raises(ClientDisconnectedError):
        await gate.run(FakeRequest(disconnected=True), None, "analyze", fn)

    assert ran is False
    assert shed_count("disconnected") == before + 1
    await _assert_gate_still_usable(gate)


@pytest.mark.parametrize(
    ("deadline_ms", "hold_slot"),
    [(0, False), (100, False), (50, True)],
    ids=["expired_at_entry", "below_min_start", "timeout_while_slot_held"],
)
async def test_gate_sheds_on_deadline_and_leaks_nothing(
    deadline_ms: float, hold_slot: bool, shed_count: Callable[[str], float]
) -> None:
    gate = InferenceGate(max_queue=4)
    before = shed_count("deadline")
    if hold_slot:
        await gate._semaphore.acquire()  # pyright: ignore[reportPrivateUsage]

    try:
        with pytest.raises(DeadlineExceededError):
            await gate.run(FakeRequest(), deadline_ms, "analyze", lambda: "never")
    finally:
        if hold_slot:
            gate._semaphore.release()  # pyright: ignore[reportPrivateUsage]

    assert shed_count("deadline") == before + 1
    await _assert_gate_still_usable(gate)


async def test_gate_runs_a_job_with_room_in_the_deadline() -> None:
    gate = InferenceGate(max_queue=4)

    result, elapsed = await gate.run(FakeRequest(), 5_000, "analyze", lambda: "done")

    assert result == "done"
    assert elapsed >= 0.0
    assert gate.running_seconds() == 0.0
