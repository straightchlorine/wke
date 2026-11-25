"""run_build queues the rating stage of the dossier it stored, only while SELECTION_RATING is on."""

from __future__ import annotations

from typing import Any

import pytest

from tests.support.builds import build_only, stored_dossier
from tests.support.constants import FIXTURE_PAGE_ID, FIXTURE_REV_ID, PIPELINE_VERSION
from tests.support.jobs import make_job
from tests.support.ml_clients import analyze_down_client
from wke.clients.ml import MLClient
from wke.clients.redis import RedisClient
from wke.clients.wikimedia import WikimediaClient
from wke.core import keys
from wke.jobs.build.rating import RatingConfig, rating_lock_key

ON = RatingConfig(enabled=True, deadline_seconds=1800)
ITEM = f"{FIXTURE_PAGE_ID}:{FIXTURE_REV_ID}"


async def _rating_keys(fake_redis: Any) -> list[str]:
    return sorted(
        [k async for k in fake_redis.scan_iter("rat*")]
        + [k async for k in fake_redis.scan_iter("rate:*")]
    )


async def test_an_ml_build_queues_the_stored_dossier_for_rating(
    redis_client: RedisClient, wikimedia_client: WikimediaClient, ml_client_ok: MLClient
) -> None:
    job = make_job()

    await build_only(redis_client, wikimedia_client, ml_client_ok, job, rating=ON)

    assert await redis_client.lrange(keys.QUEUE_RATE, 0, -1) == [ITEM]
    assert (await stored_dossier(redis_client, job)).build.analysis == "ml"
    lock = rating_lock_key(FIXTURE_PAGE_ID, FIXTURE_REV_ID, PIPELINE_VERSION)
    assert 2300 < await redis_client.ttl(lock) <= 2400


async def test_a_structural_build_is_queued_too(
    redis_client: RedisClient, wikimedia_client: WikimediaClient
) -> None:
    job = make_job()

    await build_only(redis_client, wikimedia_client, analyze_down_client(), job, rating=ON)

    assert (await stored_dossier(redis_client, job)).build.analysis == "structural"
    assert await redis_client.lrange(keys.QUEUE_RATE, 0, -1) == [ITEM]


@pytest.mark.parametrize("ml_up", [True, False])
async def test_with_the_switch_off_nothing_is_queued_locked_or_stored(
    redis_client: RedisClient,
    fake_redis: Any,
    wikimedia_client: WikimediaClient,
    ml_client_ok: MLClient,
    ml_up: bool,
) -> None:
    ml = ml_client_ok if ml_up else analyze_down_client()

    await build_only(redis_client, wikimedia_client, ml, make_job())

    assert await redis_client.llen(keys.QUEUE_RATE) == 0
    assert await _rating_keys(fake_redis) == []


async def test_a_rebuild_of_a_rated_revision_queues_nothing_more(
    redis_client: RedisClient, wikimedia_client: WikimediaClient, ml_client_ok: MLClient
) -> None:
    await build_only(redis_client, wikimedia_client, ml_client_ok, make_job(), rating=ON)
    await redis_client.delete(keys.QUEUE_RATE)

    await build_only(redis_client, wikimedia_client, ml_client_ok, make_job(), rating=ON)

    # The first build's rating lock for this revision is still held, so nothing is queued.
    assert await redis_client.llen(keys.QUEUE_RATE) == 0


async def test_a_failure_to_queue_does_not_fail_the_stored_build(
    redis_client: RedisClient,
    wikimedia_client: WikimediaClient,
    ml_client_ok: MLClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def boom(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(redis_client, "rpush", _only_for_rating(redis_client.rpush, boom))
    job = make_job()

    queue = await build_only(redis_client, wikimedia_client, ml_client_ok, job, rating=ON)

    assert (await queue.get_job(job.id)).status != "failed"  # type: ignore[union-attr]
    assert (await stored_dossier(redis_client, job)).build.state == "partial"


def _only_for_rating(real: Any, failing: Any) -> Any:
    async def rpush(key: str, *values: str) -> Any:
        if key == keys.QUEUE_RATE:
            return await failing()
        return await real(key, *values)

    return rpush
