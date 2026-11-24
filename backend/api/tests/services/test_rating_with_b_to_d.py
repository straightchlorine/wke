"""Selection by rating (F) with subsection headings (B) and the ETag.

B's headings and the fit loop run inside build_view, on the passages the pack shows. With a
rating applied that pack is the rated one, so these tests pin that they follow it. The services
here are not lean, so the key facts chunk is in the pack, as it is in the ETag of base; the
lean response with a rating is in test_rating_with_lean.py.
"""

from __future__ import annotations

import inspect
import math

import pytest

from tests.factories.synthetic import dossier_of, prose, section, sized
from tests.support.constants import PIPELINE_VERSION
from tests.support.services import make_service, seed_dossier
from wke.api.etag import compute_etag
from wke.api.routes.dossiers.params import view_etag
from wke.clients.redis import RedisClient
from wke.core.citations import seed_pin
from wke.core.models import Chunk, Dossier, DossierView
from wke.jobs.build.constants import RATING_MODEL, RATING_PROMPT_SHA256
from wke.jobs.build.rating import RatingConfig, RatingDocument, rating_key
from wke.services.dossiers import DossierService

ON = RatingConfig(enabled=True, summary_sections=8)
BORN = "Born: 4 March 1961"
DIED = "Died: 9 June 2020"


def _facts(rows: list[str]) -> Chunk:
    text = "\n".join(rows)
    return Chunk(
        id="l:facts",
        kind="facts",
        citation_id="c1",
        heading_path=[],
        order=1,
        text=text,
        est_tokens=math.ceil(len(text) / 4),
        relevance=1.0,
    )


def _two_passages() -> Dossier:
    """Passage a:0 (stored relevance 0.9) states the Born row, b:0 (0.1) states the Died row.

    At 2000 tokens only one of the two fits beside the lead, so the pack decides which one shows.
    """
    chunks = [
        prose("l:0", [], 0, "Alma Reyes is a Chilean sculptor.", 1.0),
        _facts([BORN, DIED]),
        prose("a:0", ["A"], 10, sized("Alma Reyes (born 4 March 1961) lived in Chile.", 1000), 0.9),
        prose("b:0", ["B"], 20, sized("Alma Reyes (died 9 June 2020) wrote in Chile.", 1000), 0.1),
    ]
    sections = [
        section("s0", [], ["l:0", "l:facts"]),
        section("a", ["A"], ["a:0"]),
        section("b", ["B"], ["b:0"]),
    ]
    return dossier_of(sections, chunks)


def _structural() -> Dossier:
    """One section whose passages sit in subsections; only two of its three fit at 2000 tokens."""
    chunks = [
        prose("l:0", [], 0, "Alma Reyes is a Chilean sculptor.", 1.0),
        prose("b:0", ["Busy"], 10, sized("Opening passage of the busy part.", 900), 0.9),
        prose("b:1", ["Busy", "Alpha"], 11, sized("Alpha passage of the busy part.", 900), 0.8),
        prose("b:2", ["Busy", "Beta"], 12, sized("Beta passage of the busy part.", 900), 0.1),
    ]
    sections = [section("s0", [], ["l:0"]), section("busy", ["Busy"], ["b:0", "b:1", "b:2"])]
    built = dossier_of(sections, chunks)
    return built.model_copy(
        update={"build": built.build.model_copy(update={"analysis": "structural"})}
    )


async def _serve(
    redis_client: RedisClient,
    dossier: Dossier,
    scores: dict[str, float | None] | None,
    *,
    lean: bool = False,
    headings: bool = True,
    rating: RatingConfig = ON,
) -> DossierService:
    await seed_dossier(redis_client, dossier)
    if scores is not None:
        document = RatingDocument(
            prompt_sha256=RATING_PROMPT_SHA256, model=RATING_MODEL, done=True, scores=scores
        )
        key = rating_key(dossier.topic.page_id, seed_pin(dossier).rev_id, PIPELINE_VERSION)
        await redis_client.set(key, document.model_dump_json())
    service = make_service(redis_client, lean_response=lean, rating=rating)
    service.subsection_headings = headings
    return service


async def _view(service: DossierService, dossier: Dossier, budget: int = 2000) -> DossierView:
    return await service.get_dossier_view(dossier.topic.page_id, budget, "json", False)  # type: ignore[return-value]


async def _markdown(service: DossierService, dossier: Dossier, budget: int = 2000) -> str:
    return await service.get_dossier_view(dossier.topic.page_id, budget, "markdown", False)  # type: ignore[return-value]


