"""Wikimedia Action API and Parsoid client.

Unauthenticated, one call at a time across every process, shared 150/min budget.
"""

from __future__ import annotations

from typing import Any

from wke.clients.wikimedia_transport import (
    PAGEVIEWS_API_URL,
    CallMode,
    WikimediaTransport,
)
from wke.core.errors import ApiException

EXTRACTS_EXLIMIT_MAX = 20

MAX_REVISION_HTML_BYTES = 5 * 1024 * 1024


class WikifeedsNotFound(Exception):
    """Wikifeeds has not published the featured feed for a date yet (HTTP 404).

    Args:
        date: the ISO date (`YYYY-MM-DD`) that was requested.
    """

    def __init__(self, date: str) -> None:
        super().__init__(date)
        self.date = date


class WikimediaClient(WikimediaTransport):
    """Client for the Action API and Parsoid REST API, budget/lock/pace aware."""

    async def resolve(self, title: str) -> dict[str, Any]:
        """Stage 0: resolve a title to page_id, lastrevid and links.

        Args:
            title: article title as typed or linked (not yet normalized).

        Returns:
            dict: the single `query.pages[0]` object from the Action API,
            with a `revisions[0].timestamp` for the resolved revision.
        """
        params = {
            "action": "query",
            "titles": title,
            "format": "json",
            "formatversion": "2",
            "redirects": "1",
            "prop": "info|pageprops|description|links|revisions",
            "pllimit": "10",
            "plnamespace": "0",
            "rvprop": "timestamp",
        }
        response = await self._call("GET", self._action_api_url, params, action_api=True)
        body = response.json()

        pages = body.get("query", {}).get("pages", [])
        return pages[0] if pages else {}

    async def revision_html(self, rev_id: int, mode: CallMode = "inline") -> str:
        """Stage 2: fetch Parsoid HTML for a pinned revision.

        Args:
            rev_id: revision id to fetch; asserted against the response's
                content-revision-id header.
            mode: "inline" or "worker", selects the lock-wait deadline.

        Returns:
            str: the Parsoid HTML document.

        Raises:
            ApiException: upstream_unavailable if the content-revision-id
                header does not match rev_id, or the body exceeds 5 MB.
        """
        url = f"{self._rest_api_url}/revision/{rev_id}/html"
        response = await self._call("GET", url, params=None, action_api=False, mode=mode)

        if len(response.content) > MAX_REVISION_HTML_BYTES:
            raise ApiException(
                503, "upstream_unavailable", detail="Parsoid HTML exceeded the 5 MB cap."
            )

        served_rev_id = response.headers.get("content-revision-id")

        if served_rev_id != str(rev_id):
            raise ApiException(
                503,
                "upstream_unavailable",
                detail=(
                    f"content-revision-id {served_rev_id!r} did not match "
                    f"requested rev_id {rev_id}."
                ),
            )
        return response.text

    async def morelike(self, title: str, mode: CallMode = "inline") -> list[dict[str, Any]]:
        """Stage 4: fetch up to 8 related leads via `morelike:` search.

        Args:
            title: seed article title.
            mode: "inline" or "worker", selects the lock-wait deadline.

        Returns:
            list[dict]: `query.pages` entries with extracts, lastrevid and
            a `revisions[0].timestamp` for the pinned revision.
        """
        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": f"morelike:{title}",
            "gsrlimit": "8",
            "gsrnamespace": "0",
            "prop": "extracts|info|revisions",
            "exintro": "1",
            "explaintext": "1",
            "exlimit": "8",
            "rvprop": "timestamp",
            "format": "json",
            "formatversion": "2",
        }

        response = await self._call("GET", self._action_api_url, params, action_api=True, mode=mode)
        body = response.json()

        return body.get("query", {}).get("pages", [])

    async def revision_timestamp(self, rev_id: int, mode: CallMode = "inline") -> str:
        """Stage 2: fetch the edit timestamp of one pinned revision.

        Used to fill `RevisionPin.rev_timestamp` with the real time the
        revision was made, never the time WKE happened to build it.

        Args:
            rev_id: revision id to look up.
            mode: "inline" or "worker", selects the lock-wait deadline.

        Returns:
            str: the revision's `timestamp` field, ISO 8601 UTC.

        Raises:
            ApiException: upstream_unavailable if the revision is missing
                or the response carries no timestamp.
        """
        params = {
            "action": "query",
            "revids": str(rev_id),
            "prop": "revisions",
            "rvprop": "timestamp",
            "format": "json",
            "formatversion": "2",
        }
        response = await self._call("GET", self._action_api_url, params, action_api=True, mode=mode)

        body = response.json()
        pages = body.get("query", {}).get("pages", [])
        revisions = pages[0].get("revisions", []) if pages else []
        timestamp = revisions[0].get("timestamp") if revisions else None

        if not timestamp:
            raise ApiException(
                503,
                "upstream_unavailable",
                detail=f"No revision timestamp returned for rev_id {rev_id}.",
            )
        return timestamp

    async def search(self, q: str, limit: int) -> list[dict[str, Any]]:
        """Typeahead search: one `generator=search` call, disambiguation pages dropped.

        Args:
            q: search string.
            limit: max results, 1-10.

        Returns:
            list[dict]: `pageid` / `title` entries in search order.
        """
        results, _suggestion = await self.search_with_suggestion(q, limit)
        return results

    async def search_with_suggestion(
        self, q: str, limit: int, fuzzy: bool = False
    ) -> tuple[list[dict[str, Any]], str | None]:
        """One `generator=search` call that also asks for the API's spelling suggestion.

        The same request carries `pageprops=disambiguation`, so pages that are
        disambiguation pages are dropped here and never offered as a topic
        (building one returns 409).

        Args:
            q: search string.
            limit: max results, 1-10.
            fuzzy: True to search every term with CirrusSearch's `~` fuzzy
                operator, which finds titles one or two letters away from
                a misspelt query (the plain search does not).

        Returns:
            tuple[list[dict], str | None]: the non-disambiguation pages as
            `pageid` / `title` entries in search order, and
            `query.searchinfo.suggestion`, or None if the API offered none.
        """
        srsearch = " ".join(f"{term}~" for term in q.split()) if fuzzy else q
        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": srsearch,
            "gsrlimit": str(limit),
            "gsrnamespace": "0",
            "gsrinfo": "suggestion",
            "prop": "pageprops",
            "ppprop": "disambiguation",
            "format": "json",
            "formatversion": "2",
        }

        response = await self._call("GET", self._action_api_url, params, action_api=True)
        query = response.json().get("query", {})
        suggestion = query.get("searchinfo", {}).get("suggestion")
        pages = sorted(query.get("pages", []), key=lambda page: page.get("index", 0))

        results = [
            {"pageid": page["pageid"], "title": page.get("title", "")}
            for page in pages
            if "pageid" in page and "disambiguation" not in page.get("pageprops", {})
        ]
        return results, suggestion

    async def mostread(self, date: str, mode: CallMode = "inline") -> dict[str, Any]:
        """Trending stage 1: fetch the `mostread` object of a Wikifeeds featured feed.

        The feed published for day D holds the most-read list of day D-1;
        the returned object's `date` field says which day that is. A REST
        call (Wikifeeds), so no `maxlag` param is sent.

        Args:
            date: ISO date `YYYY-MM-DD` of the feed to request (not of the
                list it carries).
            mode: "inline" or "worker", selects the lock-wait deadline.

        Returns:
            dict: the feed's `mostread` object (`articles`, `date`); empty
            when the feed carries none.

        Raises:
            WikifeedsNotFound: the feed for this date has not been
                published yet (HTTP 404).
        """
        from wke.settings import settings

        year, month, day = date.split("-")
        base = str(settings.wikifeeds_url).rstrip("/")
        url = f"{base}/{year}/{month}/{day}"

        response = await self._call("GET", url, params=None, action_api=False, mode=mode)

        if response.status_code == 404:
            raise WikifeedsNotFound(date)

        mostread = self._json_object(response).get("mostread")

        return mostread if isinstance(mostread, dict) else {}

    async def pageviews_top(self, date: str, mode: CallMode = "inline") -> dict[str, Any]:
        """Trending fallback stage: fetch AQS Pageviews top for a UTC date.

        A REST call (AQS), so no `maxlag` param is sent.

        Args:
            date: ISO date `YYYY-MM-DD` (yesterday UTC).
            mode: "inline" or "worker", selects the lock-wait deadline.

        Returns:
            dict: the first `items[]` entry (`articles`, `year`, `month`,
            `day`), or `{"articles": []}` if the response carried none.
        """
        year, month, day = date.split("-")
        url = f"{PAGEVIEWS_API_URL}/en.wikipedia/all-access/{year}/{month}/{day}"

        response = await self._call("GET", url, params=None, action_api=False, mode=mode)
        items = self._json_object(response).get("items", [])
        return items[0] if items else {"articles": []}

    async def page_extracts(
        self, titles: list[str], mode: CallMode = "inline"
    ) -> list[dict[str, Any]]:
        """Trending fallback stage: batched lead extracts for up to 20 titles.

        Args:
            titles: up to 20 article titles (TextExtracts `exlimit` cap).
            mode: "inline" or "worker", selects the lock-wait deadline.

        Returns:
            list[dict]: `query.pages` entries with `extract`, `description`
            and `lastrevid`.
        """
        params = {
            "action": "query",
            "titles": "|".join(titles[:EXTRACTS_EXLIMIT_MAX]),
            "prop": "extracts|info|description",
            "exintro": "1",
            "explaintext": "1",
            "exlimit": str(min(len(titles), EXTRACTS_EXLIMIT_MAX)),
            "format": "json",
            "formatversion": "2",
        }

        response = await self._call("GET", self._action_api_url, params, action_api=True, mode=mode)
        body = response.json()
        return body.get("query", {}).get("pages", [])
