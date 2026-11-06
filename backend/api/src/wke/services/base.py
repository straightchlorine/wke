"""Shared state of the dossier service."""

from __future__ import annotations

import asyncio

from wke.clients.redis import RedisClient
from wke.clients.wikimedia import WikimediaClient
from wke.core import keys
from wke.core.dossiers import pointer_rev_id, state_from_dossier_json
from wke.core.models import DossierListItem, DossierState, TrendingSnapshot
from wke.core.viewcache import ViewCache
from wke.jobs.queue import JobQueue


class ServiceBase:
    """State and dossier-state lookups shared by every service concern."""

    def __init__(
        self,
        redis: RedisClient,
        wikimedia: WikimediaClient,
        job_queue: JobQueue,
        pipeline_version: str,
        public_host: str = "",
        public_scheme: str = "https",
    ) -> None:
        self._redis = redis
        self._wikimedia = wikimedia
        self._job_queue = job_queue
        self._pipeline_version = pipeline_version
        self._public_host = public_host
        self._public_scheme = public_scheme
        self._base_url = f"{public_scheme}://{public_host}" if public_host else ""
        # Holds references to fire-and-forget background rebuild tasks so
        # they cannot be garbage-collected mid-flight (asyncio docs: "Save
        # a reference to the result of create_task").
        self._background_tasks: set[asyncio.Task[None]] = set()
        self._list_cache: ViewCache[list[DossierListItem]] = ViewCache()
        self._list_lock = asyncio.Lock()
        self._trending_cache: ViewCache[TrendingSnapshot] = ViewCache()
        self._trending_lock = asyncio.Lock()

    @property
    def base_url(self) -> str:
        """The scheme+host every absolute URL this service emits is rooted at.

        Built once from PUBLIC_SCHEME and PUBLIC_HOST, so `links.self` on a
        dossier view, `/llms.txt` and any other absolute link this service
        or its callers build all agree with each other.

        Returns:
            str: e.g. "https://wke.example.com", or "" if PUBLIC_HOST is unset.
        """
        return self._base_url

    async def _dossier_state(self, page_id: int) -> DossierState:
        """Read one page's dossier state; see `_dossier_states`.

        Args:
            page_id: Wikipedia page id.

        Returns:
            DossierState: the page's state.
        """
        return (await self._dossier_states([page_id]))[0]

    async def _dossier_states(self, page_ids: list[int]) -> list[DossierState]:
        """Read the dossier state of many pages with two MGETs.

        The state is read for this service's pipeline version, the one
        `get_dossier_view` serves, so a state of "ready" always means the
        dossier can be opened. Job state is not consulted: the result is
        never "building".

        Args:
            page_ids: Wikipedia page ids.

        Returns:
            list[DossierState]: one state per page id, in order.
        """
        ptr_raws = await self._redis.mget([keys.ptr(pid) for pid in page_ids])
        dossier_keys: list[str | None] = []
        for pid, ptr_raw in zip(page_ids, ptr_raws, strict=True):
            rev_id = pointer_rev_id(ptr_raw) if ptr_raw is not None else None
            dossier_keys.append(
                None if rev_id is None else keys.dossier(pid, rev_id, self._pipeline_version)
            )
        fetched = iter(await self._redis.mget([key for key in dossier_keys if key is not None]))
        return [
            state_from_dossier_json(next(fetched) if key is not None else None)
            for key in dossier_keys
        ]
