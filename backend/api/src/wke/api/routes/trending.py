"""GET /api/v1/trending: yesterday's most-read topics with a similarity graph."""

# Handlers are registered by the router decorator, never called by name; slowapi's
# limit() has no annotations.
# pyright: reportUnusedFunction=false, reportUnknownMemberType=false, reportUntypedFunctionDecorator=false

from __future__ import annotations

import hashlib

from fastapi import APIRouter, Header, Request, Response
from slowapi import Limiter

from wke.api.etag import LATEST_CACHE_CONTROL, is_not_modified
from wke.api.ratelimit import GET_READS_RATE_LIMIT
from wke.core.models import TrendingSnapshot
from wke.services.dossiers import DossierService

TRENDING_TOPIC_CAP = 40


def _topic_states_digest(snapshot: TrendingSnapshot) -> str:
    """Short hash of every topic's live dossier_state, in list order.

    Args:
        snapshot: the trending snapshot about to be served.

    Returns:
        str: an 8-hex-char digest that changes whenever any topic's
        dossier_state changes, even though `date`/`generated_at` do not.
    """
    joined = "|".join(topic.dossier_state for topic in snapshot.topics)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:8]


def build_router(limiter: Limiter) -> APIRouter:
    """Build the /api/v1/trending router bound to the app's Limiter.

    Args:
        limiter: the app's slowapi Limiter.

    Returns:
        APIRouter: with the trending route registered.
    """
    router = APIRouter(tags=["trending"])

    @router.get("/api/v1/trending", response_model=TrendingSnapshot)
    @limiter.limit(GET_READS_RATE_LIMIT)
    async def get_trending(
        request: Request,
        response: Response,
        if_none_match: str | None = Header(default=None, alias="If-None-Match"),
    ) -> TrendingSnapshot | Response:
        service: DossierService = request.app.state.service
        snapshot = await service.get_trending(TRENDING_TOPIC_CAP)
        etag = (
            f'"{snapshot.date}-{snapshot.generated_at.isoformat()}-'
            f'{_topic_states_digest(snapshot)}"'
        )
        if is_not_modified(etag, if_none_match):
            return Response(
                status_code=304, headers={"ETag": etag, "Cache-Control": LATEST_CACHE_CONTROL}
            )
        response.headers["ETag"] = etag
        response.headers["Cache-Control"] = LATEST_CACHE_CONTROL
        return snapshot

    return router
