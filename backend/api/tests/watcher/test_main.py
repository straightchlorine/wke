"""The watcher entrypoint serves Prometheus metrics before it starts consuming."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from wke.watcher import __main__ as entrypoint


async def test_run_binds_the_configured_metrics_port_before_the_watcher_starts() -> None:
    order: list[str] = []

    def record_port(port: int) -> None:
        order.append(f"metrics:{port}")

    with (
        patch.object(entrypoint.settings, "watcher_metrics_port", 8012),
        patch.object(entrypoint, "start_http_server", side_effect=record_port),
        patch.object(entrypoint, "default_redis_factory"),
        patch.object(entrypoint, "RedisClient"),
        patch.object(entrypoint, "configure_logging"),
        patch.object(entrypoint, "Watcher") as watcher_cls,
    ):
        watcher_cls.return_value.run_forever = AsyncMock(side_effect=lambda: order.append("run"))
        await entrypoint.run_watcher()
    assert order == ["metrics:8012", "run"]


def test_main_runs_the_watcher_loop_and_returns_none() -> None:
    with patch.object(entrypoint, "run_watcher", new=AsyncMock()) as run_watcher:
        assert entrypoint.main() is None
    run_watcher.assert_awaited_once_with()
