"""FastAPI application for wke-ml: embeddings, clustering, summarization.

Endpoints:
  POST /v1/analyze    -- MiniLM embed + cluster + relevance + related edges
  POST /v1/summarize  -- distilbart-cnn-6-6 abstractive summary
  POST /v1/rate       -- local model's 0 to 3 rating of up to 8 passages (off without a model file)
  GET  /healthz       -- weights resident
  GET  /readyz        -- warm-up inference done for both models
  GET  /metrics       -- prometheus text exposition

One inference slot at a time (asyncio.Semaphore(1), work run via
run_in_threadpool), a bounded wait queue (settings.queue_max_wait), 503
+ Retry-After once the queue is full, and a disconnect/deadline check
before a queued job is allowed to start. /v1/rate has a gate of its own,
so an analyze never waits behind a rating call; the two may run at once
and share the CPU. There is no per-client rate limiting: access control
is the cluster NetworkPolicy.
"""

# Route handlers and middleware are registered by their decorators, never called by name.
# pyright: reportUnusedFunction=false

from __future__ import annotations

import asyncio
import logging
import re
import sys
import threading
import time
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from functools import partial
from typing import Protocol

from fastapi import FastAPI, Header, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from wke_ml.analyze import AnalyzeRequest, AnalyzeResponse
from wke_ml.analyze import analyze as run_analyze
from wke_ml.backends import build_embedder, build_summarizer
from wke_ml.logging_setup import configure_logging, request_id_var
from wke_ml.metrics import INFER_SECONDS, INFLIGHT, SHED_TOTAL
from wke_ml.rating import (
    PROMPT_SHA256,
    PromptTooLong,
    Rater,
    RateRequest,
    RateResponse,
    RatingAbandoned,
    RatingUnavailable,
    build_rater,
)
from wke_ml.settings import Settings, get_settings
from wke_ml.summarize import SummarizeRequest, SummarizeResponse
from wke_ml.summarize import summarize as run_summarize

logger = logging.getLogger(__name__)


RETRY_AFTER_SECONDS = 2
QUIET_PATHS = frozenset({"/healthz", "/readyz", "/metrics"})
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")

# Once a job has acquired the slot, it is not worth starting if less than
# this much of the caller's deadline remains -- the caller's own timeout
# (deadline_ms/1000 in wke-api's ml client) is about to fire anyway, so
# running the job would just hold the single slot for a response nobody
# reads.
MIN_START_SECONDS = 0.5

# How often a running job that can be abandoned asks whether its client is still there.
DISCONNECT_POLL_SECONDS = 0.5


class ShedError(Exception):
    """Base for the reasons an inference job can be shed before it runs."""


class QueueFullError(ShedError):
    """The bounded wait queue already holds the maximum number of jobs."""


class DeadlineExceededError(ShedError):
    """The job could not start before the caller's X-Deadline-Ms budget."""


class ClientDisconnectedError(ShedError):
    """The client disconnected while the job was waiting for the slot."""


class DisconnectCheck(Protocol):
    """The part of a Request the gate polls once a job is next in line."""

    async def is_disconnected(self) -> bool:
        """Report whether the client has gone away.

        Returns:
            bool: True once the client disconnected.
        """


