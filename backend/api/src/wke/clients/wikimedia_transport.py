"""Budget, lock, pace and retry transport shared by every Wikimedia call.

Unauthenticated, one call at a time across every process, shared 150/min budget.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, Literal

import httpx

from wke.clients.redis import RedisClient
from wke.core import keys
from wke.core.errors import ApiException
from wke.metrics import WIKIMEDIA_BUDGET_REJECTIONS_TOTAL, WIKIMEDIA_REQUESTS_TOTAL

logger = logging.getLogger(__name__)

PAGEVIEWS_API_URL = "https://wikimedia.org/api/rest_v1/metrics/pageviews/top"

# Per-request HTTP timeout of every Wikimedia call; the shared lock's TTL
# (keys.WM_LOCK_TTL_MS) covers UNAVAILABLE_MAX_ATTEMPTS of them.
WIKIMEDIA_TIMEOUT_SECONDS = 15.0

# A call slower than this sets wm:pace, so every process pauses before the next one.
SLOW_CALL_SECONDS = 1.0
LOCK_RETRY_INTERVAL_SECONDS = 0.05
INLINE_LOCK_DEADLINE_SECONDS = 3.0
WORKER_LOCK_DEADLINE_SECONDS = 10.0
DEFAULT_RATE_LIMIT_RETRY_AFTER_SECONDS = 5
MAX_RATE_LIMIT_RETRY_AFTER_SECONDS = 30
FULL_JITTER_MIN_SECONDS = 1.0
FULL_JITTER_MAX_SECONDS = 8.0

# Attempts at a call that keeps failing with a 5xx or a network error.
UNAVAILABLE_MAX_ATTEMPTS = 3
MAXLAG = 5

ClockFn = Callable[[], float]
SleepFn = Callable[[float], Awaitable[None]]
CallMode = Literal["inline", "worker"]


class WikimediaTransport:
    """Rate-limited, locked and retried HTTP calls to the Wikimedia APIs."""

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        redis: RedisClient,
        action_api_url: str,
        rest_api_url: str,
        budget_per_minute: int,
        clock: ClockFn = time.monotonic,
        wall_clock: ClockFn = time.time,
        sleep: SleepFn = asyncio.sleep,
    ) -> None:
        self._http = http_client
        self._redis = redis
        self._action_api_url = action_api_url.rstrip("/")
        self._rest_api_url = rest_api_url.rstrip("/")
        self._budget_per_minute = budget_per_minute
        self._clock = clock
        self._wall_clock = wall_clock
        self._sleep = sleep

    # --- budget / lock / pace / retries -----------------------------------

    async def _call(
        self,
        method: str,
        url: str,
        params: dict[str, str] | None,
        action_api: bool,
        mode: CallMode = "inline",
    ) -> httpx.Response:
        await self._wait_out_pace()

        token = await self._acquire_lock(mode)
        try:
            started = self._clock()
            response = await self._request_with_retries(method, url, params, action_api)
            elapsed = self._clock() - started
            if elapsed > SLOW_CALL_SECONDS:
                await self._redis.set(keys.WM_PACE, "1", ex=keys.WM_PACE_TTL_SECONDS)
            return response
        finally:
            await self._release_lock(token)

    async def _check_budget(self) -> None:
        epoch_minute = int(self._wall_clock() // 60)
        key = keys.wm_budget(epoch_minute)
        count = await self._redis.incr(key)
        if count == 1:
            await self._redis.expire(key, keys.WM_BUDGET_TTL_SECONDS)
        if count is not None and count > self._budget_per_minute:
            WIKIMEDIA_BUDGET_REJECTIONS_TOTAL.inc()
            raise ApiException(
                503,
                "upstream_budget",
                detail="Shared Wikimedia call budget exhausted for this minute.",
                retry_after=60,
            )

    async def _acquire_lock(self, mode: CallMode) -> str:
        # set the deadline, depending on the mode
        # inline - calls on behalf of active user requests,
        # worker mode refers to background processes
        deadline_seconds = (
            INLINE_LOCK_DEADLINE_SECONDS if mode == "inline" else WORKER_LOCK_DEADLINE_SECONDS
        )
        # for the lock
        token = uuid.uuid4().hex

        started = self._clock()
        while True:
            # store the lock on redis and if available - return
            acquired = await self._redis.set(keys.WM_LOCK, token, px=keys.WM_LOCK_TTL_MS, nx=True)
            if acquired:
                return token

            # wait until the deadline passess and raise
            if self._clock() - started >= deadline_seconds:
                if mode == "inline":
                    raise ApiException(
                        503,
                        "upstream_budget",
                        detail="Timed out waiting for the shared Wikimedia lock.",
                        retry_after=2,
                    )
                raise ApiException(
                    503,
                    "upstream_unavailable",
                    detail="Timed out waiting for the shared Wikimedia lock.",
                    retry_after=5,
                )
            await self._sleep(LOCK_RETRY_INTERVAL_SECONDS)

    async def _release_lock(self, token: str) -> None:
        # remove only if the lock still holds given token, so that expiry and
        # reacquire by another caller is not undone by a release running late
        await self._redis.delete_if_equals(keys.WM_LOCK, token)

    async def _wait_out_pace(self) -> None:
        # wait out the pace (in case wikimedia seems to be under load)
        # before the lock is taken and not after, so that held duration
        # covers only the request itself
        ttl = await self._redis.ttl(keys.WM_PACE)
        if ttl and ttl > 0:
            await self._sleep(float(ttl))

    async def _request_with_retries(
        self, method: str, url: str, params: dict[str, str] | None, action_api: bool
    ) -> httpx.Response:

        # build the payload
        call_params = dict(params) if params else None
        if action_api and call_params is not None:
            call_params["maxlag"] = str(MAXLAG)

        rate_limited_retried = False
        attempt = 0
        while True:
            # every HTTP request counts against the shared budget, that includes
            # retries, so a series of retries cannot bypass the cap
            await self._check_budget()

            op = self._op_for_call(url, action_api)
            call_started = self._clock()
            try:
                response = await self._http.request(method, url, params=call_params)
            except httpx.RequestError as exc:
                # a timeout, a refused or dropped connection, a broken body:
                # retried like a 5xx, never escapes as a raw httpx error
                WIKIMEDIA_REQUESTS_TOTAL.labels(op=op, status="network_error").inc()
                attempt = await self._back_off_or_give_up(attempt, exc.__class__.__name__)
                continue
            duration_ms = (self._clock() - call_started) * 1000

            logger.info(
                "Wikimedia outbound call: %s %s status=%d duration_ms=%.0f",
                method,
                url,
                response.status_code,
                duration_ms,
            )

            # bump correct label for this request (depends on wikimedia endpoint)
            WIKIMEDIA_REQUESTS_TOTAL.labels(op=op, status=str(response.status_code)).inc()

            rate_limit_hit = self._is_rate_limited(response, action_api)
            if rate_limit_hit and not rate_limited_retried:
                retry_after = self._retry_after_seconds(response)
                logger.warning("Wikimedia rate limit hit; retrying once in %ss", retry_after)
                await self._sleep(float(retry_after))
                rate_limited_retried = True
                continue
            if rate_limit_hit and rate_limited_retried:
                # after two requests - raise
                retry_after = self._retry_after_seconds(response)
                raise ApiException(
                    503,
                    "upstream_rate_limited",
                    detail="Wikimedia rate-limited this client twice in a row.",
                    retry_after=retry_after,
                )
            if response.status_code >= 500:
                attempt = await self._back_off_or_give_up(attempt, f"HTTP {response.status_code}")
                continue
            if action_api:
                self._raise_on_bad_action_api_response(response)
            return response

    async def _back_off_or_give_up(self, attempt: int, failure: str) -> int:
        """Wait before the next attempt at a failed call, or give up on it.

        Args:
            attempt: failed attempts so far, not counting this one.
            failure: what went wrong, for the log and the error detail
                (e.g. "HTTP 502", "ConnectTimeout").

        Returns:
            int: failed attempts including this one, after the wait.

        Raises:
            ApiException: upstream_unavailable once UNAVAILABLE_MAX_ATTEMPTS
                attempts have failed.
        """
        attempt += 1
        if attempt >= UNAVAILABLE_MAX_ATTEMPTS:
            raise ApiException(
                503,
                "upstream_unavailable",
                detail=f"Wikimedia failed {attempt} times; last: {failure}.",
                retry_after=5,
            )
        delay = random.uniform(FULL_JITTER_MIN_SECONDS, FULL_JITTER_MAX_SECONDS)
        logger.warning(
            "Wikimedia %s; retry %d/%d in %.2fs", failure, attempt, UNAVAILABLE_MAX_ATTEMPTS, delay
        )
        await self._sleep(delay)
        return attempt

    def _json_object(self, response: httpx.Response) -> dict[str, Any]:
        """Read the JSON object a REST call (Wikifeeds, Pageviews) answered with.

        Args:
            response: the response of a REST call that returns JSON.

        Returns:
            dict[str, Any]: the decoded body.

        Raises:
            ApiException: upstream_unavailable on an error status, a body that
                is not JSON, or JSON that is not an object.
        """
        if response.status_code >= 400:
            raise ApiException(
                503,
                "upstream_unavailable",
                detail=f"Wikimedia returned HTTP {response.status_code}.",
            )
        try:
            body = response.json()
        except ValueError:
            body = None
        if not isinstance(body, dict):
            raise ApiException(
                503,
                "upstream_unavailable",
                detail=f"Wikimedia returned no JSON object (HTTP {response.status_code}).",
            )
        return body

    def _raise_on_bad_action_api_response(self, response: httpx.Response) -> None:
        """Reject an Action API response that is not usable JSON.

        A caller like `resolve()`/`morelike()`/`search()` calls
        `response.json()` and treats an empty-looking body as a real
        "not found"/empty result, which would then get cached as such.
        Neither a non-JSON body (e.g. an IP-ban HTML page) nor a JSON
        `error` object is a real answer, so both are raised here instead
        of reaching that caller.

        Args:
            response: the response `_request_with_retries` is about to
                return for an `action_api=True` call.

        Raises:
            ApiException: upstream_unavailable if the body does not
                decode as JSON, or decodes with a top-level `error` key.
        """
        try:
            body = response.json()
        except ValueError:
            raise ApiException(
                503,
                "upstream_unavailable",
                detail=f"Wikimedia returned a non-JSON body (HTTP {response.status_code}).",
            ) from None
        if isinstance(body, dict) and isinstance(body.get("error"), dict):
            raise ApiException(
                503,
                "upstream_unavailable",
                detail=f"Wikimedia Action API returned an error: {body['error']!r}.",
            )
        if response.status_code >= 400:
            raise ApiException(
                503,
                "upstream_unavailable",
                detail=f"Wikimedia Action API returned HTTP {response.status_code}.",
            )

    def _op_for_call(self, url: str, action_api: bool) -> str:
        """Classify one outbound call for the `op` metric label.

        Args:
            url: the request URL passed to `_call`.
            action_api: True for `action=query` calls to the Action API.

        Returns:
            str: "action" for the Action API, "rest" for Parsoid REST
            (revision_html), "pageviews" for AQS Pageviews, "wikifeeds"
            for everything else (Wikifeeds mostread).
        """
        if action_api:
            return "action"
        if url.startswith(self._rest_api_url):
            return "rest"
        if url.startswith(PAGEVIEWS_API_URL):
            return "pageviews"
        return "wikifeeds"

    def _is_rate_limited(self, response: httpx.Response, action_api: bool) -> bool:
        if response.status_code == 429:
            return True
        if action_api and response.status_code == 200:
            content_type = response.headers.get("content-type", "")
            if "json" in content_type:
                try:
                    body = response.json()
                except ValueError:
                    return False
                error = body.get("error") if isinstance(body, dict) else None
                if isinstance(error, dict) and error.get("code") in ("maxlag", "ratelimited"):
                    return True
        return False

    def _retry_after_seconds(self, response: httpx.Response) -> int:
        value = response.headers.get("retry-after")
        if value is None:
            return DEFAULT_RATE_LIMIT_RETRY_AFTER_SECONDS
        try:
            seconds = int(value)
        except ValueError:
            return DEFAULT_RATE_LIMIT_RETRY_AFTER_SECONDS
        # restricted so an upstream header cannot hold the lock past WM_LOCK_TTL_MS
        return min(seconds, MAX_RATE_LIMIT_RETRY_AFTER_SECONDS)
