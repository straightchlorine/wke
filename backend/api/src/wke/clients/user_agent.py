"""The User-Agent every outbound Wikimedia request identifies WKE with."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

import httpx


def _package_version() -> str:
    try:
        return version("wke-api")
    except PackageNotFoundError:
        return "0.1.0"


def build_user_agent() -> str:
    """Build the exact Wikimedia User-Agent string, from settings and httpx.

    Returns:
        str: `wke/<package version> (https://wke.piotrkrzysztof.dev;
        <WKE_CONTACT_EMAIL>) httpx/<httpx version>`.
    """
    from wke.settings import settings

    return (
        f"wke/{_package_version()} "
        f"(https://wke.piotrkrzysztof.dev; {settings.wke_contact_email}) "
        f"httpx/{httpx.__version__}"
    )
