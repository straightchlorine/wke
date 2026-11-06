"""Title search and the did-you-mean suggestion."""

from __future__ import annotations

import difflib
import json
from typing import Any

from wke.core import keys
from wke.core.models import TopicCandidate
from wke.metrics import CACHE_REQUESTS_TOTAL
from wke.services.base import ServiceBase

SEARCH_RESULT_CAP = 10

SearchEntry = dict[str, Any]


def _fold(text: str) -> str:
    """Fold text for comparison: casefold, underscores to spaces, single spaces.

    Args:
        text: the title or query.

    Returns:
        str: the folded text.
    """
    return " ".join(text.casefold().replace("_", " ").split())


def title_covers_query(q: str, title: str) -> bool:
    """Tell whether every word of the query starts some word of the title.

    Args:
        q: the search string.
        title: a result title.

    Returns:
        bool: True when the title plausibly answers the query as typed,
        including a query cut short mid-word.
    """
    title_words = _fold(title).split()
    return all(any(word.startswith(part) for word in title_words) for part in _fold(q).split())


def did_you_mean(q: str, titles: list[str], api_suggestion: str | None) -> str | None:
    """Pick a "Did you mean" title for a query that no result matches exactly.

    Args:
        q: the search string as typed.
        titles: result titles, best first.
        api_suggestion: the search API's spelling suggestion, if any.

    Returns:
        str | None: a title from `titles` when the suggestion or a very
        close spelling matches one, the API's suggestion text as given
        otherwise, or None when a result already is the query or nothing
        is close.
    """
    typed = _fold(q)
    by_fold = {_fold(t): t for t in titles if t}
    if typed in by_fold:
        return None
    if api_suggestion and _fold(api_suggestion) != typed:
        return by_fold.get(_fold(api_suggestion), api_suggestion)
    close = difflib.get_close_matches(typed, list(by_fold), n=1, cutoff=0.8)
    if close and not close[0].startswith(typed):
        return by_fold[close[0]]
    return None


class SearchMixin(ServiceBase):
    """Title search and the did-you-mean suggestion."""

    async def search(self, q: str, limit: int = 8) -> list[TopicCandidate]:
        """Title search (typeahead), cached 1 h, capped to `limit` results.

        Args:
            q: search string, 1-200 chars.
            limit: max results, 1-10.

        Returns:
            list[TopicCandidate]: candidates with dossier_state computed
            from `ptr:{page_id}`.
        """
        candidates, _suggestion = await self._search(q, limit, want_suggestion=False)
        return candidates

    async def search_with_suggestion(
        self, q: str, limit: int = 8
    ) -> tuple[list[TopicCandidate], str | None]:
        """Title search plus a "Did you mean" title for a misspelt query.

        The suggestion is the search API's own spelling suggestion when it
        gives one. When it does not and no result covers the query, one
        more fuzzy search (its own cached call) looks for a title a letter
        or two away. Nothing is suggested when a result already is the query.

        Args:
            q: search string, 1-200 chars.
            limit: max results, 1-10.

        Returns:
            tuple[list[TopicCandidate], str | None]: the candidates as in
            `search`, and the suggested title or None.
        """
        return await self._search(q, limit, want_suggestion=True)

    async def _search_call(
        self, q: str, limit: int, fuzzy: bool
    ) -> tuple[list[SearchEntry], str | None]:
        """One cached `generator=search` call (1 h), plain or fuzzy.

        Args:
            q: search string.
            limit: result cap, already clamped to 1-10.
            fuzzy: True for the per-term fuzzy variant.

        Returns:
            tuple[list[SearchEntry], str | None]: raw entries and the API suggestion.
        """
        cache_key = keys.wm_search(f"fuzzy:{q}" if fuzzy else q, limit)
        cached = await self._redis.get(cache_key)
        if cached is not None:
            CACHE_REQUESTS_TOTAL.labels(kind="search", result="hit").inc()
            data: dict[str, Any] = json.loads(cached)
            return data.get("results", []), data.get("suggestion")
        CACHE_REQUESTS_TOTAL.labels(kind="search", result="miss").inc()
        results, suggestion = await self._wikimedia.search_with_suggestion(q, limit, fuzzy=fuzzy)
        payload = json.dumps({"results": results, "suggestion": suggestion})
        await self._redis.set(cache_key, payload, ex=keys.WM_SEARCH_TTL_SECONDS)
        return results, suggestion

    async def _search(
        self, q: str, limit: int, want_suggestion: bool
    ) -> tuple[list[TopicCandidate], str | None]:
        """Run the cached search and build the candidates, with a suggestion if asked.

        Args:
            q: search string.
            limit: max results; clamped to 1-10.
            want_suggestion: whether to work out a "Did you mean" title.

        Returns:
            tuple[list[TopicCandidate], str | None]: the candidates and the
            suggested title, which is always None when `want_suggestion` is
            False.
        """
        capped_limit = min(max(limit, 1), SEARCH_RESULT_CAP)
        results, api_suggestion = await self._search_call(q, capped_limit, fuzzy=False)
        suggestion: str | None = None
        if want_suggestion:
            titles = [entry.get("title", "") for entry in results]
            suggestion = did_you_mean(q, titles, api_suggestion)
            if suggestion is None and not any(title_covers_query(q, t) for t in titles):
                fuzzy_results, _ = await self._search_call(q, capped_limit, fuzzy=True)
                suggestion = did_you_mean(q, [e.get("title", "") for e in fuzzy_results], None)

        entries = [entry for entry in results[:capped_limit] if entry.get("pageid") is not None]
        states = await self._dossier_states([entry["pageid"] for entry in entries])
        candidates = [
            TopicCandidate(
                page_id=entry["pageid"],
                title=entry.get("title", ""),
                description=None,
                dossier_state=state,
            )
            for entry, state in zip(entries, states, strict=True)
        ]
        return candidates, suggestion
