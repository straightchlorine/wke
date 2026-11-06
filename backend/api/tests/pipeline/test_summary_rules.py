"""Summary input, the source check and section citations of a real build."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

import httpx
import pytest

from tests.factories.dossier import make_freshness, make_links
from tests.support.builds import build_only, run_queued_summaries, stored_dossier
from tests.support.jobs import make_job
from tests.support.ml_clients import make_ml_client
from tests.support.ml_payloads import analyze_response_json, summarize_response_json
from tests.support.wikimedia import WmFixtures
from wke.clients.ml import MLClient
from wke.clients.redis import RedisClient
from wke.clients.wikimedia import WikimediaClient
from wke.core import pack, render
from wke.core.citations import FRAGMENT_SAFE
from wke.core.models import Dossier
from wke.core.validate import heading_map, validate_view


def _ml(
    summary_text: str, truncated: bool | None = None, seen: list[str] | None = None
) -> MLClient:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/analyze":
            return httpx.Response(200, json=analyze_response_json())
        body: dict[str, Any] = summarize_response_json()
        body["text"] = summary_text
        if truncated is not None:
            body["truncated"] = truncated
        if seen is not None:
            seen.append(json.loads(request.content)["text"])
        return httpx.Response(200, json=body)

    return make_ml_client(handle)


async def _build(
    redis_client: RedisClient,
    wikimedia_client: WikimediaClient,
    ml: MLClient,
    sections: int = 1,
) -> Dossier:
    job = make_job()
    queue = await build_only(redis_client, wikimedia_client, ml, job, summary_sections=sections)
    await run_queued_summaries(redis_client, queue, ml)
    return await stored_dossier(redis_client, job)


async def test_model_reads_the_opening_passage_first(
    redis_client: RedisClient, wikimedia_client: WikimediaClient
) -> None:
    seen: list[str] = []
    dossier = await _build(redis_client, wikimedia_client, _ml("A short summary.", seen=seen))
    section = next(s for s in dossier.sections if s.summary_state == "done")
    by_id = {c.id: c for c in dossier.chunks}
    prose = [by_id[cid] for cid in section.chunk_ids if by_id[cid].kind == "prose"]
    assert seen[0].startswith(prose[0].text)
    assert section.summary is not None
    assert section.summary.input_chunk_ids
    assert section.summary.input_chunk_ids[0] == prose[0].id
    assert section.summary.citation_id == section.citation_id


@pytest.mark.parametrize(
    ("summary_text", "truncated", "reason"),
    [
        # "He" opens the sentence, so Zanzibar is the only name the check can miss.
        ("He moved to Zanzibar in 1999.", None, "Zanzibar"),
        ("A short summary.", True, "the model output was cut off"),
        ("A short summary that stops at the", None, "the text does not end at a sentence end"),
    ],
)
async def test_summary_failing_the_source_check_is_withheld_with_its_reason(
    redis_client: RedisClient,
    wikimedia_client: WikimediaClient,
    summary_text: str,
    truncated: bool | None,
    reason: str,
) -> None:
    ml = _ml(summary_text, truncated=truncated)
    dossier = await _build(redis_client, wikimedia_client, ml)
    section = next(s for s in dossier.sections if s.summary_state == "withheld")
    assert section.summary is None
    assert reason in (section.withheld_reason or "")
    assert dossier.build.state == "complete"
    assert dossier.build.summaries_done == 0


async def test_summary_naming_a_related_article_is_withheld(
    redis_client: RedisClient, wikimedia_client: WikimediaClient, wm_fixtures: WmFixtures
) -> None:
    related_title = wm_fixtures.json("morelike.json")["query"]["pages"][0]["title"]
    ml = _ml(f"It is close to {related_title}.")
    dossier = await _build(redis_client, wikimedia_client, ml)
    section = next(s for s in dossier.sections if s.summary_state == "withheld")
    assert section.withheld_reason == "the text names an article that is not in the source"


async def test_withheld_summary_is_named_in_the_markdown(
    redis_client: RedisClient, wikimedia_client: WikimediaClient
) -> None:
    dossier = await _build(redis_client, wikimedia_client, _ml("It ended in Zanzibar."))
    view = render.build_view(
        dossier, 32000, make_freshness(dossier), make_links(dossier), include_summaries=True
    )
    withheld = next(s for s in dossier.sections if s.summary_state == "withheld")
    assert withheld.withheld_reason
    assert f"Summary withheld: {withheld.withheld_reason}." in render.render_markdown(
        view, include_summaries=True
    )


async def test_build_cites_each_section_at_its_real_heading_id(
    redis_client: RedisClient, wikimedia_client: WikimediaClient, wm_fixtures: WmFixtures
) -> None:
    dossier = await _build(redis_client, wikimedia_client, _ml("A short summary."))
    headings = heading_map(wm_fixtures.text("parsoid.html"))
    by_id = {c.id: c for c in dossier.citations}
    assert len(by_id) == len(dossier.citations)
    seed = by_id["c1"]
    assert str(seed.url) == str(seed.pin.permalink)
    for section in dossier.sections:
        assert section.citation_id is not None
        citation = by_id[section.citation_id]
        if section.heading_path:
            assert citation.anchor in headings
            assert headings[citation.anchor] == section.heading_path[-1]
            quoted = quote(citation.anchor, safe=FRAGMENT_SAFE)
            assert str(citation.url) == f"{citation.pin.permalink}#{quoted}"
        else:
            assert citation.id == "c1"
        for chunk in (c for c in dossier.chunks if c.id in section.chunk_ids):
            assert chunk.citation_id == section.citation_id
    related = [c for c in dossier.citations if c.role == "related"]
    assert related
    assert all(c.anchor is None for c in related)


async def test_served_dossier_passes_the_validator_at_every_budget(
    redis_client: RedisClient, wikimedia_client: WikimediaClient, wm_fixtures: WmFixtures
) -> None:
    dossier = await _build(redis_client, wikimedia_client, _ml("A short summary."), 3)
    headings = heading_map(wm_fixtures.text("parsoid.html"))
    freshness, links = make_freshness(dossier), make_links(dossier)
    for budget in (2000, 8000, 32000):
        view = render.build_view(dossier, budget, freshness, links, include_summaries=True)
        report = validate_view(
            view, render.render_markdown(view, include_summaries=True), lambda _rev: headings
        )
        assert report.ok, report.problems[:5]
        assert report.counts["anchors_checked"] > 0
        assert pack.pack(dossier, budget).budget.used_est_tokens <= budget
