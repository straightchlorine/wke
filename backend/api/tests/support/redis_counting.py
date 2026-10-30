"""A Redis wrapper that counts commands, for cache and fan-out tests."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import FastAPI

    from wke.clients.redis import RedisClient


class CountingRedis:
    """Proxy over RedisClient that counts every awaited command."""

    def __init__(self, inner: RedisClient) -> None:
        self._inner = inner
        self.calls: list[str] = []

    def __getattr__(self, name: str) -> Any:
        target = getattr(self._inner, name)
        if not callable(target):
            return target

        async def counted(*args: Any, **kwargs: Any) -> Any:
            self.calls.append(name)
            return await getattr(self._inner, name)(*args, **kwargs)

        return counted


def count_redis(app: FastAPI) -> CountingRedis:
    """Wrap the app service's Redis client in a CountingRedis and return the wrapper."""
    service = app.state.service
    counter = CountingRedis(service._redis)
    service._redis = counter
    return counter
