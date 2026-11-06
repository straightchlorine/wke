"""`python -m wke.api`: run wke-api under uvicorn.

Uses `--proxy-headers` so `request.client` reflects the real client IP
forwarded by Traefik (this is what makes slowapi's `get_remote_address`
unspoofable), restricted to `POD_CIDR` via `--forwarded-allow-ips` so only
the in-cluster proxy is trusted.
"""

from __future__ import annotations

import uvicorn

from wke.logging_setup import configure_logging
from wke.settings import settings


def main() -> None:
    """Run uvicorn on the wke.api.app:create_app factory, trusting proxy headers from POD_CIDR."""
    configure_logging(settings.log_level, settings.log_format)
    uvicorn.run(
        "wke.api.app:create_app",
        factory=True,
        host="0.0.0.0",
        port=settings.wke_port,
        proxy_headers=True,
        forwarded_allow_ips=settings.pod_cidr,
        log_level=settings.log_level.lower(),
        access_log=False,
        log_config=None,
    )


if __name__ == "__main__":
    main()
