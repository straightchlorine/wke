"""problem+json responses and the FastAPI exception handlers that produce them."""

from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from wke.core.errors import PROBLEM_BASE_URI, PROBLEM_MEDIA_TYPE, ApiException
from wke.core.models import ApiError, ErrorCode, TopicCandidate

logger = logging.getLogger(__name__)

_STATUS_TITLES: dict[int, str] = {
    400: "Bad Request",
    404: "Not Found",
    409: "Conflict",
    422: "Unprocessable Entity",
    429: "Too Many Requests",
    500: "Internal Server Error",
    503: "Service Unavailable",
}


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", str(uuid.uuid4()))


def build_error_response(
    request: Request,
    status_code: int,
    code: ErrorCode,
    detail: str | None,
    retry_after: int | None = None,
    candidates: list[TopicCandidate] | None = None,
) -> JSONResponse:
    """Build a problem+json response for the given request and error.

    Args:
        request: the in-flight request (used for request_id).
        status_code: HTTP status to respond with.
        code: machine-readable ApiError.code.
        detail: human-readable detail, omitted from the body if None.
        retry_after: seconds to wait before retrying, sets Retry-After.
        candidates: disambiguation candidates (code == "disambiguation" only).

    Returns:
        JSONResponse: with the problem+json media type and body.
    """
    problem = ApiError(
        type=f"{PROBLEM_BASE_URI}/{code}",
        title=_STATUS_TITLES.get(status_code, "Error"),
        status=status_code,
        detail=detail,
        code=code,
        request_id=_request_id(request),
        retry_after=retry_after,
        candidates=candidates,
    )
    headers: dict[str, str] = {}
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return JSONResponse(
        status_code=status_code,
        content=problem.model_dump(mode="json", exclude_none=True),
        media_type=PROBLEM_MEDIA_TYPE,
        headers=headers,
    )


def register_error_handlers(app: FastAPI) -> None:
    """Register exception handlers for ApiException, validation, rate limit,
    HTTP and unhandled exceptions.

    Args:
        app: the FastAPI application to register handlers on.
    """
    app.exception_handler(ApiException)(_handle_api_exception)
    app.exception_handler(RequestValidationError)(_handle_validation_error)
    app.exception_handler(RateLimitExceeded)(_handle_rate_limit)
    app.exception_handler(StarletteHTTPException)(_handle_http_exception)
    app.exception_handler(Exception)(_handle_unhandled)


async def _handle_api_exception(request: Request, exc: ApiException) -> JSONResponse:
    """Render an expected ApiException as problem+json."""
    return build_error_response(
        request, exc.status_code, exc.code, exc.detail, exc.retry_after, exc.candidates
    )


async def _handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Render a FastAPI request-validation failure as 422 problem+json."""
    return build_error_response(
        request,
        422,
        "validation_error",
        str(exc.errors()),
    )


async def _handle_rate_limit(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Render a slowapi rate-limit rejection as 429 problem+json."""
    return build_error_response(
        request,
        status.HTTP_429_TOO_MANY_REQUESTS,
        "rate_limited",
        str(exc.detail) if getattr(exc, "detail", None) else "Rate limit exceeded.",
        retry_after=60,
    )


async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Render a Starlette HTTPException as problem+json, 404 as not_found."""
    code: ErrorCode = "not_found" if exc.status_code == 404 else "internal"
    return build_error_response(request, exc.status_code, code, str(exc.detail))


async def _handle_unhandled(request: Request, exc: Exception) -> JSONResponse:
    """Log an unexpected exception and render a 500 problem+json."""
    # Never leak exception details; log the route template, never the
    # raw path or query string.
    route = request.scope.get("route")
    route_path = route.path if route is not None else request.url.path
    logger.exception(
        "Unhandled exception on %s %s",
        request.method,
        route_path,
        extra={"request_id": _request_id(request)},
    )
    return build_error_response(
        request, status.HTTP_500_INTERNAL_SERVER_ERROR, "internal", "Internal server error."
    )
