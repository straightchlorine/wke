"""The SUBSECTION_HEADINGS switch reaches the service's markdown render."""

from __future__ import annotations

from tests.core.render.test_render_structure import _jumping
from tests.support.services import make_service, seed_dossier
from wke.clients.redis import RedisClient


async def test_service_flag_switches_subsection_headings(redis_client: RedisClient) -> None:
    dossier = _jumping([["Busy"], ["Busy", "Alpha"]])
    await seed_dossier(redis_client, dossier)
    page_id = dossier.topic.page_id
    service = make_service(redis_client)
    on = await service.get_dossier_view(page_id, 2000, "markdown", True)
    assert "\n### Alpha\n" in on
    service.subsection_headings = False
    off = await service.get_dossier_view(page_id, 2000, "markdown", True)
    assert "### Alpha" not in off