class InferenceGate:
    """Serializes inference to one job at a time behind a bounded wait queue."""

    def __init__(self, max_queue: int) -> None:
        self._semaphore = asyncio.Semaphore(1)
        self._max_queue = max_queue
        self._waiting = 0
        self._running_since: float | None = None

    def running_seconds(self) -> float:
        """Report how long the current job has held the inference slot.

        Returns:
            float: seconds since the running job started, 0.0 when the slot is free.
        """
        if self._running_since is None:
            return 0.0
        return time.monotonic() - self._running_since

    async def run[T](
        self,
        request: DisconnectCheck,
        deadline_ms: float | None,
        op: str,
        fn: Callable[[], T],
        on_abandon: Callable[[], None] | None = None,
    ) -> tuple[T, float]:
        """Run fn under the single inference slot, subject to shedding rules.

        Args:
            request: the inbound ASGI request, polled for disconnect once
                this job is next in line to run.
            deadline_ms: remaining budget from the X-Deadline-Ms header, or
                None if the caller set no deadline.
            op: metric label for wke_ml_infer_seconds.
            fn: zero-arg callable run in the threadpool while holding the slot.
            on_abandon: called once when the client disconnects or the request is cancelled
                while fn runs, so fn can stop early; the slot stays held until fn returns,
                because its thread cannot be killed.

        Returns:
            tuple[T, float]: fn's return value and the seconds it held the slot.

        Raises:
            QueueFullError: the wait queue already holds max_queue jobs.
            DeadlineExceededError: the job could not start before the deadline,
                or too little of the deadline remained once the slot was won.
            ClientDisconnectedError: the client disconnected before the job started.
        """
        if self._waiting >= self._max_queue:
            SHED_TOTAL.labels(reason="queue_full").inc()
            raise QueueFullError()
        self._waiting += 1

        # Counted as "waiting" only until the slot is won or shedding
        # happens first; the running job itself does not occupy a queue
        # slot, so max_queue holds regardless of whether a job is in flight.
        counted = True
        acquired = False
        try:
            deadline_at = (
                time.monotonic() + deadline_ms / 1000.0 if deadline_ms is not None else None
            )
            if deadline_at is not None and deadline_at <= time.monotonic():
                SHED_TOTAL.labels(reason="deadline").inc()
                raise DeadlineExceededError()

            try:
                if deadline_at is not None:
                    timeout = max(0.0, deadline_at - time.monotonic())
                    await asyncio.wait_for(self._semaphore.acquire(), timeout=timeout)
                else:
                    await self._semaphore.acquire()
                acquired = True
            except TimeoutError as exc:
                SHED_TOTAL.labels(reason="deadline").inc()
                raise DeadlineExceededError() from exc
            finally:
                self._waiting -= 1
                counted = False

            if deadline_at is not None and deadline_at - time.monotonic() < MIN_START_SECONDS:
                SHED_TOTAL.labels(reason="deadline").inc()
                raise DeadlineExceededError()

            if await request.is_disconnected():
                SHED_TOTAL.labels(reason="disconnected").inc()
                raise ClientDisconnectedError()

            INFLIGHT.inc()
            start = time.monotonic()
            self._running_since = start
            try:
                if on_abandon is None:
                    result = await run_in_threadpool(fn)
                else:
                    result = await self._run_abandonable(request, fn, on_abandon)
            finally:
                elapsed = time.monotonic() - start
                self._running_since = None
                INFLIGHT.dec()
                INFER_SECONDS.labels(op=op).observe(elapsed)
            return result, elapsed
        finally:
            if acquired:
                self._semaphore.release()
            if counted:
                self._waiting -= 1

    async def _run_abandonable[T](
        self, request: DisconnectCheck, fn: Callable[[], T], on_abandon: Callable[[], None]
    ) -> T:
        """Run fn in the threadpool, telling on_abandon when the client goes.

        Returns:
            T: fn's return value.
        """
        work = asyncio.ensure_future(run_in_threadpool(fn))
        watcher = asyncio.create_task(_watch_disconnect(request, on_abandon))
        try:
            return await asyncio.shield(work)
        except asyncio.CancelledError:
            on_abandon()
            await asyncio.wait({work})  # the slot is held until the thread has returned
            if not work.cancelled():
                work.exception()  # marks it retrieved
            raise
        finally:
            watcher.cancel()


async def _watch_disconnect(request: DisconnectCheck, on_abandon: Callable[[], None]) -> None:
    """Call on_abandon once the client has gone away."""
    while not await request.is_disconnected():
        await asyncio.sleep(DISCONNECT_POLL_SECONDS)
    on_abandon()


