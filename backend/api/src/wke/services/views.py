"""Packed dossier views with freshness and background rebuilds."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from datetime import datetime
from typing import Any, Literal, overload

from wke.core import keys, render
from wke.core.citations import seed_pin
from wke.core.dossiers import pointer_rev_id
from wke.core.errors import ApiException
from wke.core.models import Dossier, DossierLinks, DossierView
from wke.core.models.budgets import BudgetTokens
from wke.core.render.parts import ALL_PARTS_ORDER, DEFAULT_PARTS, Part
from wke.metrics import CACHE_REQUESTS_TOTAL
from wke.services import freshness as freshness_mod
from wke.services.base import ServiceBase

logger = logging.getLogger(__name__)


def _parts_value(parts: frozenset[Part]) -> str:
    """Write a selection as the comma list the `parts` parameter takes.

    Args:
        parts: the selected parts.

    Returns:
        str: the parts in fixed order, such as "dossier,sources".
    """
    return ",".join(part for part in ALL_PARTS_ORDER if part in parts)


def _not_built(page_id: int) -> ApiException:
    """Build the 404 for a page with no stored dossier.

    Args:
        page_id: Wikipedia page id.

    Returns:
        ApiException: 404 not_built.
    """
    return ApiException(404, "not_built", detail=f"No dossier built for page {page_id}.")


class ViewsMixin(ServiceBase):
    """Packed dossier views with freshness and background rebuilds."""

    @overload
    async def get_dossier_view(
        self,
        page_id: int,
        budget: BudgetTokens,
        fmt: Literal["json"],
        summaries: bool,
        rev_id: int | None = None,
        links: bool = False,
        parts: frozenset[Part] = DEFAULT_PARTS,
    ) -> DossierView: ...

    @overload
    async def get_dossier_view(
        self,
        page_id: int,
        budget: BudgetTokens,
        fmt: Literal["markdown"],
        summaries: bool,
        rev_id: int | None = None,
        links: bool = False,
        parts: frozenset[Part] = DEFAULT_PARTS,
    ) -> str: ...

    @overload
    async def get_dossier_view(
        self,
        page_id: int,
        budget: BudgetTokens,
        fmt: Literal["json", "markdown"],
        summaries: bool,
        rev_id: int | None = None,
        links: bool = False,
        parts: frozenset[Part] = DEFAULT_PARTS,
    ) -> DossierView | str: ...

    async def get_dossier_view(
        self,
        page_id: int,
        budget: BudgetTokens,
        fmt: Literal["json", "markdown"],
        summaries: bool,
        rev_id: int | None = None,
        links: bool = False,
        parts: frozenset[Part] = DEFAULT_PARTS,
    ) -> DossierView | str:
        """Pack a built dossier for page_id to a token budget.

        Args:
            page_id: Wikipedia page id.
            budget: one of 2000, 8000, 32000.
            fmt: "json" to return a DossierView, "markdown" to return
                the rendered Markdown string.
            summaries: whether to pack section summaries.
            rev_id: pin to this exact revision (the immutable
                `/rev/{rev_id}` route); None reads the latest build via
                `ptr:{page_id}` and, if stale, fires a background
                rebuild without blocking this read.
            links: for "markdown", write the passages' wiki links as inline
                Markdown links; they are not charged to the budget.
            parts: the selected response parts; they decide the Markdown
                blocks and are carried in the view's self and markdown links
                when they differ from the default. The packed passages never
                depend on them.

        Returns:
            DossierView | str: the packed view, or its Markdown
            rendering when fmt is "markdown".

        Raises:
            ApiException: 404 not_built if no dossier is stored for
                page_id (or for that exact rev_id).
        """
        resolved_rev_id = rev_id
        if resolved_rev_id is None:
            ptr_raw = await self._redis.get(keys.ptr(page_id))
            resolved_rev_id = pointer_rev_id(ptr_raw) if ptr_raw is not None else None
            if resolved_rev_id is None:
                raise _not_built(page_id)

        dossier_key = keys.dossier(page_id, resolved_rev_id, self._pipeline_version)
        dossier_raw = await self._redis.get(dossier_key)
        if dossier_raw is None:
            CACHE_REQUESTS_TOTAL.labels(kind="dossier", result="miss").inc()
            raise _not_built(page_id)
        CACHE_REQUESTS_TOTAL.labels(kind="dossier", result="hit").inc()
        dossier = Dossier.model_validate_json(dossier_raw)

        fresh = await freshness_mod.compute_freshness(
            self._redis, page_id, resolved_rev_id, dossier.build.built_at
        )
        if rev_id is None and fresh.state == "stale":
            self._spawn_background(
                self._maybe_rebuild(page_id, dossier.topic.title, dossier.build.built_at)
            )

        view_links = self._dossier_links(dossier, page_id, resolved_rev_id, budget, fmt, parts)
        view = render.build_view(dossier, budget, fresh, view_links, include_summaries=summaries)
        if fmt == "markdown":
            return render.render_markdown(view, summaries, links, parts)
        return view

    def _spawn_background(self, coro: Coroutine[Any, Any, None]) -> None:
        """Fire a background task and keep a reference until it finishes.

        Args:
            coro: the coroutine to run as a background task.
        """
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _maybe_rebuild(self, page_id: int, title: str, built_at: datetime) -> None:
        """Fire-and-forget wrapper around `maybe_enqueue_rebuild`.

        Args:
            page_id: Wikipedia page id.
            title: article title, stored on the rebuild Job.
            built_at: the current dossier's build.built_at.
        """
        try:
            await freshness_mod.maybe_enqueue_rebuild(
                self._redis, self._job_queue, page_id, title, built_at
            )
        except Exception:  # noqa: BLE001 - background task must never crash the loop
            logger.exception("background rebuild check failed for page %s", page_id)

    def _dossier_links(
        self,
        dossier: Dossier,
        page_id: int,
        rev_id: int,
        budget: BudgetTokens,
        fmt: Literal["json", "markdown"],
        parts: frozenset[Part] = DEFAULT_PARTS,
    ) -> DossierLinks:
        """Build the self/pinned/markdown/wikipedia links for a dossier view.

        Args:
            dossier: the stored dossier, for the seed article's Wikipedia URL.
            page_id: Wikipedia page id.
            rev_id: pinned revision id.
            budget: requested token budget.
            fmt: "json" or "markdown".
            parts: the selected response parts; written into the self and
                markdown links unless it is the default.

        Returns:
            DossierLinks: absolute URLs rooted at `self._base_url`.
        """
        base = self._base_url
        try:
            wikipedia_url = str(seed_pin(dossier).url)
        except ValueError:
            wikipedia_url = f"{base}/api/v1/dossiers/{page_id}"
        parts_query = "" if parts == DEFAULT_PARTS else f"&parts={_parts_value(parts)}"
        dossier_url = f"{base}/api/v1/dossiers/{page_id}"
        return DossierLinks.model_validate(
            {
                "self": f"{dossier_url}?budget={budget}&format={fmt}{parts_query}",
                "pinned": f"{dossier_url}/rev/{rev_id}?budget={budget}{parts_query}",
                "markdown": f"{dossier_url}.md?budget={budget}{parts_query}",
                "wikipedia": wikipedia_url,
            }
        )
