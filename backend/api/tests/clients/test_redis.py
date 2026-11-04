"""RedisClient fails open: a Redis outage reads as an empty answer, except for BLMOVE."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

import fakeredis
import fakeredis.aioredis
import pytest
from redis.exceptions import RedisError

from wke.clients.redis import RedisClient

Call = Callable[[RedisClient], Awaitable[Any]]

# Each command with the value it returns while Redis is down.
FAIL_OPEN: list[tuple[str, Call, Any]] = [
    ("get", lambda r: r.get("k"), None),
    ("mget", lambda r: r.mget(["a", "b"]), [None, None]),
    ("set", lambda r: r.set("k", "v", ex=5), False),
    ("delete", lambda r: r.delete("k"), 0),
    ("incr", lambda r: r.incr("k"), None),
    ("expire", lambda r: r.expire("k", 5), False),
    ("exists", lambda r: r.exists("k"), False),
    ("lpush", lambda r: r.lpush("k", "v"), None),
    ("rpush", lambda r: r.rpush("k", "v"), None),
    ("llen", lambda r: r.llen("k"), 0),
    ("lrem", lambda r: r.lrem("k", 0, "v"), 0),
    ("ltrim", lambda r: r.ltrim("k", 0, 9), False),
    ("lrange", lambda r: r.lrange("k", 0, -1), []),
    ("zadd", lambda r: r.zadd("k", {"m": 1.0}), None),
    ("zrevrange", lambda r: r.zrevrange("k", 0, -1), []),
    ("zremrangebyrank", lambda r: r.zremrangebyrank("k", 0, 1), 0),
    ("zcount", lambda r: r.zcount("k", "-inf", "+inf"), 0),
    ("zcount_keys", lambda r: r.zcount_keys([("a", "0", "1"), ("b", "0", "1")]), [0, 0]),
    ("zscore", lambda r: r.zscore("k", "m"), None),
    ("sadd", lambda r: r.sadd("k", "m"), None),
    ("sismember", lambda r: r.sismember("k", "m"), False),
    ("smembers", lambda r: r.smembers("k"), set()),
    ("hset", lambda r: r.hset("k", "f", "v"), None),
    ("hget", lambda r: r.hget("k", "f"), None),
    ("delete_if_equals", lambda r: r.delete_if_equals("k", "token"), False),
    ("ttl", lambda r: r.ttl("k"), -2),
    ("ping", lambda r: r.ping(), False),
]


@pytest.fixture
def down_redis() -> RedisClient:
    """A RedisClient whose server refuses every command."""
    server = fakeredis.FakeServer()
    server.connected = False
    return RedisClient(fakeredis.aioredis.FakeRedis(server=server, decode_responses=True))


@pytest.mark.parametrize(("_name", "call", "default"), FAIL_OPEN, ids=[c[0] for c in FAIL_OPEN])
async def test_a_failed_command_returns_its_default(
    down_redis: RedisClient, _name: str, call: Call, default: Any
) -> None:
    assert await call(down_redis) == default


async def test_a_failed_command_is_logged_as_a_warning(
    down_redis: RedisClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="wke.clients.redis"):
        await down_redis.get("k")
    assert [r.getMessage() for r in caplog.records] == [
        "redis GET failed; using default: ConnectionError"
    ]


async def test_blmove_raises_so_an_outage_is_not_an_empty_queue(down_redis: RedisClient) -> None:
    with pytest.raises(RedisError):
        await down_redis.blmove("q:a", "q:b", 0.1)


async def test_blmove_moves_an_item_with_a_fractional_timeout(redis_client: RedisClient) -> None:
    await redis_client.rpush("q:a", "job-1")
    assert await redis_client.blmove("q:a", "q:b", 0.2) == "job-1"
    assert await redis_client.lrange("q:b", 0, -1) == ["job-1"]