# The rating puts b:0 above a:0, the reverse of the stored relevance.
SWAPPED: dict[str, float | None] = {"l:0": 3.0, "a:0": 0.0, "b:0": 3.0}


async def test_subsection_headings_follow_the_prose_of_the_rated_pack(
    redis_client: RedisClient,
) -> None:
    dossier = _structural()
    unrated = await _markdown(await _serve(redis_client, dossier, None), dossier)
    assert "\n### Alpha\n" in unrated and "### Beta" not in unrated

    rated_scores: dict[str, float | None] = {"l:0": 3.0, "b:0": 3.0, "b:1": 0.0, "b:2": 3.0}
    service = await _serve(redis_client, dossier, rated_scores)
    view = await _view(service, dossier)
    rated = await _markdown(service, dossier)

    assert view.build.selection == "rating"
    assert view.build.analysis == "structural"
    assert [c.id for c in view.chunks if c.kind == "prose"] == ["l:0", "b:0", "b:2"]
    assert "\n### Beta\n" in rated and "### Alpha" not in rated

    service.subsection_headings = False
    assert "###" not in await _markdown(service, dossier)


async def test_the_fit_loop_counts_the_headings_of_the_rated_pack(
    redis_client: RedisClient,
) -> None:
    dossier = _structural()
    scores: dict[str, float | None] = {"l:0": 3.0, "b:0": 3.0, "b:1": 0.0, "b:2": 3.0}
    on = await _view(await _serve(redis_client, dossier, scores), dossier)
    off = await _view(await _serve(redis_client, dossier, scores, headings=False), dossier)

    assert on.budget.used_est_tokens <= on.budget.requested
    assert on.budget.used_est_tokens > off.budget.used_est_tokens


# ETag: every part is named here; nothing but the selection is new to the ETag of base.


def _base_etag(view: DossierView, budget: int = 2000) -> str:
    """The ETag of base's code: build state, summaries done, s0, l0 and the parts code pd."""
    build = view.build
    return (
        f'"{view.freshness.pinned_rev_id}-{build.pipeline_version}-{budget}-json-'
        f'{build.state}-{build.summaries_done}-s0-l0-pd"'
    )


async def test_every_switch_off_gives_the_etag_of_base(redis_client: RedisClient) -> None:
    dossier = _two_passages()
    service = await _serve(
        redis_client, dossier, SWAPPED, lean=False, headings=False, rating=RatingConfig()
    )

    view = await _view(service, dossier)

    assert view.build.selection is None
    assert view_etag(view, 2000, "json", False, lean=False, subsection_headings=False) == (
        _base_etag(view)
    )


async def test_the_etag_reflects_the_selection_used(redis_client: RedisClient) -> None:
    dossier = _two_passages()
    unrated = await _view(await _serve(redis_client, dossier, None), dossier)
    rated = await _view(await _serve(redis_client, dossier, SWAPPED), dossier)

    off = {"lean": False, "subsection_headings": False}
    assert view_etag(unrated, 2000, "json", False, **off) == _base_etag(unrated)[:-1] + '-r0"'
    assert view_etag(rated, 2000, "json", False, **off) == _base_etag(rated)[:-1] + '-r1"'


@pytest.mark.parametrize("headings", [True, False])
async def test_the_subsection_switch_adds_the_letter_h_to_the_etag(
    redis_client: RedisClient, headings: bool
) -> None:
    dossier = _structural()
    service = await _serve(redis_client, dossier, None, headings=headings, rating=RatingConfig())

    view = await _view(service, dossier)

    etag = view_etag(view, 2000, "json", False, lean=False, subsection_headings=headings)
    assert etag == (_base_etag(view)[:-1] + 'h"' if headings else _base_etag(view))


def test_compute_etag_takes_nothing_new_but_the_selection() -> None:
    names = list(inspect.signature(compute_etag).parameters)
    assert names == [
        "rev_id",
        "pipeline_version",
        "budget",
        "fmt",
        "build_state",
        "summaries_done",
        "summaries",
        "links",
        "parts_code",
        "selection",
    ]
    base = compute_etag(7, "pv", 2000, "json")
    assert base == '"7-pv-2000-json-complete-0-s0-l0-pd"'
    assert compute_etag(7, "pv", 2000, "json", selection="relevance") == base[:-1] + '-r0"'
    assert compute_etag(7, "pv", 2000, "json", selection="rating") == base[:-1] + '-r1"'
