"""Fixtures for the wke-watcher test suite: the recorded SSE fixture."""

from __future__ import annotations

from pathlib import Path

import pytest

SSE_FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "wm" / "recentchange.sse"


@pytest.fixture
def sse_bytes() -> bytes:
    """Raw bytes of the recorded 200-event recentchange.sse fixture."""
    return SSE_FIXTURE_PATH.read_bytes()
