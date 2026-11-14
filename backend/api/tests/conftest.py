"""Shared test fixtures: no network, deterministic fakeredis, fixed settings."""

from __future__ import annotations

import asyncio
import os
import socket
from typing import TYPE_CHECKING, Any

import fakeredis.aioredis
import httpx
import pytest

from tests.support.constants import REQUIRED_ENV

if TYPE_CHECKING:
    from fastapi import FastAPI

    from tests.support.wikimedia import WmFixtures
    from wke.clients.ml import MLClient
    from wke.clients.wikimedia import WikimediaClient

# wke.settings builds a Settings() at import, testing needs these - setting them first.
for _key, _value in REQUIRED_ENV.items():
    os.environ.setdefault(_key, _value)

from wke.settings import Settings  # noqa: E402
from wke.settings import settings as shared_settings  # noqa: E402

# Tests never read the developer .env.
# The shared instance is built at import, before the file could be switched off:
# copy fresh values into it so every module importing it sees the same values.
Settings.model_config["env_file"] = None
_fresh = Settings.model_validate({})
for _name in Settings.model_fields:
    setattr(shared_settings, _name, getattr(_fresh, _name))


_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}
_REAL_CONNECT = socket.socket.connect


def _guarded_connect(self: socket.socket, address: Any, *args: Any, **kwargs: Any) -> Any:
    host = address[0] if isinstance(address, tuple) else address
    if host not in _LOOPBACK_HOSTS:
        raise RuntimeError(
            f"Network access blocked in tests: attempted connect to {address!r}. "
            "Use httpx.MockTransport or fakeredis instead."
        )
    return _REAL_CONNECT(self, address, *args, **kwargs)


@pytest.fixture(autouse=True)
def _hermetic_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep CORS_ORIGINS and PUBLIC_SCHEME from the shell out of Settings."""
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    monkeypatch.delenv("PUBLIC_SCHEME", raising=False)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Block any socket connect that is not to loopback."""
    monkeypatch.setattr(socket.socket, "connect", _guarded_connect)


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """A fresh Settings instance with every required env var set."""
    for key, value in REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)
    return Settings.model_validate({})


class _NetworkedFakeRedis(fakeredis.aioredis.FakeRedis):
    """FakeRedis that suspends like a networked Redis.

    fakeredis (redis-py 8) completes without yielding:
        concurrent coroutines never interleave and the event loop is starved.

    To avoid that ensuring that each command yields once.
    """

    async def execute_command(self, *args, **options):
        await asyncio.sleep(0)
        return await super().execute_command(*args, **options)

    async def blmove(self, first_list, second_list, timeout, *args, **kwargs):
        item = await super().blmove(first_list, second_list, timeout, *args, **kwargs)
        if item is None:
            await asyncio.sleep(timeout)
        return item


@pytest.fixture
async def fake_redis():
    """A fresh networked-like FakeRedis instance, closed after the test."""
    redis = _NetworkedFakeRedis(decode_responses=True)
    yield redis
    await redis.aclose()


@pytest.fixture
async def redis_client(fake_redis):
    """A wke.clients.redis.RedisClient wrapping the fakeredis fixture."""
    from wke.clients.redis import RedisClient

    return RedisClient(fake_redis)


@pytest.fixture
def wm_fixtures() -> WmFixtures:
    """Loader for the recorded article fixtures in tests/fixtures/wm/."""
    from tests.support.constants import FIXTURES_DIR
    from tests.support.wikimedia import WmFixtures

    return WmFixtures(FIXTURES_DIR)


@pytest.fixture
def wikimedia_client(redis_client, wm_fixtures) -> WikimediaClient:
    """A WikimediaClient resolving the recorded article, a missing title, and a disambiguation."""
    from tests.support.wikimedia import make_wikimedia_client, wikimedia_handler

    return make_wikimedia_client(redis_client, wikimedia_handler(wm_fixtures))


@pytest.fixture
def ml_client_ok() -> MLClient:
    """An MLClient whose wke-ml answers analyze and summarize with canned bodies."""
    from tests.support.ml_payloads import analyze_response_json, summarize_response_json
    from wke.clients.ml import MLClient

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/analyze":
            return httpx.Response(200, json=analyze_response_json())
        if request.url.path == "/v1/summarize":
            return httpx.Response(200, json=summarize_response_json())
        return httpx.Response(404)

    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handle), base_url="http://wke-ml.test"
    )
    return MLClient(http_client)


@pytest.fixture
def app(fake_redis, settings, wikimedia_client, ml_client_ok) -> FastAPI:
    """A create_app() wired to the same fake_redis, Wikimedia mock and ML mock."""
    from tests.support.apps import make_app

    return make_app(
        fake_redis,
        settings,
        wikimedia_http=wikimedia_client._http,
        ml_http=ml_client_ok._http,
    )
