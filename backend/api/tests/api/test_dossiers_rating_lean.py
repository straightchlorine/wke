"""A rated read with LEAN_RESPONSE on drops the Key facts and left-out lines in every format.

LEAN_RESPONSE omits the Key facts block and the per-section "left out at this budget" lines.
"""

from __future__ import annotations

import pytest

from tests.support.apps import app_client
from tests.support.constants import FIXTURE_REV_ID, PIPELINE_VERSION
from wke.core import keys
from wke.core.citations import seed_pin
from wke.core.models import Dossier
from wke.jobs.build.constants import RATING_MODEL, RATING_PROMPT_SHA256
from wke.jobs.build.rating import RatingDocument, rating_key
from wke.settings import Settings

ALL = {"parts": "dossier,metadata,sources"}


@pytest.fixture
def rating_on(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "selection_rating", True)


async def _store_rating(fake_redis, page_id: int) -> Dossier:
    key = keys.dossier(page_id, FIXTURE_REV_ID, PIPELINE_VERSION)
    dossier = Dossier.model_validate_json(await fake_redis.get(key))
    document = RatingDocument(
        prompt_sha256=RATING_PROMPT_SHA256,
        model=RATING_MODEL,
        done=True,
        scores={c.id: 1.0 for c in dossier.chunks if c.kind == "prose"},
    )
    await fake_redis.set(
        rating_key(page_id, FIXTURE_REV_ID, PIPELINE_VERSION), document.model_dump_json()
    )
    return dossier


@pytest.mark.parametrize("budget", [2000, 8000, 32000])
async def test_a_rated_json_response_carries_no_key_facts_chunk(
    app, built_page, fake_redis, rating_on, budget
) -> None:
    stored = await _store_rating(fake_redis, built_page)
    facts_ids = {c.id for c in stored.chunks if c.kind == "facts"}
    assert facts_ids

    async with app_client(app) as client:
        response = await client.get(
            f"/api/v1/dossiers/{built_page}", params={**ALL, "budget": budget}
        )

    body = response.json()
    assert body["metadata"]["build"]["selection"] == "rating"
    assert facts_ids.isdisjoint(c["id"] for c in body["dossier"]["chunks"])
    assert facts_ids.isdisjoint(body["metadata"]["budget"]["included_chunk_ids"])
    assert all(facts_ids.isdisjoint(s["chunk_ids"]) for s in body["dossier"]["sections"])


@pytest.mark.parametrize("params", [{}, {"links": "true"}, ALL, {"parts": "dossier,metadata"}])
async def test_a_rated_markdown_response_carries_no_key_facts_block(
    app, built_page, fake_redis, rating_on, params
) -> None:
    await _store_rating(fake_redis, built_page)

    async with app_client(app) as client:
        response = await client.get(f"/api/v1/dossiers/{built_page}.md", params=params)

    assert response.status_code == 200
    assert "**Key facts**" not in response.text
    assert "Born:" not in response.text


async def test_the_etag_of_a_rated_lean_response_names_both(
    app, built_page, fake_redis, rating_on
) -> None:
    async with app_client(app) as client:
        before = await client.get(f"/api/v1/dossiers/{built_page}")
        await _store_rating(fake_redis, built_page)
        after = await client.get(f"/api/v1/dossiers/{built_page}")

    assert before.headers["etag"].endswith('-pdlh-r0"')
    assert after.headers["etag"].endswith('-pdlh-r1"')
    assert after.headers["etag"] != before.headers["etag"]


async def test_the_dossier_tokens_header_of_a_rated_lean_response_is_within_the_budget(
    app, built_page, fake_redis, rating_on
) -> None:
    await _store_rating(fake_redis, built_page)

    async with app_client(app) as client:
        response = await client.get(f"/api/v1/dossiers/{built_page}.md", params={"budget": 2000})

    assert int(response.headers["wke-dossier-tokens"]) <= 2000


