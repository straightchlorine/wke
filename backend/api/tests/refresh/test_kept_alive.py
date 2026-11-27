"""A dossier the job kept alive is still read and still listed after its old expiry."""

from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET

import pytest
from fakeredis.aioredis import FakeRedis

from tests.support.constants import PIPELINE_VERSION
from tests.support.refresh import FakeTime, make_stale, store
from tests.support.services import make_service
from wke.api.sitemap import render_sitemap
from wke.clients.redis import RedisClient
from wke.core import keys
from wke.core.viewcache import invalidate_views
from wke.jobs.queue import JobQueue
from wke.refresh import run as refresh
from wke.refresh.run import run_refresh

NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}


async def _refresh(fake_redis: FakeRedis, redis_client: RedisClient, limit_to_zero: bool) -> None:
    fake_time = FakeTime()
    with pytest.MonkeyPatch.context() as patch:
        if limit_to_zero:
            patch.setattr(refresh, "MAX_REBUILDS_PER_RUN", 0)
        await run_refresh(
            fake_redis,
            redis_client,
            JobQueue(redis_client, PIPELINE_VERSION, 20),
            PIPELINE_VERSION,
            sleep=fake_time.sleep,
            clock=fake_time.clock,
        )


async def _locs(redis_client: RedisClient, host: str) -> list[str]:
    service = make_service(redis_client, public_host=host)
    invalidate_views()
    sitemap = ET.fromstring(await render_sitemap(service))
    return [e.text or "" for e in sitemap.findall("s:url/s:loc", NS)]


async def test_a_dossier_that_was_extended_is_still_served_and_listed_after_its_old_expiry(
    fake_redis: FakeRedis, redis_client: RedisClient
) -> None:
    kept = await store(redis_client, fake_redis, 71, 0.6)
    await _refresh(fake_redis, redis_client, limit_to_zero=False)
    # The control has the same short lifetime and was never refreshed.
    await store(redis_client, fake_redis, 72, 0.6)

    await asyncio.sleep(0.8)

    service = make_service(redis_client, public_host="kept-alive.example.test")
    view = await service.get_dossier_view(71, 8000, "json", False)
    locs = await _locs(redis_client, "kept-alive.example.test")
    assert view.topic.title == kept.topic.title
    assert any(loc.endswith("/t/Page_71") for loc in locs)
    assert not any(loc.endswith("/t/Page_72") for loc in locs)


@pytest.mark.parametrize(
    ("limit_to_zero", "debounced", "host"),
    [
        (False, True, "refused.example.test"),
        (True, False, "deferred.example.test"),
    ],
    ids=["rebuild refused", "rebuild deferred by the limit"],
)
async def test_a_stale_dossier_without_a_rebuild_is_still_served_and_listed_after_its_old_expiry(
    fake_redis: FakeRedis,
    redis_client: RedisClient,
    limit_to_zero: bool,
    debounced: bool,
    host: str,
) -> None:
    stale = await store(redis_client, fake_redis, 81, 0.6)
    await make_stale(redis_client, stale)
    if debounced:
        await redis_client.set(keys.rebuild_debounce(81), "1", ex=600)

    await _refresh(fake_redis, redis_client, limit_to_zero)
    await asyncio.sleep(0.8)

    view = await make_service(redis_client, public_host=host).get_dossier_view(
        81, 8000, "json", False
    )
    locs = await _locs(redis_client, host)
    assert view.topic.title == stale.topic.title
    assert any(loc.endswith("/t/Page_81") for loc in locs)
    assert await redis_client.llen(keys.QUEUE_BACKGROUND) == 0
