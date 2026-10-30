"""The guards in tests/conftest.py hold: no network, no developer .env."""

from __future__ import annotations

import socket

import pytest


def test_connect_to_non_loopback_raises() -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(RuntimeError, match="Network access blocked in tests"):
            sock.connect(("93.184.216.34", 80))
    finally:
        sock.close()


def test_connect_to_loopback_is_not_blocked_by_the_guard() -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(OSError) as excinfo:
            sock.connect(("127.0.0.1", 1))
    finally:
        sock.close()

    assert "Network access blocked" not in str(excinfo.value)


def test_shared_settings_ignore_the_developer_env_file() -> None:
    """The import-time `wke.settings.settings` reads no backend/api/.env under pytest."""
    from wke.settings import settings as shared

    assert shared.public_scheme == "https"
    assert shared.watcher_metrics_port == 8000
