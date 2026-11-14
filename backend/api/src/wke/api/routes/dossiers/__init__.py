"""POST/GET /api/v1/dossiers and its page_id/rev_id sub-routes."""

from __future__ import annotations

from fastapi import APIRouter
from slowapi import Limiter

from wke.api.routes.dossiers.listing import register_list_route
from wke.api.routes.dossiers.read import (
    register_get_dossier,
    register_get_markdown,
    register_get_revision,
)
from wke.api.routes.dossiers.submit import register_submit_route


def build_router(limiter: Limiter) -> APIRouter:
    """Build the /api/v1/dossiers routers bound to the app's Limiter.

    Args:
        limiter: the app's slowapi Limiter.

    Returns:
        APIRouter: with all dossier routes registered.
    """
    router = APIRouter(tags=["dossiers"])
    register_list_route(router, limiter)
    register_submit_route(router, limiter)
    register_get_dossier(router, limiter)
    register_get_markdown(router, limiter)
    register_get_revision(router, limiter)
    return router
