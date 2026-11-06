"""The trending view is computed once for both the REST route and the MCP tool."""

from __future__ import annotations

import json

from tests.support.apps import app_client
from tests.support.redis_counting import count_redis
from tests.support.snapshots import make_snapshot
from wke.core import keys
from wke.core.viewcache import invalidate_views


async def test_service_get_trending_is_shared_by_route_and_mcp(app, fake_redis) -> None:
    await fake_redis.set(
        keys.TRENDING_LATEST, json.dumps(make_snapshot(page_id=999, views=1, rev_id=1))
    )

    async with app_client(app):
        service = app.state.service
        counter = count_redis(app)
        first = await service.get_trending(10)
        second = await service.get_trending(10)
        assert second is first
        warm_calls = len(counter.calls)
        invalidate_views()
        third = await service.get_trending(10)

    assert third is not first
    assert len(counter.calls) == 2 * warm_calls
