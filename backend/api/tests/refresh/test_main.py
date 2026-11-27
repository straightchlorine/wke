"""The refresh entrypoint: the summary line, the exit code and the closed client."""

from __future__ import annotations

# pyright: reportPrivateUsage=false
# The entrypoint's `_run` is the unit under test; `main` only wraps it in asyncio.run.
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from wke.refresh import __main__ as entrypoint
from wke.refresh.run import RefreshSummary


async def test_run_logs_the_counts_and_exits_zero_even_with_deferred_rebuilds(
    caplog: pytest.LogCaptureFixture,
) -> None:
    redis = MagicMock(aclose=AsyncMock())
    summary = RefreshSummary(
        stored=9, stale=4, admitted=2, refused=1, deferred=1, extended=3, left_alone=2, skipped=1
    )
    with (
        patch.object(entrypoint, "default_redis_factory"),
        patch.object(entrypoint, "RedisClient", return_value=redis),
        patch.object(entrypoint, "run_refresh", AsyncMock(return_value=summary)),
        caplog.at_level(logging.INFO, logger=entrypoint.logger.name),
    ):
        assert await entrypoint._run() == 0

    redis.aclose.assert_awaited_once()
    assert (
        "stored=9 stale=4 admitted=2 refused=1 deferred=1 extended=3 left_alone=2 skipped=1"
        in caplog.text
    )
    assert "duration_s=" in caplog.text


async def test_a_redis_failure_is_an_error_exit_and_the_client_is_closed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    redis = MagicMock(aclose=AsyncMock())
    with (
        patch.object(entrypoint, "default_redis_factory"),
        patch.object(entrypoint, "RedisClient", return_value=redis),
        patch.object(
            entrypoint, "run_refresh", AsyncMock(side_effect=RedisConnectionError("down"))
        ),
        caplog.at_level(logging.ERROR, logger=entrypoint.logger.name),
    ):
        assert await entrypoint._run() == 1

    redis.aclose.assert_awaited_once()
    assert "redis failed" in caplog.text
