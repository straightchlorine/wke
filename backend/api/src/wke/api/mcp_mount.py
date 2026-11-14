"""ASGI mount that serves the MCP SDK app behind the API's own rate limit and 404s."""

from __future__ import annotations

import limits
from fastapi import FastAPI, Response
from slowapi.util import get_remote_address
from starlette.requests import Request as ASGIRequest
from starlette.types import Receive, Scope, Send

from wke.api.constants import MCP_PATH, RATE_LIMIT_RETRY_AFTER_SECONDS
from wke.api.ratelimit import MCP_RATE_LIMIT
from wke.core.errors import ApiException

MCP_RATE_LIMIT_ITEM = limits.parse(MCP_RATE_LIMIT)


def is_mcp_path(path: str) -> bool:
    """Tell whether a request path belongs to the MCP endpoint.

    Args:
        path: the URL path of the request.

    Returns:
        bool: True for MCP_PATH itself and anything below it, not for a
        sibling that merely starts with the same letters, such as "/mcpx".
    """
    return path == MCP_PATH or path.startswith(MCP_PATH + "/")


class MCPDelegate:
    """ASGI app that delegates to app.state.mcp_asgi_app once lifespan builds it.

    Mounted at "/" after all API routes: FastAPI's router matches API routes
    first; Starlette's Mount sees only unclaimed requests. Raises ApiException
    for genuine 404s so every error body is an ApiError.
    Rate limiting enforced by hand (not via @limiter.limit decorator) before
    the MCP SDK sees any request.

    Args:
        app: the FastAPI application this delegate is mounted on.
    """

    def __init__(self, app: FastAPI) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Serve one ASGI event: 404 outside MCP_PATH, rate limit, then the MCP app.

        Args:
            scope: the ASGI connection scope.
            receive: the ASGI receive channel.
            send: the ASGI send channel.

        Raises:
            ApiException: 404 for a path outside MCP_PATH, 429 over the limit.
        """
        if scope["type"] == "http" and not is_mcp_path(scope["path"]):
            raise ApiException(404, "not_found", f"No such route: {scope['path']}")
        if scope["type"] == "http":
            limiter = getattr(self._app.state, "limiter", None)
            if limiter is not None:
                key = get_remote_address(ASGIRequest(scope, receive))
                if not limiter.limiter.hit(MCP_RATE_LIMIT_ITEM, key):
                    raise ApiException(
                        429,
                        "rate_limited",
                        detail="MCP rate limit exceeded. Wait a moment and retry.",
                        retry_after=RATE_LIMIT_RETRY_AFTER_SECONDS,
                    )
        mcp_asgi_app = getattr(self._app.state, "mcp_asgi_app", None)
        if mcp_asgi_app is None:
            response = Response(status_code=503, content="MCP not ready. Retry in a few seconds.")
            await response(scope, receive, send)
            return
        await mcp_asgi_app(scope, receive, send)
