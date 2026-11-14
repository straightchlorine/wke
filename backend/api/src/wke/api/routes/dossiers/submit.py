"""POST /api/v1/dossiers: admit a title and answer 200 (built) or 202 (queued)."""

# Handlers are registered by the router decorator, never called by name.
# pyright: reportUnusedFunction=false

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import limits
from fastapi import APIRouter, Body, Request, Response
from slowapi import Limiter
from slowapi.util import get_remote_address

from wke.api.openapi_docs import error_response
from wke.api.ratelimit import POST_DOSSIERS_RATE_LIMIT
from wke.api.routes.dossiers.body import dossier_body, token_headers
from wke.api.routes.dossiers.docs import (
    PARTS_OPENAPI_PARAM,
    POST_REQUEST_BODY,
    RATE_LIMITED_RESPONSE,
    TOKEN_HEADERS,
)
from wke.api.routes.dossiers.params import DEFAULT_BUDGET, parse_dossier_request, view_etag
from wke.api.routes.jobs import retry_after_seconds
from wke.core.errors import ApiException
from wke.core.models import DossierResponse, Job
from wke.core.render.defaults import DEFAULT_INCLUDE_SUMMARIES
from wke.core.render.parts import Part, parse_parts
from wke.services.dossiers import DossierService

# A forced rebuild draws on its own per-IP allowance, apart from the build limit.
_REFRESH_PER_HOUR = 2
_REFRESH_RATE_LIMIT = limits.parse(f"{_REFRESH_PER_HOUR}/hour")
_REFRESH_LIMIT_TEXT = f"Refresh limit reached ({_REFRESH_PER_HOUR} per hour per IP)."
_REFRESH_RETRY_AFTER_S = 3600
_BUILD_RETRY_AFTER_S = 60

# Applied by hand as an admission gate in request_dossier, not via
# @limiter.limit, so that only a queued build (202) draws against it and a
# refused one queues nothing: a POST that resolves to an already-built
# dossier (200) costs the caller nothing.
_POST_DOSSIERS_RATE_LIMIT = limits.parse(POST_DOSSIERS_RATE_LIMIT)

_POST_RESPONSES: dict[int | str, dict[str, Any]] = {
    "200": {
        "description": "Dossier already built",
        "model": DossierResponse,
        "headers": {"ETag": {"schema": {"type": "string"}}, **TOKEN_HEADERS},
    },
    "202": {
        "description": "Build queued or already in flight",
        "model": Job,
        "headers": {
            "Location": {"schema": {"type": "string"}},
            "Retry-After": {"schema": {"type": "integer"}},
        },
    },
    "404": error_response("Unknown title or not an article (not_found, not_article)"),
    "409": error_response("Disambiguation page; pick a candidate"),
    "422": error_response("Validation error"),
    "429": RATE_LIMITED_RESPONSE,
    "503": error_response("Wikimedia budget exhausted, unavailable or queue full"),
}


async def _refresh_limited_detail(service: DossierService, title: str) -> str:
    """Word the refresh-limit 429 honestly about the existing dossier.

    Args:
        service: the dossier service.
        title: the requested article title.

    Returns:
        str: mentions the cached dossier and its GET route when one is
        already known to exist; a plain limit message otherwise.
    """
    peek = await service.peek_dossier_state_for_title(title)
    if peek is not None and peek[1] in ("ready", "partial"):
        page_id, _state = peek
        return (
            f"{_REFRESH_LIMIT_TEXT} "
            f"The existing dossier is still readable at GET /api/v1/dossiers/{page_id}."
        )
    return _REFRESH_LIMIT_TEXT


async def _enforce_refresh_limit(
    limiter: Limiter, request: Request, service: DossierService, title: str
) -> None:
    """Draw one refresh from the caller's per-IP allowance.

    Args:
        limiter: the app's slowapi Limiter.
        request: the in-flight POST request.
        service: the dossier service.
        title: the requested article title.

    Raises:
        ApiException: 429 rate_limited when the refresh allowance is spent.
    """
    if limiter.limiter.hit(_REFRESH_RATE_LIMIT, "refresh", get_remote_address(request)):
        return
    raise ApiException(
        429,
        "rate_limited",
        detail=await _refresh_limited_detail(service, title),
        retry_after=_REFRESH_RETRY_AFTER_S,
    )


def _make_build_gate(limiter: Limiter, request: Request) -> Callable[[], None]:
    """Build the admission gate that charges the per-IP build limit.

    Args:
        limiter: the app's slowapi Limiter.
        request: the in-flight POST request.

    Returns:
        Callable[[], None]: runs inside the admission, after the ready check
        and before any job is written, so a refused request queues nothing.
    """

    def build_gate() -> None:
        if not limiter.limiter.hit(
            _POST_DOSSIERS_RATE_LIMIT, "dossiers", get_remote_address(request)
        ):
            raise ApiException(
                429,
                "rate_limited",
                detail=(
                    f"Too many builds from this IP ({POST_DOSSIERS_RATE_LIMIT}). Try again later."
                ),
                retry_after=_BUILD_RETRY_AFTER_S,
            )

    return build_gate


async def _ready_dossier(service: DossierService, page_id: int, parts: frozenset[Part]) -> Response:
    """Serve the already-built dossier for a POST that resolved to ready.

    Args:
        service: the dossier service.
        page_id: the resolved page id.
        parts: the selected response parts.

    Returns:
        Response: the default-budget JSON body, equal to the GET body for the
        same parts, with the same ETag and the two token headers.
    """
    view = await service.get_dossier_view(
        page_id, DEFAULT_BUDGET, "json", DEFAULT_INCLUDE_SUMMARIES, parts=parts
    )
    body, media_type = dossier_body(view, "json", DEFAULT_INCLUDE_SUMMARIES, False, parts)
    etag = view_etag(view, DEFAULT_BUDGET, "json", DEFAULT_INCLUDE_SUMMARIES, parts=parts)
    return Response(
        content=body,
        media_type=media_type,
        headers={"ETag": etag, **token_headers(view, body)},
    )


def _queued_job(job: Job, response: Response) -> Job:
    """Stamp a 202 response with the job's Location and Retry-After.

    Args:
        job: the queued or in-flight build job.
        response: the response to mutate.

    Returns:
        Job: the same job, for the response body.
    """
    response.status_code = 202
    response.headers["Location"] = f"/api/v1/jobs/{job.id}"
    response.headers["Retry-After"] = retry_after_seconds(job)
    return job


def register_submit_route(router: APIRouter, limiter: Limiter) -> None:
    """Register POST /api/v1/dossiers.

    Args:
        router: the dossiers router.
        limiter: the app's slowapi Limiter.
    """

    @router.post(
        "/api/v1/dossiers",
        status_code=200,
        response_model=None,
        openapi_extra={"requestBody": POST_REQUEST_BODY, "parameters": [PARTS_OPENAPI_PARAM]},
        responses=_POST_RESPONSES,
    )
    async def request_dossier(
        request: Request,
        response: Response,
        payload: dict[str, Any] = Body(...),
    ) -> Response | Job:
        title, refresh = parse_dossier_request(payload)
        parts = parse_parts(request.query_params.get("parts"))
        service: DossierService = request.app.state.service
        if refresh:
            await _enforce_refresh_limit(limiter, request, service, title)
        page_id, _rev_id, result = await service.resolve_and_admit(
            title, refresh=refresh, gate=_make_build_gate(limiter, request)
        )
        if result == "ready":
            return await _ready_dossier(service, page_id, parts)
        return _queued_job(result, response)