def _parse_deadline(header_value: str | None) -> float | None:
    """Parse the X-Deadline-Ms header into a float, ignoring bad input.

    Args:
        header_value: raw header value, or None if absent.

    Returns:
        float | None: the remaining milliseconds, or None if absent or invalid.
    """
    if header_value is None:
        return None
    try:
        return float(header_value)
    except ValueError:
        return None


def _request_id(request: Request) -> str:
    """Validate the caller's X-Request-ID, or mint a fresh one.

    Args:
        request: the inbound request.

    Returns:
        str: the header value if it matches ^[A-Za-z0-9-]{8,64}$, else a uuid4 hex.
    """
    header_value = request.headers.get("X-Request-ID")
    if header_value and REQUEST_ID_RE.match(header_value):
        return header_value
    return uuid.uuid4().hex


def _shed_response(request: Request) -> JSONResponse:
    """Build the 503 + Retry-After error response for a shed job.

    Args:
        request: the inbound request, used for X-Request-ID echo.

    Returns:
        JSONResponse: a 503 with an ApiError-shaped body and a Retry-After header.
    """
    body = {
        "type": "about:blank",
        "title": "wke-ml is busy",
        "status": 503,
        "detail": "No inference slot became available in time.",
        "code": "queue_full",
        "request_id": request.state.request_id,
        "retry_after": RETRY_AFTER_SECONDS,
    }
    return JSONResponse(
        status_code=503,
        content=body,
        media_type="application/problem+json",
        headers={"Retry-After": str(RETRY_AFTER_SECONDS)},
    )


