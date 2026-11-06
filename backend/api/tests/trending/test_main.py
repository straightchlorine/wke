"""The trending entrypoint runs the pipeline once and always closes its clients."""

# pyright: reportPrivateUsage=false
# The entrypoint's `_run` is the unit under test; `main` only wraps it in asyncio.run.
from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wke.trending import __main__ as entrypoint


def _snapshot(*states: str) -> MagicMock:
    snapshot = MagicMock()
    snapshot.date = "2026-09-26"
    snapshot.source = "wikifeeds_mostread"
    snapshot.topics = [MagicMock(dossier_state=state) for state in states]
    return snapshot


async def test_run_logs_the_summary_and_closes_the_clients(
    caplog: pytest.LogCaptureFixture,
) -> None:
    redis = MagicMock(aclose=AsyncMock())
    with (
        patch.object(entrypoint, "default_redis_factory"),
        patch.object(entrypoint, "RedisClient", return_value=redis),
        patch.object(
            entrypoint,
            "run_trending",
            AsyncMock(return_value=_snapshot("ready", "none", "partial")),
        ),
        caplog.at_level(logging.INFO, logger=entrypoint.logger.name),
    ):
        assert await entrypoint._run() == 0

    redis.aclose.assert_awaited_once()
    assert "topics=3 to_build=2" in caplog.text


async def test_run_without_a_snapshot_is_a_successful_no_op() -> None:
    redis = MagicMock(aclose=AsyncMock())
    with (
        patch.object(entrypoint, "default_redis_factory"),
        patch.object(entrypoint, "RedisClient", return_value=redis),
        patch.object(entrypoint, "run_trending", AsyncMock(return_value=None)),
    ):
        assert await entrypoint._run() == 0


async def test_run_closes_the_clients_when_the_pipeline_fails() -> None:
    redis = MagicMock(aclose=AsyncMock())
    with (
        patch.object(entrypoint, "default_redis_factory"),
        patch.object(entrypoint, "RedisClient", return_value=redis),
        patch.object(entrypoint, "run_trending", AsyncMock(side_effect=RuntimeError("boom"))),
        pytest.raises(RuntimeError, match="boom"),
    ):
        await entrypoint._run()

    redis.aclose.assert_awaited_once()
