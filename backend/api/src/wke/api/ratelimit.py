"""slowapi rate limiter, keyed by the real client IP, backed by Redis.

`get_remote_address` reads Starlette's `request.client.host`, which is
only spoofable by controlling the TCP connection itself; uvicorn is run
with `--proxy-headers --forwarded-allow-ips=<Traefik pod CIDR>` so that
address is Traefik's, not an attacker's X-Forwarded-For. slowapi's other
built-in key func, `get_ipaddr`, trusts a client-supplied
X-Forwarded-For header directly and is never used here.

Per-route limits: search 30/min, POST dossiers 6/min, GET reads 120/min,
job polling 600/min, live 12/min, MCP 30/min. Every decorated route counts
against its own bucket. The REST limits are applied as `@limiter.limit(...)`
decorators on the routes themselves and the MCP limit by hand in
`mcp_mount`; this module holds the limit strings and builds the shared
`Limiter` instance.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

SEARCH_RATE_LIMIT = "30/minute"
POST_DOSSIERS_RATE_LIMIT = "6/minute"
GET_READS_RATE_LIMIT = "120/minute"
JOB_POLL_RATE_LIMIT = "600/minute"
LIVE_RATE_LIMIT = "12/minute"
MCP_RATE_LIMIT = "30/minute"


def build_limiter(redis_url: str) -> Limiter:
    """Build the shared slowapi Limiter, backed by Redis.

    Args:
        redis_url: Redis connection URL (REDIS_URL setting).

    Returns:
        Limiter: configured with get_remote_address and Redis storage.
    """
    return Limiter(key_func=get_remote_address, storage_uri=redis_url)
