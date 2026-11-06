"""Liveness, readiness and Prometheus scrape routes."""

# Handlers are registered by the router decorator, never called by name.
# pyright: reportUnusedFunction=false

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from wke.api.probes import sample_redis_gauges


def build_router() -> APIRouter:
    """Build the router of /healthz, /readyz and /metrics.

    Returns:
        APIRouter: with the three internal routes registered.
    """
    router = APIRouter()

    @router.get("/healthz", tags=["internal"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/readyz", tags=["internal"])
    async def readyz(request: Request) -> JSONResponse:
        if getattr(request.app.state, "ready", False):
            return JSONResponse(status_code=200, content={"status": "ready"})
        return JSONResponse(status_code=503, content={"status": "starting"})

    @router.get("/metrics", tags=["internal"])
    async def metrics(request: Request) -> Response:
        await sample_redis_gauges(request.app)
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return router
