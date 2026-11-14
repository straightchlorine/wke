"""GET /sitemap.xml: stored dossiers as sitemap entries."""

# Handlers are registered by the router decorator, never called by name.
# pyright: reportUnusedFunction=false

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from wke.api.etag import body_etag, is_not_modified
from wke.api.sitemap import render_sitemap
from wke.services.dossiers import DossierService

CACHE_CONTROL = "public, max-age=300"


def build_router() -> APIRouter:
    """Build the router of GET /sitemap.xml.

    Returns:
        APIRouter: with the route registered.
    """
    router = APIRouter()

    @router.get("/sitemap.xml", tags=["machine"])
    async def sitemap_route(request: Request) -> Response:
        service: DossierService = request.app.state.service
        body = await render_sitemap(service)
        etag = body_etag(body, "ascii")
        headers = {"ETag": etag, "Cache-Control": CACHE_CONTROL}
        if is_not_modified(etag, request.headers.get("if-none-match")):
            return Response(status_code=304, headers=headers)
        return Response(content=body, media_type="application/xml", headers=headers)

    return router
