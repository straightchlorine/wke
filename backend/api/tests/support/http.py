"""HTTP assertions shared by route tests."""

from __future__ import annotations

import httpx
from httpx import AsyncClient


async def assert_conditional_get(
    client: AsyncClient, url: str, cache_control: str
) -> httpx.Response:
    """GET `url`, then replay it with If-None-Match and check the 304.

    Args:
        client: a client with the app lifespan running.
        url: the path to fetch twice.
        cache_control: the exact Cache-Control value both responses must carry.

    Returns:
        httpx.Response: the first (200) response.
    """
    first = await client.get(url)
    assert first.status_code == 200
    assert first.headers["cache-control"] == cache_control

    etag = first.headers["etag"]
    second = await client.get(url, headers={"If-None-Match": etag})
    assert second.status_code == 304
    assert second.headers["etag"] == etag
    assert second.headers["cache-control"] == cache_control
    assert second.content == b""

    return first
