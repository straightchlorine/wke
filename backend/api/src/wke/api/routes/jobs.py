"""GET /api/v1/jobs/{job_id}: build job status."""

# Handlers are registered by the router decorator, never called by name; slowapi's
# limit() has no annotations.
# pyright: reportUnusedFunction=false, reportUnknownMemberType=false, reportUntypedFunctionDecorator=false

from __future__ import annotations

from fastapi import APIRouter, Path, Request, Response
from slowapi import Limiter

from wke.api.openapi_docs import error_response
from wke.api.ratelimit import JOB_POLL_RATE_LIMIT
from wke.core.errors import ApiException
from wke.core.models import Job
from wke.services.dossiers import DossierService

JOB_ID_PATTERN = r"^[0-9a-f]{16}$"


def retry_after_seconds(job: Job) -> str:
    """Write the Retry-After value of a queued or running job.

    Args:
        job: the job being polled or just queued.

    Returns:
        str: whole seconds of the job's poll_after_ms, at least 1.
    """
    return str(max(job.poll_after_ms // 1000, 1))


def build_router(limiter: Limiter) -> APIRouter:
    """Build the /api/v1/jobs/{job_id} router bound to the app's Limiter.

    Args:
        limiter: the app's slowapi Limiter.

    Returns:
        APIRouter: with the job-status route registered.
    """
    router = APIRouter(tags=["jobs"])

    @router.get(
        "/api/v1/jobs/{job_id}",
        response_model=Job,
        responses={
            "404": error_response("Unknown or expired job (not_found)"),
            "422": error_response("Validation error"),
            "429": error_response("Client rate limit hit; Retry-After set"),
        },
    )
    @limiter.limit(JOB_POLL_RATE_LIMIT)
    async def get_job(
        request: Request,
        response: Response,
        job_id: str = Path(..., pattern=JOB_ID_PATTERN),
    ) -> Job:
        service: DossierService = request.app.state.service
        job = await service.get_job(job_id)
        if job is None:
            raise ApiException(404, "not_found", detail=f"No job {job_id!r} (expired or unknown).")
        if job.status in ("queued", "running"):
            response.headers["Retry-After"] = retry_after_seconds(job)
        return job

    return router
