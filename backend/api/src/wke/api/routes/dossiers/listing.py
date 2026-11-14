"""GET /api/v1/dossiers: one page of built dossiers."""

# Handlers are registered by the router decorator, never called by name; slowapi's
# limit() has no annotations.
# pyright: reportUnusedFunction=false, reportUnknownMemberType=false, reportUntypedFunctionDecorator=false

from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, Header, Query, Request, Response
from slowapi import Limiter

from wke.api.etag import LIST_CACHE_CONTROL, is_not_modified
from wke.api.openapi_docs import error_response
from wke.api.ratelimit import GET_READS_RATE_LIMIT
from wke.api.routes.dossiers.docs import RATE_LIMITED_RESPONSE
from wke.services.dossiers import DossierService


def register_list_route(router: APIRouter, limiter: Limiter) -> None:
    """Register GET /api/v1/dossiers.

    Args:
        router: the dossiers router.
        limiter: the app's slowapi Limiter.
    """

    @router.get(
        "/api/v1/dossiers",
        responses={
            "200": {
                "description": "One page of built dossiers, newest first",
                "headers": {
                    "ETag": {"schema": {"type": "string"}},
                    "Cache-Control": {"schema": {"type": "string"}},
                },
            },
            "304": {"description": "If-None-Match matched the ETag"},
            "422": error_response("Validation error"),
            "429": RATE_LIMITED_RESPONSE,
        },
    )
    @limiter.limit(GET_READS_RATE_LIMIT)
    async def list_dossiers(
        request: Request,
        q: str | None = Query(default=None, min_length=1, max_length=200),
        limit: int = Query(50, ge=1, le=100),
        cursor: str | None = Query(default=None),
        if_none_match: str | None = Header(default=None, alias="If-None-Match"),
    ) -> Response:
        service: DossierService = request.app.state.service
        items, next_cursor = await service.list_dossiers(q, limit, cursor)
        body = json.dumps(
            {"items": [item.model_dump(mode="json") for item in items], "next_cursor": next_cursor},
            separators=(",", ":"),
        )
        etag = f'"{hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]}"'
        headers = {"ETag": etag, "Cache-Control": LIST_CACHE_CONTROL}
        if is_not_modified(etag, if_none_match):
            return Response(status_code=304, headers=headers)
        return Response(content=body, media_type="application/json", headers=headers)
