"""Request id, security headers, access log and request metrics for every request."""

# The middleware function is registered by decorator and never called by name.
# pyright: reportUnusedFunction=false

from __future__ import annotations

import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from wke.api.constants import MCP_PATH
from wke.api.error_handlers import build_error_response
from wke.api.mcp_mount import is_mcp_path
from wke.logging_setup import request_id_var
from wke.metrics import HTTP_REQUESTS_SECONDS, HTTP_REQUESTS_TOTAL

logger = logging.getLogger(__name__)

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9-]{8,64}$")
NOINDEX_PATH = re.compile(r"^/(api|mcp)(/|$)")
QUIET_ROUTE_PATHS = frozenset({"/healthz", "/readyz", "/metrics", "/api/v1/jobs/{job_id}"})


def route_label(request: Request) -> str:
    """Name the matched route for metric labels and access logs.

    Args:
        request: the current request.

    Returns:
        str: the route template, MCP_PATH for the MCP mount, else
        "unmatched" (never the raw path, which is unbounded label
        cardinality and may carry a title).
    """
    route = request.scope.get("route")
    path = getattr(route, "path", "")
    if path:
        return path
    if is_mcp_path(request.url.path):
        return MCP_PATH
    return "unmatched"


def install_request_middleware(app: FastAPI) -> None:
    """Register the per-request middleware on the application.

    Args:
        app: the FastAPI application.
    """

    @app.middleware("http")
    async def request_id_and_security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get("x-request-id")
        request_id = (
            incoming if incoming and REQUEST_ID_PATTERN.match(incoming) else str(uuid.uuid4())
        )
        request.state.request_id = request_id
        request_id_var.set(request_id)

        started = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            # Belt-and-suspenders: registered handlers already turn route
            # exceptions into responses, but this stops anything that
            # escapes them from reaching ServerErrorMiddleware and printing
            # a second traceback.
            route_path = route_label(request)
            logger.exception(
                "Unhandled exception on %s %s",
                request.method,
                route_path,
                extra={"request_id": request_id},
            )
            response = build_error_response(request, 500, "internal", "Internal server error.")
        duration_ms = (time.monotonic() - started) * 1000

        response.headers["X-Request-ID"] = request_id
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "()"
        # JSON and Markdown renditions must not compete with the page in
        # search results. /llms.txt and /sitemap.xml stay indexable.
        if NOINDEX_PATH.match(request.url.path):
            response.headers["X-Robots-Tag"] = "noindex"

        route_path = route_label(request)
        status_class = f"{response.status_code // 100}xx"
        HTTP_REQUESTS_TOTAL.labels(
            route=route_path, method=request.method, status_class=status_class
        ).inc()
        HTTP_REQUESTS_SECONDS.labels(
            route=route_path, method=request.method, status_class=status_class
        ).observe(duration_ms / 1000)
        level = logging.WARNING if response.status_code >= 500 else logging.INFO
        if route_path in QUIET_ROUTE_PATHS:
            level = logging.DEBUG
        # Route template only, never the raw path or query string, for privacy.
        logger.log(
            level,
            "%s %s status=%d duration_ms=%.0f",
            request.method,
            route_path,
            response.status_code,
            duration_ms,
            extra={"request_id": request_id},
        )
        return response
