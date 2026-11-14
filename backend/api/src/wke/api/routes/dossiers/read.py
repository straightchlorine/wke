"""Read routes for one built dossier: latest, Markdown and pinned revision."""

# Handlers are registered by the router decorator, never called by name; slowapi's
# limit() has no annotations.
# pyright: reportUnusedFunction=false, reportUnknownMemberType=false, reportUntypedFunctionDecorator=false

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Header, Path, Query, Request, Response
from slowapi import Limiter

from wke.api.etag import cache_control_for, is_not_modified
from wke.api.openapi_docs import error_response
from wke.api.ratelimit import GET_READS_RATE_LIMIT
from wke.api.routes.dossiers.body import dossier_body, token_headers
from wke.api.routes.dossiers.docs import (
    BUDGET_OPENAPI_PARAM,
    DOSSIER_200_RESPONSE,
    MARKDOWN_CONTENT,
    NOT_BUILT_RESPONSE,
    NOT_MODIFIED_RESPONSE,
    PARTS_OPENAPI_PARAM,
    RATE_LIMITED_RESPONSE,
    TOKEN_HEADERS,
)
from wke.api.routes.dossiers.params import FormatParam, parse_budget, parse_format, view_etag
from wke.core.models import DossierResponse
from wke.core.render.defaults import DEFAULT_INCLUDE_SUMMARIES
from wke.core.render.parts import parse_parts
from wke.services.dossiers import DossierService


async def _serve_dossier(
    request: Request,
    page_id: int,
    fmt: Literal["json", "markdown"],
    summaries: bool,
    links: bool,
    if_none_match: str | None,
    rev_id: int | None = None,
    discovery_headers: bool = False,
) -> Response:
    """Pack a built dossier and answer a read with ETag, 304 and the token headers.

    Args:
        request: the in-flight request (budget and parts are read from its query).
        page_id: the Wikipedia page id.
        fmt: "json" or "markdown".
        summaries: whether to pack and render the stored summaries.
        links: whether the Markdown carries inline links.
        if_none_match: the If-None-Match request header, if any.
        rev_id: the pinned revision for the immutable route, None for the latest build.
        discovery_headers: whether to add WKE-Freshness and the Link header.

    Returns:
        Response: the 304, or the body with ETag, Cache-Control and the token headers.

    Raises:
        ApiException: 422 validation_error on a bad budget or parts, 404 not_built
            when nothing is stored.
    """
    service: DossierService = request.app.state.service
    budget = parse_budget(request.query_params.get("budget"))
    parts = parse_parts(request.query_params.get("parts"))
    view = await service.get_dossier_view(
        page_id, budget, "json", summaries, rev_id=rev_id, parts=parts
    )
    # Only a complete, ml-analyzed build at a pinned revision is truly immutable:
    # a partial build (summaries still pending) or a structural-fallback build
    # (short-TTL, meant to be rebuilt) can still change in place, so caching it
    # for a year would freeze it.
    is_final = rev_id is not None and view.build.state == "complete" and view.build.analysis == "ml"
    headers = {
        "ETag": view_etag(view, budget, fmt, summaries, links, parts),
        "Cache-Control": cache_control_for("revision" if is_final else "latest"),
    }
    if is_not_modified(headers["ETag"], if_none_match):
        return Response(status_code=304, headers=headers)
    body, media_type = dossier_body(view, fmt, summaries, links, parts)
    headers.update(token_headers(view, body))
    if discovery_headers:
        headers["WKE-Freshness"] = view.freshness.state
        headers["Link"] = (
            f'<{view.links.markdown}>; rel="alternate"; type="text/markdown", '
            '</llms.txt>; rel="describedby"'
        )
    return Response(content=body, media_type=media_type, headers=headers)


