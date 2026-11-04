"""wke-ml client: /v1/analyze and /v1/summarize, one in-flight call.

wke-ml holds exactly one inference slot; this client mirrors that with its
own `asyncio.Semaphore(1)` so a second caller queues in wke-api rather than
piling up requests at wke-ml. Every request carries `X-Deadline-Ms`; the
client never caches anything itself -- only model output (the summary
content-address cache) is cached, and that lives in the caller, not here.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from wke.logging_setup import request_id_var

DEFAULT_ANALYZE_DEADLINE_MS = 8000
DEFAULT_SUMMARIZE_DEADLINE_MS = 8000


class MLUnavailable(Exception):
    """wke-ml could not be reached in time, or did not return a usable JSON body.

    Args:
        reason: short machine-readable reason: timeout, connect_error, another
            httpx error class name, http_<status> or bad_response.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class MLClient:
    """Client for wke-ml's internal analyze/summarize endpoints."""

    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._http = http_client
        self._semaphore = asyncio.Semaphore(1)

    async def analyze(
        self,
        lead: str,
        chunks: list[dict[str, str]],
        related_leads: list[dict[str, Any]] | None = None,
        max_clusters: int = 6,
        max_edges: int = 20,
        page_id: int | None = None,
        deadline_ms: int = DEFAULT_ANALYZE_DEADLINE_MS,
    ) -> dict[str, Any]:
        """Embed chunks, cluster and compute relevance and related edges.

        Args:
            lead: lead paragraph text used as the relevance anchor.
            chunks: list of {id, text} chunk payloads, max 400. Empty for
                the trending job, which analyzes bare topic leads.
            related_leads: list of {page_id, text} related-article leads.
            max_clusters: KMeans upper bound, 2-6.
            max_edges: cap on returned edges, 1-80.
            page_id: seed node id for the returned edges; omitted, wke-ml
                uses a placeholder id.
            deadline_ms: X-Deadline-Ms sent to wke-ml.

        Returns:
            dict: model, model_revision, relevance, cluster_ids,
            representatives, edges, infer_seconds.

        Raises:
            MLUnavailable: on timeout, connection error, an HTTP error status or
                a non-JSON body.
        """
        payload: dict[str, Any] = {
            "lead": lead,
            "chunks": chunks,
            "related_leads": related_leads or [],
            "max_clusters": max_clusters,
            "max_edges": max_edges,
        }
        if page_id is not None:
            payload["page_id"] = page_id
        return await self._post("/v1/analyze", payload, deadline_ms)

    async def summarize(
        self,
        text: str,
        num_beams: int = 1,
        min_length: int = 30,
        max_length: int = 96,
        deadline_ms: int = DEFAULT_SUMMARIZE_DEADLINE_MS,
    ) -> dict[str, Any]:
        """Generate an abstractive summary with distilbart-cnn-6-6.

        Args:
            text: input text, 1-20000 chars.
            num_beams: beam count, 1-4.
            min_length: minimum generated length.
            max_length: maximum generated length.
            deadline_ms: X-Deadline-Ms sent to wke-ml.

        Returns:
            dict: a MachineSummary payload.

        Raises:
            MLUnavailable: on timeout, connection error, an HTTP error status or
                a non-JSON body.
        """
        payload = {
            "text": text,
            "num_beams": num_beams,
            "min_length": min_length,
            "max_length": max_length,
        }
        return await self._post("/v1/summarize", payload, deadline_ms)

    async def readyz(self) -> bool:
        """Probe wke-ml's /readyz endpoint.

        Returns:
            bool: True if wke-ml answered 200, False on any non-200
            status, timeout or connection error.
        """
        try:
            response = await self._http.get("/readyz", timeout=5.0)
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    async def _post(self, path: str, payload: dict[str, Any], deadline_ms: int) -> dict[str, Any]:
        headers = {"X-Deadline-Ms": str(deadline_ms)}
        request_id = request_id_var.get()
        if request_id is not None:
            headers["X-Request-ID"] = request_id
        async with self._semaphore:
            try:
                response = await self._http.post(
                    path,
                    json=payload,
                    headers=headers,
                    timeout=deadline_ms / 1000,
                )
            except httpx.TimeoutException as exc:
                raise MLUnavailable("timeout") from exc
            except httpx.ConnectError as exc:
                raise MLUnavailable("connect_error") from exc
            except httpx.HTTPError as exc:
                # A wke-ml restart mid-request degrades like a timeout.
                raise MLUnavailable(exc.__class__.__name__) from exc
            if response.status_code >= 400:
                raise MLUnavailable(f"http_{response.status_code}")
            try:
                body = response.json()
            except ValueError as exc:
                raise MLUnavailable("bad_response") from exc
            if not isinstance(body, dict):
                raise MLUnavailable("bad_response")
            return body