def _problem(request: Request, status: int, code: str, title: str, detail: str) -> JSONResponse:
    """Build an error response without Retry-After.

    Args:
        request: the inbound request, used for X-Request-ID echo.
        status: the HTTP status.
        code: the machine-readable error code.
        title: short summary of the problem.
        detail: what went wrong.

    Returns:
        JSONResponse: an ApiError-shaped problem body.
    """
    body = {
        "type": "about:blank",
        "title": title,
        "status": status,
        "detail": detail,
        "code": code,
        "request_id": request.state.request_id,
    }
    return JSONResponse(status_code=status, content=body, media_type="application/problem+json")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Load model weights, warm up both backends, then serve.

    Exits the process with status 1 if weight loading or warm-up inference
    fails, so a broken image never reports healthy under k8s.

    Args:
        app: the FastAPI app being started.

    Yields:
        None: once weights are resident and warm-up has completed.
    """
    settings: Settings = app.state.settings
    try:
        if settings.backend == "torch":
            import torch

            torch.set_num_threads(settings.omp_num_threads)

        embedder = app.state.embedder_factory(settings)
        summarizer = app.state.summarizer_factory(settings)
        app.state.embedder = embedder
        app.state.summarizer = summarizer
        app.state.rater = app.state.rater_factory(settings)  # loads on its first call
        logger.info("wke-ml weights resident")

        await run_in_threadpool(embedder.embed, ["warm-up"])
        warmup_request = SummarizeRequest(text="Warm up text for the summarization pipeline.")
        await run_in_threadpool(
            summarizer.summarize,
            warmup_request.text,
            num_beams=warmup_request.num_beams,
            min_length=warmup_request.min_length,
            max_length=warmup_request.max_length,
        )
        logger.info("wke-ml ready")
    except Exception:
        logger.exception("wke-ml warm-up failed; exiting")
        sys.exit(1)
    yield


class RequestIdMiddleware:
    """Attach a validated request id to the request state and echo it as X-Request-ID.

    Also logs one access line per request, once the response starts. It is a plain ASGI
    middleware on purpose: a BaseHTTPMiddleware hands the app another receive channel, under
    which Request.is_disconnected() stays False on a real server and an abandoned call is never
    seen.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        request_id = _request_id(request)
        request.state.request_id = request_id
        request_id_var.set(request_id)
        started = time.monotonic()

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
                # Fixed ml paths only (no titles or query strings), so the caller's
                # id is searchable in wke-ml's logs.
                logger.log(
                    logging.DEBUG if request.url.path in QUIET_PATHS else logging.INFO,
                    "%s %s status=%d duration_ms=%.0f",
                    request.method,
                    request.url.path,
                    message["status"],
                    (time.monotonic() - started) * 1000,
                )
            await send(message)

        await self.app(scope, receive, send_with_id)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the wke-ml FastAPI app.

    Args:
        settings: explicit Settings to use instead of get_settings(); tests
            pass a Settings(backend="stub", ...) here so no torch import
            or weight download happens.

    Returns:
        FastAPI: the constructed, not-yet-started app.
    """
    app = FastAPI(title="wke-ml", lifespan=lifespan)
    app.state.settings = settings or get_settings()
    configure_logging(app.state.settings.log_level, app.state.settings.log_format)
    app.state.embedder_factory = build_embedder
    app.state.summarizer_factory = build_summarizer
    app.state.rater_factory = build_rater
    app.state.gate = InferenceGate(app.state.settings.queue_max_wait)
    app.state.rate_gate = InferenceGate(app.state.settings.queue_max_wait)

    @app.exception_handler(ShedError)
    async def handle_shed_error(request: Request, _exc: ShedError) -> JSONResponse:
        """Turn any shed reason into the shared 503 error response.

        Args:
            request: the inbound request, used for X-Request-ID echo.
            _exc: the raised ShedError subclass; only its type is used for
                routing, not its content.

        Returns:
            JSONResponse: the 503 + Retry-After error response.
        """
        return _shed_response(request)

    @app.exception_handler(RatingUnavailable)
    async def handle_rating_unavailable(request: Request, exc: RatingUnavailable) -> JSONResponse:
        """Answer 503 rating_unavailable when the rating model is off, missing or failed to load.

        Args:
            request: the inbound request, used for X-Request-ID echo.
            exc: the raised error; its message becomes the detail.

        Returns:
            JSONResponse: a 503 without Retry-After.
        """
        return _problem(request, 503, "rating_unavailable", "Rating is unavailable", str(exc))

    @app.exception_handler(PromptTooLong)
    async def handle_prompt_too_long(request: Request, exc: PromptTooLong) -> JSONResponse:
        """Answer 422 prompt_too_long when one passage's prompt exceeds the context.

        Args:
            request: the inbound request, used for X-Request-ID echo.
            exc: the raised error; its message becomes the detail.

        Returns:
            JSONResponse: a 422.
        """
        return _problem(request, 422, "prompt_too_long", "Prompt is too long", str(exc))

    app.add_middleware(RequestIdMiddleware)

    @app.post("/v1/analyze")
    async def analyze(
        request: Request,
        body: AnalyzeRequest,
        x_deadline_ms: str | None = Header(default=None, alias="X-Deadline-Ms"),
    ) -> AnalyzeResponse:
        """Embed, cluster and score related-lead edges, under the inference gate.

        Args:
            request: the inbound request, polled for disconnect and deadline.
            body: lead, chunks and related leads to analyze.
            x_deadline_ms: remaining caller budget in milliseconds, if set.

        Returns:
            AnalyzeResponse: the analysis result; a shed job answers 503 instead.
        """
        settings_: Settings = request.app.state.settings
        gate: InferenceGate = request.app.state.gate
        embedder = request.app.state.embedder
        result, elapsed = await gate.run(
            request,
            _parse_deadline(x_deadline_ms),
            "analyze",
            lambda: run_analyze(body, embedder, settings_),
        )
        result.infer_seconds = elapsed
        return result

    @app.post("/v1/summarize")
    async def summarize(
        request: Request,
        body: SummarizeRequest,
        x_deadline_ms: str | None = Header(default=None, alias="X-Deadline-Ms"),
    ) -> SummarizeResponse:
        """Summarize text with distilbart-cnn-6-6, under the inference gate.

        Args:
            request: the inbound request, polled for disconnect and deadline.
            body: text to summarize and generation parameters.
            x_deadline_ms: remaining caller budget in milliseconds, if set.

        Returns:
            SummarizeResponse: the machine summary; a shed job answers 503 instead.
        """
        settings_: Settings = request.app.state.settings
        gate: InferenceGate = request.app.state.gate
        summarizer = request.app.state.summarizer
        result, elapsed = await gate.run(
            request,
            _parse_deadline(x_deadline_ms),
            "summarize",
            lambda: run_summarize(body, summarizer, settings_),
        )
        result.infer_seconds = elapsed
        return result

    @app.post("/v1/rate")
    async def rate(
        request: Request,
        body: RateRequest,
        x_deadline_ms: str | None = Header(default=None, alias="X-Deadline-Ms"),
    ) -> RateResponse:
        """Rate each passage of one article, one hold of the rating gate per passage.

        The rating gate is not the one analyze and summarize use, so those never wait behind a
        rating call. When the client goes away the running passage stops at the next point the
        model can be left and no further passage starts.

        Args:
            request: the inbound request, polled for disconnect and deadline.
            body: article title and lead, and 1 to 8 passages.
            x_deadline_ms: remaining caller budget in milliseconds, if set; it applies to
                the wait for the slot of each passage.

        Returns:
            RateResponse: score per passage id (null when no digit came), the ids rated by
            the generated digit; a shed job answers 503 instead.

        Raises:
            ClientDisconnectedError: the client went away while a passage was being rated.
        """
        gate: InferenceGate = request.app.state.rate_gate
        rater: Rater = request.app.state.rater
        deadline = _parse_deadline(x_deadline_ms)
        scores: dict[str, float | None] = {}
        fallback_ids: list[str] = []
        seconds = 0.0
        stop = threading.Event()
        try:
            for passage in body.passages:
                rating, elapsed = await gate.run(
                    request,
                    deadline,
                    "rate",
                    partial(rater.rate, body.title, body.lead, passage.text, stop.is_set),
                    on_abandon=stop.set,
                )
                scores[passage.id] = rating.score
                if rating.fallback:
                    fallback_ids.append(passage.id)
                seconds += elapsed
        except RatingAbandoned:
            SHED_TOTAL.labels(reason="disconnected").inc()
            raise ClientDisconnectedError() from None
        finally:
            stop.set()
        return RateResponse(
            model=rater.model_file,
            prompt_sha256=PROMPT_SHA256,
            scores=scores,
            fallback_ids=fallback_ids,
            infer_seconds=seconds,
        )

    @app.get("/healthz")
    async def healthz() -> JSONResponse:
        """Report that model weights are resident and inference is not wedged.

        Uvicorn does not bind the socket until lifespan startup completes
        (weights loaded, warm-up run) or exits the process, so weights are
        always resident once the endpoint is reachable; the k8s startupProbe
        must cover the loading window itself. Beyond that, liveness fails
        when one job has held an inference slot (either gate) longer than
        stuck_after_seconds. A thread wedged inside torch is the only case
        this catches; a slow but progressing job is not distinguished from
        a hung one below that threshold.

        Returns:
            JSONResponse: 200 with status "ok", or 503 with status "stuck" when
            the running job exceeds stuck_after_seconds.
        """
        running = max(app.state.gate.running_seconds(), app.state.rate_gate.running_seconds())
        if running > app.state.settings.stuck_after_seconds:
            return JSONResponse(status_code=503, content={"status": "stuck"})
        return JSONResponse(status_code=200, content={"status": "ok"})

    @app.get("/readyz")
    async def readyz() -> JSONResponse:
        """Report that warm-up inference has completed for both models.

        See healthz: reachable only after warm-up succeeds or the process
        exits, so this is always true once the endpoint is reachable.

        Returns:
            JSONResponse: 200, with status "ready".
        """
        return JSONResponse(status_code=200, content={"status": "ready"})

    @app.get("/metrics")
    async def metrics() -> Response:
        """Expose prometheus text-format metrics.

        Returns:
            Response: the current wke_ml_infer_seconds, wke_ml_inflight and
            wke_ml_shed_total series in prometheus exposition format.
        """
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
