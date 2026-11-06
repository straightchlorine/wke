"""GET /api/v1/live: recent tracked-page edits and real counters."""

# Handlers are registered by the router decorator, never called by name; slowapi's
# limit() has no annotations.
# pyright: reportUnusedFunction=false, reportUnknownMemberType=false, reportUntypedFunctionDecorator=false

from __future__ import annotations

from fastapi import APIRouter, Query, Request, Response
from slowapi import Limiter

from wke.api.ratelimit import LIVE_RATE_LIMIT
from wke.core.models import LiveResponse
from wke.services.dossiers import DossierService


def build_router(limiter: Limiter) -> APIRouter:
    """Build the /api/v1/live router bound to the app's Limiter.

    Args:
        limiter: the app's slowapi Limiter.

    Returns:
        APIRouter: with the live-edits route registered.
    """
    router = APIRouter(tags=["live"])

    @router.get("/api/v1/live", response_model=LiveResponse)
    @limiter.limit(LIVE_RATE_LIMIT)
    async def get_live(
        request: Request,
        response: Response,
        since: int = Query(0, ge=0),
    ) -> LiveResponse:
        service: DossierService = request.app.state.service
        response.headers["Cache-Control"] = "no-store"
        return await service.get_live(since)

    return router
