"""A transient 4xx/non-JSON Wikimedia response must never be cached as data.

wke.clients.wikimedia_transport._raise_on_bad_action_api_response is what stops a
403 HTML error page or a JSON `error` body from being treated as an empty
or "not found" result; these tests confirm the failure actually reaches
DossierService as an ApiException before anything is written to
`wm:resolve:*`.
"""

from __future__ import annotations

import httpx
import pytest

from tests.support.constants import FIXTURE_TITLE
from tests.support.services import make_service
from wke.clients.redis import RedisClient
from wke.core import keys
from wke.core.errors import ApiException
from wke.core.titles import normalize_title


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(403, text="<html>blocked</html>"),
        httpx.Response(400, json={"error": {"code": "badtitle"}}),
    ],
    ids=["403-html", "400-json-error"],
)
async def test_bad_resolve_response_is_a_503_and_is_not_cached(
    redis_client: RedisClient, response: httpx.Response
) -> None:
    service = make_service(redis_client, lambda request: response)

    with pytest.raises(ApiException) as exc_info:
        await service.request_build(FIXTURE_TITLE)

    assert exc_info.value.status_code == 503
    assert await redis_client.get(keys.wm_resolve(normalize_title(FIXTURE_TITLE))) is None
