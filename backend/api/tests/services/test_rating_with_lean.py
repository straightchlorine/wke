"""A view chosen by the rating is lean like an unrated one: no Key facts, no left-out lines."""

from __future__ import annotations

import pytest

from tests.factories.synthetic import dossier_of, prose, section, sized
from tests.support.constants import PIPELINE_VERSION
from tests.support.services import make_service, seed_dossier
from wke.api.routes.dossiers.params import view_etag
from wke.clients.redis import RedisClient
from wke.core.citations import seed_pin
from wke.core.models import Dossier, DossierView
from wke.core.render.markdown import content_text
from wke.core.render.parts import ALL_PARTS, DEFAULT_PARTS
from wke.core.text.tokens import est_tokens
from wke.jobs.build.constants import RATING_MODEL, RATING_PROMPT_SHA256
from wke.jobs.build.rating import RatingConfig, RatingDocument, rating_key
from wke.services.dossiers import DossierService

ON = RatingConfig(enabled=True, summary_sections=8)
FACTS_ID = "1:lead:facts"
NOTICE = "_1 list of this section is left out at this budget._"
FACTS_LABEL = "**Key facts**"


def _dossier() -> Dossier:
    """A lead with Key facts, one section of 40 passages and a list too long for 2000 tokens."""
    rows = "\n".join(f"Fact {n}: {sized('value', 14)}" for n in range(12))
    facts = prose(FACTS_ID, [], 1, rows).model_copy(update={"kind": "facts"})
    items = "\n".join(f"- {'word ' * 120}{n}" for n in range(10))
    structured = prose("1:data:list0", ["Data"], 99, items).model_copy(update={"kind": "list"})
    passages = [
        prose(f"1:data:{n}", ["Data"], n, sized(f"Passage {n} says.", 90), 0.9 - n * 0.01)
        for n in range(40)
    ]
    return dossier_of(
        [
            section("lead", [], ["1:lead:0", facts.id]),
            section("data", ["Data"], [*(p.id for p in passages), structured.id]),
        ],
        [prose("1:lead:0", [], 0, "Alpha builds boats."), facts, *passages, structured],
    )


def _scores(dossier: Dossier) -> dict[str, float | None]:
    """Scores that rank the last ten passages first, the reverse of their stored relevance."""
    return {
        c.id: (3.0 if c.id == "1:lead:0" or int(c.id.rsplit(":", 1)[1]) >= 30 else 0.0)
        for c in dossier.chunks
        if c.kind == "prose"
    }