def _structural_dossier() -> Dossier:
    """A structural build: one section whose passages cycle through four subsections in turn."""
    from tests.factories.synthetic import dossier_of, prose, section, sized

    rows = "\n".join(f"Fact {n}: {sized('value', 14)}" for n in range(12))
    facts = prose("1:lead:facts", [], 1, rows).model_copy(update={"kind": "facts"})
    names = ["Alpha", "Beta", "Gamma", "Delta"]
    passages = [
        prose(f"1:busy:{n}", ["Busy", names[n % 4]], n, sized(f"Passage {n}.", 70), 0.9 - n * 0.01)
        for n in range(40)
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


@pytest.mark.parametrize("rated", [False, True])
@pytest.mark.parametrize("lean", [False, True])
@pytest.mark.parametrize("headings", [False, True])
async def test_each_switch_acts_alone_on_the_markdown_route(
    app, settings, redis_client, fake_redis, monkeypatch, headings, lean, rated
) -> None:
    from tests.support.services import seed_dossier

    dossier = _structural_dossier()
    await seed_dossier(redis_client, dossier)
    monkeypatch.setattr(settings, "subsection_headings", headings)
    monkeypatch.setattr(settings, "lean_response", lean)
    monkeypatch.setattr(settings, "selection_rating", rated)
    if rated:
        document = RatingDocument(
            prompt_sha256=RATING_PROMPT_SHA256,
            model=RATING_MODEL,
            done=True,
            scores={c.id: float(c.order % 4) for c in dossier.chunks if c.kind == "prose"},
        )
        key = rating_key(dossier.topic.page_id, seed_pin(dossier).rev_id, PIPELINE_VERSION)
        await fake_redis.set(key, document.model_dump_json())

    async with app_client(app) as client:
        response = await client.get(
            f"/api/v1/dossiers/{dossier.topic.page_id}.md", params={"budget": 2000}
        )

    assert response.status_code == 200
    assert ("\n### " in response.text) == headings
    assert ("**Key facts**" in response.text) == (not lean)
    assert response.headers["etag"].endswith('-r1"') == rated


async def _seed_rated_with_a_left_out_table(redis_client, fake_redis) -> Dossier:
    """A dossier whose section s3 has a table too big for 2000 tokens, and a stored rating."""
    from tests.api.test_lean_response import _with_heavy_table
    from tests.factories.dossier import make_fixture_dossier
    from tests.support.services import seed_dossier

    dossier = _with_heavy_table(make_fixture_dossier())
    await seed_dossier(redis_client, dossier)
    document = RatingDocument(
        prompt_sha256=RATING_PROMPT_SHA256,
        model=RATING_MODEL,
        done=True,
        scores={c.id: 1.0 for c in dossier.chunks if c.kind == "prose"},
    )
    key = rating_key(dossier.topic.page_id, seed_pin(dossier).rev_id, PIPELINE_VERSION)
    await fake_redis.set(key, document.model_dump_json())
    return dossier


@pytest.mark.parametrize("route", ["{id}.md", "{id}?format=md"])
async def test_a_rated_markdown_read_writes_the_left_out_line_only_with_metadata(
    app, redis_client, fake_redis, rating_on, route
) -> None:
    dossier = await _seed_rated_with_a_left_out_table(redis_client, fake_redis)
    path = f"/api/v1/dossiers/{route.format(id=dossier.topic.page_id)}"
    sep = "&" if "?" in path else "?"

    async with app_client(app) as client:
        plain = await client.get(f"{path}{sep}budget=2000")
        with_metadata = await client.get(f"{path}{sep}budget=2000&parts=dossier,metadata")

    assert plain.headers["etag"].endswith('-r1"')
    assert "of this section" not in plain.text
    assert "_1 table of this section is left out at this budget._" in with_metadata.text


async def test_a_rated_post_200_equals_the_get_with_the_same_lean_etag(
    app, built_page, fake_redis, rating_on
) -> None:
    from tests.support.constants import FIXTURE_TITLE

    await _store_rating(fake_redis, built_page)
    async with app_client(app) as client:
        posted = await client.post("/api/v1/dossiers", json={"title": FIXTURE_TITLE})
        fetched = await client.get(f"/api/v1/dossiers/{built_page}")

    assert posted.status_code == 200
    assert posted.headers["etag"] == fetched.headers["etag"]
    assert posted.headers["etag"].endswith('-pdlh-r1"')
    assert posted.content == fetched.content
