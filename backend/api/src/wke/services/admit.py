"""Build admission: pin a revision, queue a job, report job state."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Literal, NoReturn

from wke.core import keys
from wke.core.errors import ApiException
from wke.core.models import DossierState, Job
from wke.core.titles import normalize_title
from wke.core.viewcache import invalidate_views
from wke.metrics import CACHE_REQUESTS_TOTAL
from wke.services.search import SearchMixin

DISAMBIGUATION_CANDIDATES = 8


def _require_article(page: dict[str, Any], title: str) -> None:
    """Reject a missing page or a page outside the article namespace.

    Args:
        page: the Wikimedia page record.
        title: article title as submitted, for the error detail.

    Raises:
        ApiException: 404 not_found or 404 not_article.
    """
    if not page or page.get("missing"):
        raise ApiException(404, "not_found", detail=f"No Wikipedia article titled {title!r}.")
    if page.get("ns") != 0:
        raise ApiException(
            404,
            "not_article",
            detail="That title is not an article (talk, user and category pages are not built).",
        )


class AdmitMixin(SearchMixin):
    """Build admission: pin a revision, queue a job, report job state."""

    async def request_build(self, title: str, refresh: bool = False) -> Job | Literal["ready"]:
        """Resolve a title and admit a build (stages 0-1 of the pipeline).

        Args:
            title: article title as submitted.
            refresh: force a rebuild of the current revision even if a
                dossier for it already exists.

        Returns:
            Job | "ready": "ready" if a dossier already exists for the
            current revision; otherwise the (new or in-flight) Job.

        Raises:
            ApiException: 404 not_found (page missing), 404 not_article
                (non-article namespace), 409 disambiguation (with
                candidates), or whatever WikimediaClient/JobQueue raise.
        """
        _, _, result = await self.resolve_and_admit(title, refresh=refresh)
        return result

    async def resolve_and_admit(
        self,
        title: str,
        refresh: bool = False,
        gate: Callable[[], None] | None = None,
    ) -> tuple[int, int, Job | Literal["ready"]]:
        """Resolve a title and admit a build, also returning the page id.

        Same resolution and admission as `request_build`, but also
        returns page_id/rev_id so callers (the POST route, MCP's
        get_dossier) can pack a "ready" result without re-resolving the
        title.

        Args:
            title: article title as submitted.
            refresh: force a rebuild of the current revision even if a
                dossier for it already exists.
            gate: forwarded to `JobQueue.admit`; runs only when a build
                would be joined or started, and may raise to refuse it.

        Returns:
            tuple[int, int, Job | "ready"]: page_id, rev_id, and the
            admission result.

        Raises:
            ApiException: same as `request_build`.
        """
        if refresh:
            invalidate_views()
        normalized = normalize_title(title)
        page = await self._resolve_page(normalized)
        _require_article(page, title)
        if "disambiguation" in (page.get("pageprops") or {}):
            await self._raise_disambiguation(title, normalized)

        page_id = page["pageid"]
        rev_id = page["lastrevid"]
        await self._cache_revision_timestamp(page, rev_id)
        # Stale-while-revalidate, never delete: refresh=true admits a
        # rebuild but leaves the existing dossier in place for readers
        # until the rebuild finalizes and overwrites it. jobkey dedup
        # still applies, so concurrent refreshes admit at most one rebuild.
        result = await self._job_queue.admit(
            page_id,
            rev_id,
            page.get("title", normalized),
            background=refresh,
            force=refresh,
            gate=gate,
        )
        return page_id, rev_id, result

    async def _resolve_page(self, normalized: str) -> dict[str, Any]:
        """Resolve a normalized title through the wm:resolve cache.

        Args:
            normalized: the normalized article title.

        Returns:
            dict[str, Any]: the Wikimedia page record (may be empty or marked missing).
        """
        cache_key = keys.wm_resolve(normalized)
        cached = await self._redis.get(cache_key)
        if cached is not None:
            CACHE_REQUESTS_TOTAL.labels(kind="resolve", result="hit").inc()
            return json.loads(cached)
        CACHE_REQUESTS_TOTAL.labels(kind="resolve", result="miss").inc()
        page = await self._wikimedia.resolve(normalized)
        await self._redis.set(cache_key, json.dumps(page), ex=keys.WM_RESOLVE_TTL_SECONDS)
        return page

    async def _raise_disambiguation(self, title: str, normalized: str) -> NoReturn:
        """Refuse a disambiguation page with real search candidates.

        Candidates come from the search path (the same 1 h wm:search cache
        as `search()`), not from the disambiguation page's links, so every
        candidate carries a real page_id and an honest dossier_state.

        Args:
            title: article title as submitted.
            normalized: the normalized title, excluded from the candidates.

        Raises:
            ApiException: always, 409 disambiguation with candidates.
        """
        candidates = [
            candidate
            for candidate in await self.search(title, limit=DISAMBIGUATION_CANDIDATES)
            if normalize_title(candidate.title) != normalized
        ]
        raise ApiException(
            409,
            "disambiguation",
            detail=f"{title!r} is a disambiguation page. Pick one of the candidates.",
            candidates=candidates,
        )

    async def _cache_revision_timestamp(self, page: dict[str, Any], rev_id: int) -> None:
        """Cache the edit time of the pinned revision for the build.

        Captured at the same instant rev_id was resolved, so it is always
        the edit time of exactly that revision, not whatever is latest by
        the time the worker picks the job up.

        Args:
            page: the Wikimedia page record.
            rev_id: the pinned revision id.
        """
        revisions: list[dict[str, Any]] = page.get("revisions") or []
        raw_timestamp: str | None = revisions[0].get("timestamp") if revisions else None
        if raw_timestamp:
            await self._redis.set(
                keys.wm_revts(rev_id),
                raw_timestamp.replace("Z", "+00:00"),
                ex=keys.WM_HTML_TTL_SECONDS,
            )

    async def peek_dossier_state_for_title(self, title: str) -> tuple[int, DossierState] | None:
        """Look up a title's page id and dossier state from cache only.

        Makes no Wikimedia call: if the title's resolve result is not
        already warm in Redis, the title is unresolved as far as this
        method is concerned. Used to word a rate-limit error honestly
        (e.g. "the existing dossier is still readable") without spending
        an extra request just to build that sentence.

        Args:
            title: article title as submitted.

        Returns:
            tuple[int, DossierState] | None: (page_id, dossier_state) if the
            title's resolve result is cached; None otherwise.
        """
        normalized = normalize_title(title)
        cached = await self._redis.get(keys.wm_resolve(normalized))
        if cached is None:
            return None
        page = json.loads(cached)
        page_id = page.get("pageid") if page and not page.get("missing") else None
        if page_id is None:
            return None
        return page_id, await self._dossier_state(page_id)

    async def get_job(self, job_id: str) -> Job | None:
        """Read a build job's current status.

        Args:
            job_id: 16 hex char job id.

        Returns:
            Job | None: None if the job does not exist or has expired.
        """
        return await self._job_queue.get_job(job_id)
