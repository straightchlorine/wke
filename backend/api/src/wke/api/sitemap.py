"""Hand-rolled /sitemap.xml, cached 5 min in-process.

Lists the static pages plus one URL per built dossier, rooted at the same
public base URL as /llms.txt.

A dossier is listed when `DossierService.list_dossiers` returns it, which needs
both its pointer and the dossier stored under the current pipeline version. A
page whose entry in the `built` index has lost either (expired, or built under
an older pipeline version and not yet rebuilt) is left out, as GET answers 404
for it too. The body is cached for CACHE_TTL_SECONDS and refreshed at once
when a build bumps the view generation.
"""

from __future__ import annotations

import time
from datetime import UTC
from urllib.parse import quote
from xml.sax.saxutils import escape

from wke.core.viewcache import current_generation
from wke.services.dossiers import DossierService

CACHE_TTL_SECONDS = 300
MAX_ENTRIES = 50000
PAGE_SIZE = 100
STATIC_PATHS = ("/", "/t/", "/machines")

# (monotonic time, view generation, body) per base URL; a build or an
# invalidation bumps the generation so a new dossier is listed at once.
_cache: dict[str, tuple[float, int, str]] = {}


async def render_sitemap(service: DossierService, max_entries: int = MAX_ENTRIES) -> str:
    """Render (or return the cached) /sitemap.xml body.

    Args:
        service: shared DossierService instance; its `base_url` roots every
            <loc>, the same base /llms.txt and `links.self` use.
        max_entries: cap on <url> elements, static pages included.

    Returns:
        str: the sitemap XML (sitemaps.org 0.9), ASCII only.
    """
    base = service.base_url
    cached = _cache.get(base)
    now = time.monotonic()
    generation = current_generation()
    if cached is not None and cached[1] == generation and now - cached[0] < CACHE_TTL_SECONDS:
        return cached[2]

    entries = [f"  <url><loc>{escape(base + path)}</loc></url>" for path in STATIC_PATHS]

    cursor: str | None = None
    while len(entries) < max_entries:
        items, cursor = await service.list_dossiers(None, PAGE_SIZE, cursor)
        for item in items:
            if len(entries) >= max_entries:
                break
            slug = quote(item.title.replace(" ", "_"), safe="_()',!*~-.")
            lastmod = item.pinned_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            entries.append(
                f"  <url><loc>{escape(f'{base}/t/{slug}')}</loc><lastmod>{lastmod}</lastmod></url>"
            )
        if cursor is None:
            break

    body = "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
            *entries,
            "</urlset>",
            "",
        ]
    )
    _cache[base] = (now, generation, body)
    return body
