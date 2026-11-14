"""The in-process cache of /llms.txt and /sitemap.xml: reused, dropped by a build or by time."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from types import ModuleType
from unittest.mock import AsyncMock

import pytest

from tests.support.snapshots import make_snapshot
from wke.api import llmstxt, sitemap
from wke.core.models import TrendingSnapshot
from wke.core.viewcache import invalidate_views
from wke.services.dossiers import DossierService

Renderer = Callable[[DossierService], Awaitable[str]]


def _service(base_url: str) -> AsyncMock:
    service = AsyncMock(spec=DossierService)
    service.base_url = base_url
    service.get_trending.return_value = TrendingSnapshot.model_validate(make_snapshot())
    service.list_dossiers.return_value = ([], None)
    return service


@pytest.mark.parametrize(
    ("renderer", "source_call", "module"),
    [
        pytest.param(llmstxt.render_llms_txt, "get_trending", llmstxt, id="llms"),
        pytest.param(sitemap.render_sitemap, "list_dossiers", sitemap, id="sitemap"),
    ],
)
async def test_body_is_reused_until_a_build_or_the_ttl_drops_it(
    monkeypatch: pytest.MonkeyPatch,
    renderer: Renderer,
    source_call: str,
    module: ModuleType,
) -> None:
    clock = [1000.0]
    monkeypatch.setattr(f"{module.__name__}.time.monotonic", lambda: clock[0])
    service = _service(f"https://cache-{source_call}.example.test")
    source = getattr(service, source_call)

    first = await renderer(service)
    clock[0] += 299
    again = await renderer(service)
    assert again == first
    assert source.await_count == 1

    invalidate_views()
    await renderer(service)
    assert source.await_count == 2

    clock[0] += 300
    await renderer(service)
    assert source.await_count == 3
