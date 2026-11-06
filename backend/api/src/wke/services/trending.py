"""The cached trending snapshot."""

from __future__ import annotations

from datetime import UTC, datetime

from wke.core import keys
from wke.core.errors import ApiException
from wke.core.models import TrendingSnapshot
from wke.core.viewcache import current_generation
from wke.services.base import ServiceBase


class TrendingMixin(ServiceBase):
    """The cached trending snapshot."""

    async def get_trending(self, limit: int) -> TrendingSnapshot:
        """Read the latest trending snapshot.

        The assembled view is cached in-process for 10 s per `limit`. A build
        finishing in this process (dev stack) drops it early; in k8s the
        worker is a separate pod, so the TTL is the real staleness bound.

        Args:
            limit: max topics to return (the snapshot itself caps at 40).

        Returns:
            TrendingSnapshot: `trending:latest`, topics truncated to
            limit, each topic's dossier_state recomputed live against
            `ptr:{page_id}` rather than trusting the stored snapshot's
            (possibly stale) value, only the edges whose two ends are
            both among the returned topics, and edits_last_hour recomputed live
            against `pageedits:{page_id}` rather than the all-time count
            frozen at the nightly snapshot (the Home card labels this
            field "edits, last 1 h").

        Raises:
            ApiException: 503 upstream_unavailable if no snapshot has
                been built yet (cold Redis / wke-trending has not run).
        """
        cached = self._trending_cache.get(limit)
        if cached is not None:
            return cached
        async with self._trending_lock:
            cached = self._trending_cache.get(limit)
            if cached is not None:
                return cached
            generation = current_generation()
            snapshot = await self._assemble_trending(limit)
            self._trending_cache.put(limit, snapshot, generation)
            return snapshot

    async def _assemble_trending(self, limit: int) -> TrendingSnapshot:
        """Build the trending view from Redis: one GET, two MGETs, one pipeline.

        Args:
            limit: max topics to return.

        Returns:
            TrendingSnapshot: the view described on `get_trending`.

        Raises:
            ApiException: 503 upstream_unavailable if no snapshot exists.
        """
        raw = await self._redis.get(keys.TRENDING_LATEST)
        if raw is None:
            raise ApiException(
                503,
                "upstream_unavailable",
                detail="No most-read snapshot yet. The nightly job has not run.",
                retry_after=60,
            )
        snapshot = TrendingSnapshot.model_validate_json(raw)
        now = datetime.now(UTC).timestamp()
        picked = snapshot.topics[: max(limit, 0)]
        states = await self._dossier_states([topic.page_id for topic in picked])
        edit_counts = await self._redis.zcount_keys(
            [(keys.pageedits(topic.page_id), str(now - 3600), "+inf") for topic in picked]
        )
        topics = [
            topic.model_copy(update={"dossier_state": state, "edits_last_hour": edits})
            for topic, state, edits in zip(picked, states, edit_counts, strict=True)
        ]
        kept = {topic.page_id for topic in topics}
        edges = [edge for edge in snapshot.edges if edge.source in kept and edge.target in kept]
        return snapshot.model_copy(update={"topics": topics, "edges": edges})