async def _serve(
    redis_client: RedisClient,
    dossier: Dossier,
    scores: dict[str, float | None] | None,
    *,
    lean: bool = True,
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


async def _markdown(
    service: DossierService, dossier: Dossier, budget: int = 2000, parts=DEFAULT_PARTS
) -> str:
    return await service.get_dossier_view(  # type: ignore[return-value]
        dossier.topic.page_id, budget, "markdown", False, parts=parts
    )


def _prose_tokens(view: DossierView) -> int:
    return sum(c.est_tokens for c in view.chunks if c.kind == "prose")


@pytest.mark.parametrize("budget", [2000, 8000, 32000])
async def test_a_rated_lean_pack_holds_no_key_facts_chunk(
    redis_client: RedisClient, budget: int
) -> None:
    dossier = _dossier()
    view = await _view(await _serve(redis_client, dossier, _scores(dossier)), dossier, budget)

    assert view.build.selection == "rating"
    assert FACTS_ID not in [c.id for c in view.chunks]
    assert FACTS_ID not in view.budget.included_chunk_ids
    assert all(FACTS_ID not in s.chunk_ids for s in view.sections)
    assert view.budget.omitted_chunks == len(dossier.chunks) - 1 - len(view.chunks)


async def test_the_key_facts_room_of_a_rated_pack_goes_to_passages(
    redis_client: RedisClient,
) -> None:
    dossier = _dossier()
    scores = _scores(dossier)
    lean = await _view(await _serve(redis_client, dossier, scores), dossier)
    full = await _view(await _serve(redis_client, dossier, scores, lean=False), dossier)

    assert lean.build.selection == full.build.selection == "rating"
    assert FACTS_ID in [c.id for c in full.chunks]
    assert _prose_tokens(lean) > _prose_tokens(full)
    shown = {c.id for c in lean.chunks}
    assert all(f"1:data:{n}" in shown for n in range(30, 40))


async def test_a_rated_lean_view_is_the_lean_view_of_the_rated_dossier(
    redis_client: RedisClient,
) -> None:
    dossier = _dossier()
    scores = _scores(dossier)
    rated_service = await _serve(redis_client, dossier, scores)
    rated = await _view(rated_service, dossier)
    rated_dossier, selection = await rated_service._select_by_rating(
        dossier, dossier.topic.page_id, seed_pin(dossier).rev_id
    )
    assert selection == "rating"

    from tests.factories.dossier import make_freshness, make_links
    from wke.core import render

    expected = render.build_view(
        rated_dossier,
        2000,
        make_freshness(rated_dossier),
        make_links(rated_dossier),
        include_summaries=False,
        subsection_headings=True,
        lean=True,
    )
    assert [c.id for c in rated.chunks] == [c.id for c in expected.chunks]
    assert rated.budget.used_est_tokens == expected.budget.used_est_tokens


async def test_no_left_out_line_stands_in_the_dossier_part_of_a_rated_view(
    redis_client: RedisClient,
) -> None:
    dossier = _dossier()
    service = await _serve(redis_client, dossier, _scores(dossier))

    body = await _markdown(service, dossier)

    assert "of this section" not in body
    assert FACTS_LABEL not in body and "Fact 0:" not in body
    with_head = await _markdown(service, dossier, parts=frozenset({"dossier", "metadata"}))
    assert NOTICE in with_head
    assert FACTS_LABEL not in with_head and "Fact 0:" not in with_head
    everything = await _markdown(service, dossier, parts=ALL_PARTS)
    assert NOTICE in everything and FACTS_LABEL not in everything


async def test_a_rated_view_not_lean_still_writes_both_as_before(
    redis_client: RedisClient,
) -> None:
    dossier = _dossier()
    service = await _serve(redis_client, dossier, _scores(dossier), lean=False)

    body = await _markdown(service, dossier)

    assert FACTS_LABEL in body
    assert NOTICE in body


def _structural() -> Dossier:
    """One section whose 60 passages cycle through five subsections, plus a lead and Key facts."""
    rows = "\n".join(f"Fact {n}: {sized('value', 14)}" for n in range(12))
    facts = prose(FACTS_ID, [], 1, rows).model_copy(update={"kind": "facts"})
    subsections = ["Alpha", "Beta", "Gamma", "Delta", "Epsilon"]
    passages = [
        prose(
            f"1:busy:{n}",
            ["Busy", subsections[n % len(subsections)]],
            n,
            sized(f"Passage {n} of {subsections[n % len(subsections)]}.", 70),
            0.9 - n * 0.01,
        )
        for n in range(60)
    ]
    built = dossier_of(
        [
            section("lead", [], ["1:lead:0", facts.id]),
            section("busy", ["Busy"], [p.id for p in passages]),
        ],
        [prose("1:lead:0", [], 0, "Alpha builds boats."), facts, *passages],
    )
    return built.model_copy(
        update={"build": built.build.model_copy(update={"analysis": "structural"})}
    )


@pytest.mark.parametrize("budget", [2000, 8000])
@pytest.mark.parametrize("rated", [True, False])
async def test_headings_and_the_lean_response_together_stay_within_the_budget(
    redis_client: RedisClient, budget: int, rated: bool
) -> None:
    dossier = _structural()
    # Spreads the scores so the chosen passages alternate between subsections.
    scores: dict[str, float | None] = {
        c.id: float((int(c.id.rsplit(":", 1)[1]) * 7) % 4) if c.id != "1:lead:0" else 3.0
        for c in dossier.chunks
        if c.kind == "prose"
    }
    service = await _serve(redis_client, dossier, scores if rated else None)

    view = await _view(service, dossier, budget)
    body = await _markdown(service, dossier, budget)

    assert view.build.selection == ("rating" if rated else "relevance")
    assert FACTS_ID not in [c.id for c in view.chunks]
    assert body.count("\n### ") >= 3
    counted, _ = content_text(view, subsection_headings=True, notes=False)
    assert view.budget.used_est_tokens == est_tokens(counted) <= budget
    unheaded, _ = content_text(view, subsection_headings=False, notes=False)
    assert est_tokens(unheaded) < est_tokens(counted)


async def test_the_etag_names_the_lean_response_then_the_selection(
    redis_client: RedisClient,
) -> None:
    dossier = _dossier()
    unrated = await _view(await _serve(redis_client, dossier, None), dossier)
    plain = await _view(
        await _serve(redis_client, dossier, None, lean=False, rating=RatingConfig()), dossier
    )
    rated = await _view(await _serve(redis_client, dossier, _scores(dossier)), dossier)

    no_h = {"subsection_headings": False, "table_repack": False}
    assert view_etag(rated, 2000, "json", False, lean=True, **no_h).endswith('-pdl-r1"')
    assert view_etag(unrated, 2000, "json", False, lean=True, **no_h).endswith('-pdl-r0"')
    assert view_etag(plain, 2000, "json", False, lean=False, **no_h).endswith('-s0-l0-pd"')