def register_get_dossier(router: APIRouter, limiter: Limiter) -> None:
    """Register GET /api/v1/dossiers/{page_id}: the packed dossier as JSON or Markdown.

    Args:
        router: the dossiers router.
        limiter: the app's slowapi Limiter.
    """

    @router.get(
        "/api/v1/dossiers/{page_id:int}",
        response_model=DossierResponse,
        openapi_extra={"parameters": [BUDGET_OPENAPI_PARAM, PARTS_OPENAPI_PARAM]},
        responses={
            "200": DOSSIER_200_RESPONSE,
            "304": NOT_MODIFIED_RESPONSE,
            "404": NOT_BUILT_RESPONSE,
            "422": error_response("Validation error"),
            "429": RATE_LIMITED_RESPONSE,
        },
    )
    @limiter.limit(GET_READS_RATE_LIMIT)
    async def get_dossier(
        request: Request,
        page_id: int = Path(..., ge=1),
        format: FormatParam = Query("json"),
        summaries: bool = Query(DEFAULT_INCLUDE_SUMMARIES),
        links: bool = Query(False),
        if_none_match: str | None = Header(default=None, alias="If-None-Match"),
    ) -> Response:
        return await _serve_dossier(
            request,
            page_id,
            parse_format(format),
            summaries,
            links,
            if_none_match,
            discovery_headers=True,
        )


def register_get_markdown(router: APIRouter, limiter: Limiter) -> None:
    """Register GET /api/v1/dossiers/{page_id}.md: the packed dossier as Markdown.

    Args:
        router: the dossiers router.
        limiter: the app's slowapi Limiter.
    """

    @router.get(
        "/api/v1/dossiers/{page_id:int}.md",
        openapi_extra={"parameters": [BUDGET_OPENAPI_PARAM, PARTS_OPENAPI_PARAM]},
        response_class=Response,
        responses={
            "200": {
                "description": "Markdown",
                "headers": TOKEN_HEADERS,
                "content": MARKDOWN_CONTENT,
            },
            "304": NOT_MODIFIED_RESPONSE,
            "404": NOT_BUILT_RESPONSE,
            "422": error_response("Validation error"),
            "429": RATE_LIMITED_RESPONSE,
        },
    )
    @limiter.limit(GET_READS_RATE_LIMIT)
    async def get_dossier_markdown(
        request: Request,
        page_id: int = Path(..., ge=1),
        summaries: bool = Query(DEFAULT_INCLUDE_SUMMARIES),
        links: bool = Query(False),
        if_none_match: str | None = Header(default=None, alias="If-None-Match"),
    ) -> Response:
        return await _serve_dossier(request, page_id, "markdown", summaries, links, if_none_match)


def register_get_revision(router: APIRouter, limiter: Limiter) -> None:
    """Register GET /api/v1/dossiers/{page_id}/rev/{rev_id}: one pinned revision.

    Args:
        router: the dossiers router.
        limiter: the app's slowapi Limiter.
    """

    @router.get(
        "/api/v1/dossiers/{page_id:int}/rev/{rev_id:int}",
        response_model=DossierResponse,
        openapi_extra={"parameters": [BUDGET_OPENAPI_PARAM, PARTS_OPENAPI_PARAM]},
        responses={
            "200": DOSSIER_200_RESPONSE,
            "304": NOT_MODIFIED_RESPONSE,
            "404": NOT_BUILT_RESPONSE,
            "422": error_response("Validation error"),
            "429": RATE_LIMITED_RESPONSE,
        },
    )
    @limiter.limit(GET_READS_RATE_LIMIT)
    async def get_dossier_revision(
        request: Request,
        page_id: int = Path(..., ge=1),
        rev_id: int = Path(..., ge=1),
        format: FormatParam = Query("json"),
        summaries: bool = Query(DEFAULT_INCLUDE_SUMMARIES),
        links: bool = Query(False),
        if_none_match: str | None = Header(default=None, alias="If-None-Match"),
    ) -> Response:
        return await _serve_dossier(
            request, page_id, parse_format(format), summaries, links, if_none_match, rev_id=rev_id
        )
