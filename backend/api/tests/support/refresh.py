"""Stored dossiers, edits and a fake clock for the refresh job tests."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

from fakeredis.aioredis import FakeRedis

from tests.factories.dossier import make_fixture_dossier
from tests.support.constants import PIPELINE_VERSION
from tests.support.services import renamed, seed_dossier
from wke.clients.redis import RedisClient
from wke.core import keys
from wke.core.citations import seed_pin
from wke.core.models import Dossier
from wke.jobs.build.rating import rating_key

DAY = 24 * 60 * 60


async def store(
    redis_client: RedisClient,
    fake_redis: FakeRedis,
    page_id: int,
    expires_in: float | None,
    *,
    pipeline_version: str = PIPELINE_VERSION,
    analysis: str = "ml",
    rating: bool = False,
) -> Dossier:
    """Store a dossier of the fixture article under another page id, with a lifetime.

    Args:
        redis_client: the RedisClient to write through.
        fake_redis: the fakeredis behind it, for the expiry.
        page_id: the page id of the stored copy.
        expires_in: seconds until the dossier key expires; None for no expiry.
        pipeline_version: the version in the dossier key and the pointer.
        analysis: the stored build.analysis.
        rating: also store a rating document with the same lifetime.

    Returns:
        Dossier: the stored dossier.
    """
    dossier = renamed(make_fixture_dossier(), page_id, f"Page {page_id}")
    build = dossier.build.model_copy(update={"analysis": analysis})
    dossier = dossier.model_copy(update={"build": build})
    await seed_dossier(redis_client, dossier, pipeline_version)
    rev_id = seed_pin(dossier).rev_id
    if expires_in is not None:
        await fake_redis.pexpire(
            keys.dossier(page_id, rev_id, pipeline_version), int(expires_in * 1000)
        )
    if rating:
        await redis_client.set(
            rating_key(page_id, rev_id, pipeline_version),
            "{}",
            ex=None if expires_in is None else int(expires_in) + 1,
        )
    return dossier


async def make_stale(redis_client: RedisClient, dossier: Dossier) -> None:
    """Record a newer revision, edited long enough ago for a rebuild to be allowed.

    Args:
        redis_client: the RedisClient to write through.
        dossier: a stored dossier built long ago.
    """
    page_id = dossier.topic.page_id
    newer = seed_pin(dossier).rev_id + 1
    edited = datetime.now(UTC) - timedelta(hours=1)
    await redis_client.set(keys.latest_rev(page_id), str(newer))
    await redis_client.zadd(keys.pageedits(page_id), {str(newer): edited.timestamp()})


class FakeTime:
    """A clock and a sleep that move together, so a test never waits."""

    def __init__(self) -> None:
        self.now = time.monotonic()
        self.sleeps: list[float] = []

    def clock(self) -> float:
        """Read the fake time."""
        return self.now

    async def sleep(self, seconds: float) -> None:
        """Move the fake time on and note the wait."""
        self.sleeps.append(seconds)
        self.now += seconds
