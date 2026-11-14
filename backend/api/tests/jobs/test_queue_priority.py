"""next_item() priority: q:interactive > q:sum:interactive > q:background > q:sum:background."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from wke.clients.redis import RedisClient
from wke.core import keys
from wke.jobs import queue as queue_module
from wke.jobs.queue import JobQueue

PIPELINE_VERSION = "test-pv"


class _FakeClock:
    """Stands in for `time` and `asyncio` inside wke.jobs.queue: sleeping advances time."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []
        self.asyncio = SimpleNamespace(sleep=self.sleep)

    def monotonic(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class _ScriptedRedis:
    """Stands in for redis.asyncio.Redis: each blmove replays the next outcome.

    An exception outcome is raised; anything else is returned. Once the
    script is used up, every blmove raises, as a Redis that stays down.
    """

    def __init__(self, *outcomes: Exception | str | None) -> None:
        self._outcomes = list(outcomes)
        self.blmove_calls = 0

    async def blmove(self, *args: object, **kwargs: object) -> str | None:
        self.blmove_calls += 1
        if not self._outcomes:
            raise RedisConnectionError("redis is down")
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _EmptyRedis:
    """Stands in for redis.asyncio.Redis: every queue is empty; records each blmove timeout."""

    def __init__(self) -> None:
        self.timeouts: list[float] = []

    async def blmove(self, first_list: str, second_list: str, timeout: float, *args: str) -> None:
        self.timeouts.append(timeout)
        await asyncio.sleep(0)
        return None


def _client_over(double: Any) -> RedisClient:
    """Wrap a test double that implements only the Redis calls the test makes."""
    return RedisClient(double)


@pytest.fixture
def fake_clock(monkeypatch: pytest.MonkeyPatch) -> _FakeClock:
    clock = _FakeClock()
    monkeypatch.setattr(queue_module, "time", clock)
    monkeypatch.setattr(queue_module, "asyncio", clock.asyncio)
    return clock


async def test_next_item_drains_in_strict_priority_order(redis_client: RedisClient) -> None:
    queue = JobQueue(redis_client, PIPELINE_VERSION, queue_cap=20)

    await redis_client.lpush(keys.QUEUE_SUM_BACKGROUND, "job-sb-1")
    await redis_client.lpush(keys.QUEUE_SUM_BACKGROUND, "job-sb-2")
    await redis_client.lpush(keys.QUEUE_BACKGROUND, "job-bg-1")
    await redis_client.lpush(keys.QUEUE_SUM_INTERACTIVE, "job-si-1")
    await redis_client.lpush(keys.QUEUE_INTERACTIVE, "job-int-1")

    seen: list[tuple[str, str]] = []
    for _ in range(5):
        item = await queue.next_item(timeout=1.0)
        assert item is not None
        seen.append(item)

    assert [queue_name for queue_name, _ in seen] == [
        keys.QUEUE_INTERACTIVE,
        keys.QUEUE_SUM_INTERACTIVE,
        keys.QUEUE_BACKGROUND,
        keys.QUEUE_SUM_BACKGROUND,
        keys.QUEUE_SUM_BACKGROUND,
    ]

    assert await queue.next_item(timeout=0.3) is None


async def test_next_item_prefers_interactive_pushed_after_background_already_queued(
    redis_client: RedisClient,
) -> None:
    queue = JobQueue(redis_client, PIPELINE_VERSION, queue_cap=20)

    # Interactive queue is re-checked on each poll cycle despite earlier
    # queueing of background items.
    await redis_client.lpush(keys.QUEUE_BACKGROUND, "job-bg-1")
    await redis_client.lpush(keys.QUEUE_INTERACTIVE, "job-int-1")

    first = await queue.next_item(timeout=1.0)
    second = await queue.next_item(timeout=1.0)

    assert first == (keys.QUEUE_INTERACTIVE, "job-int-1")
    assert second == (keys.QUEUE_BACKGROUND, "job-bg-1")


async def test_admit_enqueues_fifo_within_a_queue(redis_client: RedisClient) -> None:
    """Jobs admitted one after another are served in admission order, not LIFO."""
    queue = JobQueue(redis_client, PIPELINE_VERSION, queue_cap=20)

    first = await queue.admit(1, 100, "First")
    second = await queue.admit(2, 200, "Second")
    third = await queue.admit(3, 300, "Third")

    assert first != "ready" and second != "ready" and third != "ready"

    served = [await queue.next_item(timeout=1.0) for _ in range(3)]

    assert served == [
        (keys.QUEUE_INTERACTIVE, first.id),
        (keys.QUEUE_INTERACTIVE, second.id),
        (keys.QUEUE_INTERACTIVE, third.id),
    ]


async def test_next_item_backs_off_with_capped_doubling_delays_when_redis_is_down(
    fake_clock: _FakeClock,
) -> None:
    redis = _ScriptedRedis()
    queue = JobQueue(_client_over(redis), PIPELINE_VERSION, queue_cap=20)

    item = await queue.next_item(timeout=40.0)

    assert item is None
    # 0.5, 1, 2, 4, 8, then capped at 10; the last sleep stops at the deadline.
    assert fake_clock.sleeps == [0.5, 1.0, 2.0, 4.0, 8.0, 10.0, 10.0, 4.5]
    assert redis.blmove_calls == len(fake_clock.sleeps)


async def test_next_item_restarts_the_backoff_after_a_successful_poll(
    fake_clock: _FakeClock,
) -> None:
    down = RedisConnectionError("redis is down")
    redis = _ScriptedRedis(down, down, "job-1", down)
    queue = JobQueue(_client_over(redis), PIPELINE_VERSION, queue_cap=20)

    first = await queue.next_item(timeout=10.0)
    assert first == (keys.QUEUE_BACKGROUND, "job-1")
    assert fake_clock.sleeps == [0.5, 1.0]

    await queue.next_item(timeout=10.0)
    assert fake_clock.sleeps[2] == 0.5


async def test_next_item_never_blocks_past_the_deadline() -> None:
    redis = _EmptyRedis()
    queue = JobQueue(_client_over(redis), PIPELINE_VERSION, queue_cap=20)

    assert await queue.next_item(timeout=0.05) is None

    assert redis.timeouts
    assert max(redis.timeouts) <= 0.05
