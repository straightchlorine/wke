"""A read uses the stored rating only when it is complete and matches the dossier."""

from __future__ import annotations

from typing import Any

import pytest
from redis.exceptions import RedisError

from tests.factories.dossier import make_fixture_dossier
from tests.support.constants import PIPELINE_VERSION
from tests.support.services import make_service, seed_dossier
from wke.clients.redis import RedisClient
from wke.core import keys
from wke.core.citations import seed_pin
from wke.core.models import DossierView
from wke.jobs.build.constants import RATING_MODEL, RATING_PROMPT_SHA256
from wke.jobs.build.rating import RatingConfig, RatingDocument, apply_rating, rating_key
from wke.services.dossiers import DossierService

DOSSIER = make_fixture_dossier()
PAGE_ID = DOSSIER.topic.page_id
REV_ID = seed_pin(DOSSIER).rev_id
KEY = rating_key(PAGE_ID, REV_ID, PIPELINE_VERSION)
PROSE_IDS = [c.id for c in DOSSIER.chunks if c.kind == "prose"]
# The lead gets the lowest score, the reverse of its stored relevance (the highest).
SCORES: dict[str, float | None] = dict(zip(PROSE_IDS, [0.0, 1.0, 1.0, 2.0, 3.0, 3.0], strict=True))
ON = RatingConfig(enabled=True, summary_sections=8)


def _document(**overrides: Any) -> str:
    fields: dict[str, Any] = {
        "prompt_sha256": RATING_PROMPT_SHA256,
        "model": RATING_MODEL,
        "done": True,
        "scores": SCORES,
    }
    return RatingDocument(**{**fields, **overrides}).model_dump_json()


async def _service(redis_client: RedisClient, config: RatingConfig = ON) -> DossierService:
    await seed_dossier(redis_client, DOSSIER)
    # LEAN_RESPONSE off: these tests compare the relevance of every chunk, Key facts included.
    return make_service(redis_client, rating=config, lean_response=False)


def _relevance(view: DossierView) -> dict[str, float]:
    return {c.id: c.relevance for c in view.chunks}


async def test_a_complete_rating_is_applied_and_the_view_says_so(
    redis_client: RedisClient,
) -> None:
    service = await _service(redis_client)
    await redis_client.set(KEY, _document())

    view = await service.get_dossier_view(PAGE_ID, 8000, "json", False)

    expected = apply_rating(DOSSIER, SCORES, 8)
    assert expected is not None
    assert view.build.selection == "rating"
    assert _relevance(view) == {c.id: c.relevance for c in expected.chunks}
    assert _relevance(view) != {c.id: c.relevance for c in DOSSIER.chunks}


@pytest.mark.parametrize(
    "stored",
    [
        None,
        _document(done=False),
        _document(scores={k: v for k, v in SCORES.items() if k != PROSE_IDS[0]}),
        _document(scores={**SCORES, "x:other": 1.0}),
        _document(prompt_sha256="0" * 64),
        _document(model="other"),
        "not json",
    ],
    ids=[
        "absent",
        "unfinished",
        "missing_id",
        "extra_id",
        "other_prompt",
        "other_model",
        "corrupt",
    ],
)
async def test_without_a_usable_rating_the_stored_relevance_is_packed(
    redis_client: RedisClient, stored: str | None
) -> None:
    service = await _service(redis_client)
    if stored is not None:
        await redis_client.set(KEY, stored)

    view = await service.get_dossier_view(PAGE_ID, 8000, "json", False)

    assert view.build.selection == "relevance"
    assert _relevance(view) == {c.id: c.relevance for c in DOSSIER.chunks}


async def test_with_the_switch_off_the_rating_key_is_never_read_and_no_field_is_added(
    redis_client: RedisClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = await _service(redis_client, RatingConfig())
    await redis_client.set(KEY, _document())
    read: list[str] = []
    real_get = redis_client.get

    async def spying_get(key: str) -> str | None:
        read.append(key)
        return await real_get(key)

    monkeypatch.setattr(redis_client, "get", spying_get)

    view = await service.get_dossier_view(PAGE_ID, 8000, "json", False)

    assert KEY not in read
    assert view.build.selection is None
    assert "selection" not in view.model_dump(mode="json")["build"]
    assert _relevance(view) == {c.id: c.relevance for c in DOSSIER.chunks}


async def test_a_redis_error_on_the_rating_key_reads_as_no_rating(
    redis_client: RedisClient, fake_redis: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = await _service(redis_client)
    await redis_client.set(KEY, _document())
    real_get = fake_redis.get

    async def failing_get(key: str, *args: Any, **kwargs: Any) -> Any:
        if key.startswith("rating:"):
            raise RedisError("down")
        return await real_get(key, *args, **kwargs)

    monkeypatch.setattr(fake_redis, "get", failing_get)

    view = await service.get_dossier_view(PAGE_ID, 8000, "json", False)

    assert view.build.selection == "relevance"


async def test_reading_leaves_the_stored_dossier_and_rating_as_they_were(
    redis_client: RedisClient,
) -> None:
    service = await _service(redis_client)
    await redis_client.set(KEY, _document())
    dossier_key = keys.dossier(PAGE_ID, REV_ID, PIPELINE_VERSION)
    before = await redis_client.get(dossier_key)

    await service.get_dossier_view(PAGE_ID, 8000, "json", False)

    assert await redis_client.get(dossier_key) == before
    assert await redis_client.get(KEY) == _document()


async def test_a_pinned_read_uses_the_rating_of_that_revision(redis_client: RedisClient) -> None:
    service = await _service(redis_client)
    await redis_client.set(KEY, _document())

    view = await service.get_dossier_view(PAGE_ID, 8000, "json", False, rev_id=REV_ID)

    assert view.build.selection == "rating"


async def test_the_markdown_read_packs_with_the_rating_too(redis_client: RedisClient) -> None:
    service = await _service(redis_client)
    plain = await service.get_dossier_view(PAGE_ID, 8000, "markdown", False)
    await redis_client.set(KEY, _document())

    rated = await service.get_dossier_view(PAGE_ID, 8000, "markdown", False)

    assert isinstance(rated, str) and isinstance(plain, str)
    assert "selection" not in rated


async def test_a_rating_with_too_few_real_scores_is_not_applied_and_the_view_says_relevance(
    redis_client: RedisClient,
) -> None:
    service = await _service(redis_client)
    await redis_client.set(KEY, _document(scores={i: None for i in PROSE_IDS}))

    view = await service.get_dossier_view(PAGE_ID, 8000, "json", False)

    assert view.build.selection == "relevance"
    assert _relevance(view) == {c.id: c.relevance for c in DOSSIER.chunks}


async def test_the_coverage_setting_decides_how_many_nulls_a_rating_may_hold(
    redis_client: RedisClient,
) -> None:
    # One of six scores is None: coverage is 5/6, above 0.8 and below 0.9.
    scores = {**SCORES, PROSE_IDS[0]: None}
    await _service(redis_client)
    await redis_client.set(KEY, _document(scores=scores))

    strict = make_service(redis_client, rating=RatingConfig(enabled=True, min_coverage=0.9))
    lenient = make_service(redis_client, rating=RatingConfig(enabled=True, min_coverage=0.8))

    assert (await strict.get_dossier_view(PAGE_ID, 8000, "json", False)).build.selection == (
        "relevance"
    )
    assert (await lenient.get_dossier_view(PAGE_ID, 8000, "json", False)).build.selection == (
        "rating"
    )
