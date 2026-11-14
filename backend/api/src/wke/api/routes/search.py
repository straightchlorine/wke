"""GET /api/v1/search: title search (typeahead)."""

# Handlers are registered by the router decorator, never called by name; slowapi's
# limit() has no annotations.
# pyright: reportUnusedFunction=false, reportUnknownMemberType=false, reportUntypedFunctionDecorator=false

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from slowapi import Limiter

from wke.api.ratelimit import SEARCH_RATE_LIMIT
from wke.services.dossiers import DossierService


def build_router(limiter: Limiter) -> APIRouter:
    """Build the /api/v1/search router bound to the app's Limiter.

    Args:
        limiter: the app's slowapi Limiter. The rate-limit decorator
            must close over this exact instance rather than a
            module-level one, since create_app() can be handed a
            different Limiter per call (tests use a memory:// one).

    Returns:
        APIRouter: with the search route registered.
    """
    router = APIRouter(tags=["search"])

    @router.get("/api/v1/search")
    @limiter.limit(SEARCH_RATE_LIMIT)
    async def search_topics(
        request: Request,
        q: str = Query(..., min_length=1, max_length=200),
        limit: int = Query(8, ge=1, le=10),
    ) -> dict[str, object]:
        service: DossierService = request.app.state.service
        results, suggestion = await service.search_with_suggestion(q, limit)
        return {"query": q, "results": results, "did_you_mean": suggestion}

    return router
