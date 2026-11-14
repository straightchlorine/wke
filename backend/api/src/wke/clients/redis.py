"""Fail-open async Redis wrapper."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

RedisFactory = Callable[[str], Redis]

_DELETE_IF_EQUALS_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
else
  return 0
end
"""


def default_redis_factory(url: str) -> Redis:
    """Build a redis.asyncio.Redis from a URL.

    Tests replace this factory with one that returns a fakeredis client.

    Args:
        url: Redis connection URL.

    Returns:
        Redis: an async Redis client, decode_responses=True.
    """
    return Redis.from_url(url, decode_responses=True)


async def _fail_open(label: str, awaitable: Awaitable[Any], default: Any) -> Any:
    try:
        return await awaitable
    except RedisError as exc:
        logger.warning("redis %s failed; using default: %s", label, exc.__class__.__name__)
        return default


class RedisClient:
    """Thin fail-open wrapper around redis.asyncio, sized to wke-api's needs."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def get(self, key: str) -> str | None:
        """Read a string value, or None if the key is missing or Redis failed.

        Args:
            key: the Redis key.

        Returns:
            str | None: the stored value.
        """
        return await _fail_open("GET", self._redis.get(key), None)

    async def mget(self, keys: list[str]) -> list[str | None]:
        """Fetch many keys in one round trip.

        Args:
            keys: keys to read.

        Returns:
            list[str | None]: one value per key, in order; all None if
            Redis failed (fail open, like `get`).
        """
        if not keys:
            return []
        default: list[str | None] = [None] * len(keys)
        return await _fail_open("MGET", self._redis.mget(keys), default)

    async def set(
        self,
        key: str,
        value: str,
        ex: int | None = None,
        px: int | None = None,
        nx: bool = False,
    ) -> bool:
        """Write a string value, optionally with an expiry or only if absent.

        Args:
            key: the Redis key.
            value: the value to store.
            ex: expiry in seconds, or None for no expiry.
            px: expiry in milliseconds, or None.
            nx: True to write only when the key does not exist.

        Returns:
            bool: True if the value was written; False if nx refused or Redis failed.
        """
        result = await _fail_open("SET", self._redis.set(key, value, ex=ex, px=px, nx=nx), None)
        return bool(result)

    async def delete(self, *keys: str) -> int:
        """Delete keys.

        Args:
            *keys: the keys to delete.

        Returns:
            int: how many keys were removed; 0 if Redis failed.
        """
        return await _fail_open("DEL", self._redis.delete(*keys), 0)

    async def incr(self, key: str) -> int | None:
        """Increment an integer counter by one.

        Args:
            key: the counter key.

        Returns:
            int | None: the new value, or None if Redis failed.
        """
        return await _fail_open("INCR", self._redis.incr(key), None)

    async def expire(self, key: str, seconds: int) -> bool:
        """Set a key's time to live.

        Args:
            key: the Redis key.
            seconds: time to live in seconds.

        Returns:
            bool: True if the key exists and the expiry was set.
        """
        return await _fail_open("EXPIRE", self._redis.expire(key, seconds), False)

    async def exists(self, key: str) -> bool:
        """Tell whether a key exists.

        Args:
            key: the Redis key.

        Returns:
            bool: True if the key exists; False if it does not or Redis failed.
        """
        result = await _fail_open("EXISTS", self._redis.exists(key), 0)
        return bool(result)

    async def lpush(self, key: str, *values: str) -> int | None:
        """Push values onto the head of a list.

        Args:
            key: the list key.
            *values: the values to push.

        Returns:
            int | None: the list length after the push, or None if Redis failed.
        """
        return await _fail_open("LPUSH", self._redis.lpush(key, *values), None)

    async def rpush(self, key: str, *values: str) -> int | None:
        """Push values onto the tail of a list.

        Args:
            key: the list key.
            *values: the values to push.

        Returns:
            int | None: the list length after the push, or None if Redis failed.
        """
        return await _fail_open("RPUSH", self._redis.rpush(key, *values), None)

    async def llen(self, key: str) -> int:
        """Read a list's length.

        Args:
            key: the list key.

        Returns:
            int: the length; 0 if the list is missing or Redis failed.
        """
        return await _fail_open("LLEN", self._redis.llen(key), 0)

    async def blmove(self, first_list: str, second_list: str, timeout: float) -> str | None:
        """Move one item, blocking up to `timeout` seconds.

        Does not fail open, since an outage must be distinguishable from an
        empty queue so the caller can back off.

        Args:
            first_list: source list, popped from the left.
            second_list: destination list, pushed to the right.
            timeout: seconds to block waiting for an item.

        Returns:
            str | None: the moved item, or None if `timeout` elapsed
            with nothing to move.

        Raises:
            redis.exceptions.RedisError: on any Redis-side failure.
        """
        # int annotation on the blmove is not enforced, lib:
        # params = [first_list, second_list, src, dest, timeout]
        # so float timeout reaches the server
        item = await self._redis.blmove(
            first_list,
            second_list,
            timeout,  # pyright: ignore[reportArgumentType]
            "LEFT",
            "RIGHT",
        )
        # decode_responses=True makes this a str; bytes only if that changes.
        return item.decode() if isinstance(item, bytes) else item

    async def lrem(self, key: str, count: int, value: str) -> int:
        """Remove occurrences of a value from a list.

        Args:
            key: the list key.
            count: how many to remove; 0 removes all.
            value: the value to remove.

        Returns:
            int: how many entries were removed; 0 if Redis failed.
        """
        return await _fail_open("LREM", self._redis.lrem(key, count, value), 0)

    async def zadd(self, key: str, mapping: dict[str, float]) -> int | None:
        """Add members to a sorted set.

        Args:
            key: the sorted set key.
            mapping: member to score.

        Returns:
            int | None: how many members were added, or None if Redis failed.
        """
        return await _fail_open("ZADD", self._redis.zadd(key, mapping), None)

    async def zrevrange(self, key: str, start: int, stop: int) -> list[str]:
        """Read sorted-set members from highest score down.

        Args:
            key: the sorted set key.
            start: first rank, inclusive.
            stop: last rank, inclusive; -1 for the end.

        Returns:
            list[str]: the members; empty if Redis failed.
        """
        return await _fail_open("ZREVRANGE", self._redis.zrevrange(key, start, stop), [])

    async def zremrangebyrank(self, key: str, start: int, stop: int) -> int:
        """Remove sorted-set members within a rank range.

        Args:
            key: the sorted set key.
            start: first rank, inclusive.
            stop: last rank, inclusive.

        Returns:
            int: how many members were removed; 0 if Redis failed.
        """
        return await _fail_open("ZREMRANGEBYRANK", self._redis.zremrangebyrank(key, start, stop), 0)

    async def zcount(self, key: str, min_: str, max_: str) -> int:
        """Count sorted-set members within a score range.

        Args:
            key: the sorted set key.
            min_: lowest score, as Redis accepts it.
            max_: highest score, as Redis accepts it.

        Returns:
            int: the count; 0 if Redis failed.
        """
        return await _fail_open("ZCOUNT", self._redis.zcount(key, min_, max_), 0)

    async def zscore(self, key: str, member: str) -> float | None:
        """Read a member's score.

        Args:
            key: the sorted set key.
            member: the member.

        Returns:
            float | None: the score, or None if absent or Redis failed.
        """
        return await _fail_open("ZSCORE", self._redis.zscore(key, member), None)

    async def sadd(self, key: str, *members: str) -> int | None:
        """Add members to a set.

        Args:
            key: the set key.
            *members: the members to add.

        Returns:
            int | None: how many were new, or None if Redis failed.
        """
        return await _fail_open("SADD", self._redis.sadd(key, *members), None)

    async def sismember(self, key: str, member: str) -> bool:
        """Tell whether a value is in a set.

        Args:
            key: the set key.
            member: the value to look for.

        Returns:
            bool: True if it is a member; False if not or Redis failed.
        """
        result = await _fail_open("SISMEMBER", self._redis.sismember(key, member), 0)
        return bool(result)

    async def smembers(self, key: str) -> set[str]:
        """Read every member of a set.

        Args:
            key: the set key.

        Returns:
            set[str]: the members; empty if Redis failed.
        """
        return await _fail_open("SMEMBERS", self._redis.smembers(key), set())

    async def hset(self, key: str, field: str, value: str) -> int | None:
        """Set one field of a hash.

        Args:
            key: the hash key.
            field: the field name.
            value: the value to store.

        Returns:
            int | None: 1 if the field is new, 0 if it was updated, None if Redis failed.
        """
        return await _fail_open("HSET", self._redis.hset(key, field, value), None)

    async def hget(self, key: str, field: str) -> str | None:
        """Read one field of a hash.

        Args:
            key: the hash key.
            field: the field name.

        Returns:
            str | None: the value, or None if absent or Redis failed.
        """
        return await _fail_open("HGET", self._redis.hget(key, field), None)

    async def delete_if_equals(self, key: str, value: str) -> bool:
        """Delete `key` only if its current value is `value` (compare-and-delete).

        Args:
            key: key to delete.
            value: expected current value; a token held by the caller.

        Returns:
            bool: True if the key was deleted, False if it had moved on
            (already expired and re-taken by someone else) or Redis failed.
        """
        result = await _fail_open(
            "DELETE_IF_EQUALS", self._redis.eval(_DELETE_IF_EQUALS_SCRIPT, 1, key, value), 0
        )
        return bool(result)

    async def zcount_keys(self, specs: list[tuple[str, str, str]]) -> list[int]:
        """Run ZCOUNT over many (key, min, max) specs in one pipelined round trip.

        Args:
            specs: (key, min, max) triples.

        Returns:
            list[int]: one count per spec, in order; all 0 if Redis failed.
        """
        if not specs:
            return []

        async def run() -> list[int]:
            async with self._redis.pipeline(transaction=False) as pipe:
                for key, lo, hi in specs:
                    pipe.zcount(key, lo, hi)
                return [int(n) for n in await pipe.execute()]

        return await _fail_open("ZCOUNT_MANY", run(), [0] * len(specs))

    async def ltrim(self, key: str, start: int, stop: int) -> bool:
        """Trim a list to a range.

        Args:
            key: the list key.
            start: first index to keep.
            stop: last index to keep, inclusive.

        Returns:
            bool: True if the trim ran; False if Redis failed.
        """
        result = await _fail_open("LTRIM", self._redis.ltrim(key, start, stop), None)
        return bool(result)

    async def lrange(self, key: str, start: int, stop: int) -> list[str]:
        """Read a range of a list.

        Args:
            key: the list key.
            start: first index.
            stop: last index, inclusive; -1 for the end.

        Returns:
            list[str]: the entries; empty if Redis failed.
        """
        return await _fail_open("LRANGE", self._redis.lrange(key, start, stop), [])

    async def ttl(self, key: str) -> int:
        """Read a key's remaining time to live.

        Args:
            key: the Redis key.

        Returns:
            int: seconds left, -1 without an expiry, -2 if the key is missing or Redis failed.
        """
        return await _fail_open("TTL", self._redis.ttl(key), -2)

    async def ping(self) -> bool:
        """Check that Redis answers.

        Returns:
            bool: True if it answered; False if Redis failed.
        """
        result = await _fail_open("PING", self._redis.ping(), False)
        return bool(result)

    async def aclose(self) -> None:
        """Close the connection; a Redis error on close is logged, not raised."""
        try:
            await self._redis.aclose()
        except RedisError as exc:
            logger.warning("redis close failed: %s", exc.__class__.__name__)
