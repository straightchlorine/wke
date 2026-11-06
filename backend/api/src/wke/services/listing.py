"""The catalog of stored dossiers."""

from __future__ import annotations

import logging

from pydantic import ValidationError

from wke.core import keys, pack
from wke.core.citations import seed_pin
from wke.core.dossiers import pointer_rev_id
from wke.core.models import Dossier, DossierListItem
from wke.core.models.budgets import BUDGETS, BudgetTokens
from wke.core.viewcache import current_generation
from wke.services import freshness as freshness_mod
from wke.services.base import ServiceBase

logger = logging.getLogger(__name__)

LIST_DOSSIERS_SCAN_CAP = 500


class ListingMixin(ServiceBase):
    """The catalog of stored dossiers."""

    async def list_dossiers(
        self, q: str | None, limit: int, cursor: str | None
    ) -> tuple[list[DossierListItem], str | None]:
        """List built dossiers newest-first for the Dossiers page.

        The scan behind it is cached in-process for 10 s. A build finishing
        or a refresh starting in this process (dev stack, where the worker
        shares the process) drops the cache early; in k8s the api pods and
        the worker are separate processes, so the TTL is the real bound on
        how stale a list can be.

        Args:
            q: case-insensitive substring of the title, or None.
            limit: max items to return, 1-100.
            cursor: `next_cursor` from a previous call, or None for the
                first page. Anything but a non-negative integer starts at
                the first page.

        Returns:
            tuple[list[DossierListItem], str | None]: one page of items
            plus the cursor for the next page, or None if this is the
            last page.
        """
        try:
            offset = max(int(cursor), 0) if cursor else 0
        except ValueError:
            offset = 0

        all_items = await self._list_all_items()
        query = q.lower() if q else None
        items = (
            all_items
            if query is None
            else [item for item in all_items if query in item.title.lower()]
        )
        page = items[offset : offset + limit]
        next_cursor = str(offset + limit) if offset + limit < len(items) else None
        return page, next_cursor

    async def _list_all_items(self) -> list[DossierListItem]:
        """Compute (or reuse) the newest-first rows for every built dossier.

        Cached for 10 s as one entry; `q` filtering and paging are cheap
        in-memory slices of it, so every (q, limit, cursor) combination
        shares one Redis scan. Concurrent misses share one computation.

        Returns:
            list[DossierListItem]: up to LIST_DOSSIERS_SCAN_CAP rows, newest first.
        """
        cached = self._list_cache.get("all")
        if cached is not None:
            return cached
        async with self._list_lock:
            cached = self._list_cache.get("all")
            if cached is not None:
                return cached
            generation = current_generation()
            page_ids = await self._redis.zrevrange(keys.BUILT, 0, LIST_DOSSIERS_SCAN_CAP - 1)
            items: list[DossierListItem] = []
            for raw_page_id in page_ids:
                item = await self._dossier_list_item(int(raw_page_id))
                if item is not None:
                    items.append(item)
            self._list_cache.put("all", items, generation)
            return items

    async def _dossier_list_item(self, page_id: int) -> DossierListItem | None:
        """Build one row for `list_dossiers` from a page's latest build.

        Args:
            page_id: Wikipedia page id from the `built` ZSET.

        Returns:
            DossierListItem | None: None if the pointer or dossier is
            missing (evicted or never finished writing) or unreadable.
        """
        ptr_raw = await self._redis.get(keys.ptr(page_id))
        rev_id = pointer_rev_id(ptr_raw) if ptr_raw is not None else None
        if rev_id is None:
            return None
        dossier_raw = await self._redis.get(keys.dossier(page_id, rev_id, self._pipeline_version))
        if dossier_raw is None:
            return None
        try:
            dossier = Dossier.model_validate_json(dossier_raw)
        except ValidationError:
            logger.warning("unreadable dossier for page %s left out of the list", page_id)
            return None

        # The smallest budget whose pack holds every section; the largest
        # budget when none does.
        largest_budget_filled: BudgetTokens = 32000
        for candidate in BUDGETS:
            if pack.pack(dossier, candidate).budget.complete:
                largest_budget_filled = candidate
                break

        fresh = await freshness_mod.compute_freshness(
            self._redis, page_id, rev_id, dossier.build.built_at
        )
        edits_since_pin = (
            fresh.edits_since
            if fresh.edits_since is not None
            else await freshness_mod.count_edits_since(self._redis, page_id, dossier.build.built_at)
        )
        pin = seed_pin(dossier)
        return DossierListItem(
            page_id=page_id,
            title=dossier.topic.title,
            rev_id=rev_id,
            pinned_at=pin.rev_timestamp,
            freshness_state=fresh.state,
            edits_since_pin=edits_since_pin,
            largest_budget_filled=largest_budget_filled,
            sections=len(dossier.sections),
            built_at=dossier.build.built_at,
        )
