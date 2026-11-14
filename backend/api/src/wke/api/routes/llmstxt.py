"""GET /llms.txt: the machine-readable index of the site."""

# Handlers are registered by the router decorator, never called by name.
# pyright: reportUnusedFunction=false

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from wke.api.etag import body_etag, is_not_modified
from wke.api.llmstxt import render_llms_txt
from wke.services.dossiers import DossierService

CACHE_CONTROL = "public, max-age=300"


def build_router() -> APIRouter:
    """Build the router of GET /llms.txt.

    Returns:
        APIRouter: with the route registered.
    """
    router = APIRouter()

    @router.get("/llms.txt", tags=["machine"])
    async def llmstxt_route(request: Request) -> Response:
        service: DossierService = request.app.state.service
        body = await render_llms_txt(service)
        etag = body_etag(body, "utf-8")
        headers = {"ETag": etag, "Cache-Control": CACHE_CONTROL}
        if is_not_modified(etag, request.headers.get("if-none-match")):
            return Response(status_code=304, headers=headers)
        return Response(content=body, media_type="text/markdown", headers=headers)

    return router
