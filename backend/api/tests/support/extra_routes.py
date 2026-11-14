"""Mount one-off routes on a built app, ahead of the MCP catch-all."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI
from fastapi.routing import APIRoute


def add_test_route(app: FastAPI, path: str, endpoint: Callable[..., Any]) -> None:
    """Add a GET route that the app's router matches before the MCP mount.

    create_app() mounts the MCP catch-all Mount("/") as its last route, and
    Starlette's router stops at the first full match, so a route appended
    after it would never be reached.

    Args:
        app: an app built by create_app().
        path: the URL path of the new route.
        endpoint: the route's handler.
    """
    route = APIRoute(path, endpoint, methods=["GET"])
    app.router.routes.insert(len(app.router.routes) - 1, route)
