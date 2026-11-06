"""POST /api/v1/dossiers: admission, refresh and build limits, and Wikimedia call counts."""

from __future__ import annotations

from datetime import datetime

import limits
import pytest

from tests.support.apps import app_client, make_app
from tests.support.constants import (
    DISAMBIGUATION_TITLE,
    FIXTURE_PAGE_ID,
    FIXTURE_REV_TIMESTAMP,
    FIXTURE_TITLE,
    MISSING_TITLE,
    NEW_TITLE,
    PIPELINE_VERSION,
)
from wke.api.ratelimit import POST_DOSSIERS_RATE_LIMIT
from wke.core import keys
from wke.core.models import Dossier
from wke.jobs.build.run import run_build
from wke.jobs.queue import JobQueue
from wke.services.dossiers import DossierService


async def test_post_missing_title_is_404_problem(app) -> None:
    async with app_client(app) as client:
        response = await client.post("/api/v1/dossiers", json={"title": MISSING_TITLE})

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == "not_found"
    assert "request_id" in body


async def test_post_disambiguation_is_409_with_candidates(app, wm_fixtures) -> None:
    """Candidates come from the search path (generator=search), not the
    disambiguation page's `links`, so every candidate carries a real
    page_id and an honest dossier_state -- never page_id 0.
    """
    async with app_client(app) as client:
        response = await client.post("/api/v1/dossiers", json={"title": DISAMBIGUATION_TITLE})

    assert response.status_code == 409
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == "disambiguation"
    assert ";" not in body["detail"]
    assert "disambiguation page. Pick one of the candidates." in body["detail"]
    candidates = body["candidates"]
    assert candidates
    pages = wm_fixtures.json("search.json")["query"]["pages"]
    expected_titles = {
        page["title"] for page in pages if "disambiguation" not in page.get("pageprops", {})
    }
    assert {c["title"] for c in candidates} == expected_titles
    assert all(c["page_id"] > 0 for c in candidates)
    assert all(c["dossier_state"] == "none" for c in candidates)


async def test_post_disambiguation_costs_exactly_one_extra_wikimedia_call(
    fake_redis, settings, counting_wikimedia_client, ml_client_ok
) -> None:
    """A 409 disambiguation resolve plus its search-path candidate lookup
    is exactly two Wikimedia calls: one resolve, one generator=search.
    """
    wikimedia, calls = counting_wikimedia_client
    app = make_app(fake_redis, settings, wikimedia_http=wikimedia._http, ml_http=ml_client_ok._http)

    async with app_client(app) as client:
        response = await client.post("/api/v1/dossiers", json={"title": DISAMBIGUATION_TITLE})

    assert response.status_code == 409
    assert len(calls) == 2
    assert "generator=search" in calls[1]


async def test_post_unexpected_field_is_422(app) -> None:
    async with app_client(app) as client:
        response = await client.post(
            "/api/v1/dossiers", json={"title": FIXTURE_TITLE, "bogus": True}
        )

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "validation_error"


async def test_post_new_title_is_202_with_location_and_job(app) -> None:
    async with app_client(app) as client:
        response = await client.post("/api/v1/dossiers", json={"title": NEW_TITLE})

    assert response.status_code == 202
    body = response.json()
    assert response.headers["location"] == f"/api/v1/jobs/{body['id']}"
    assert response.headers["retry-after"] == "1"
    assert body["title"] == NEW_TITLE
    # No worker runs in the test app (start_worker=False), so this can
    # only be "queued"; "running" would mean a live worker raced the
    # assertion.
    assert body["status"] == "queued"


async def test_post_already_built_is_200_with_etag(app, built_page) -> None:
    async with app_client(app) as client:
        response = await client.post(
            "/api/v1/dossiers", params={"parts": "dossier,metadata"}, json={"title": FIXTURE_TITLE}
        )
        fetched = await client.get(
            f"/api/v1/dossiers/{built_page}", params={"parts": "dossier,metadata"}
        )

    assert response.status_code == 200
    assert response.headers["etag"] == fetched.headers["etag"]
    assert response.json()["metadata"]["topic"]["page_id"] == built_page


async def test_post_refresh_true_admits_rebuild_and_keeps_old_dossier(app, built_page) -> None:
    """Stale-while-revalidate: refresh=true must never make the dossier 404."""
    async with app_client(app) as client:
        response = await client.post(
            "/api/v1/dossiers", json={"title": FIXTURE_TITLE, "refresh": True}
        )
        still_there = await client.get(f"/api/v1/dossiers/{built_page}")

    assert response.status_code == 202
    assert "Location" in response.headers
    assert still_there.status_code == 200


async def test_post_refresh_true_is_rate_limited_at_two_per_hour(app, built_page) -> None:
    """A forced rebuild is limited to 2 per hour per IP; the third is a 429."""
    page_id = built_page
    async with app_client(app) as client:
        first = await client.post(
            "/api/v1/dossiers", json={"title": FIXTURE_TITLE, "refresh": True}
        )
        second = await client.post(
            "/api/v1/dossiers", json={"title": FIXTURE_TITLE, "refresh": True}
        )
        third = await client.post(
            "/api/v1/dossiers", json={"title": FIXTURE_TITLE, "refresh": True}
        )

    assert first.status_code == 202
    assert second.status_code == 202
    assert third.status_code == 429
    assert third.headers["content-type"] == "application/problem+json"
    body = third.json()
    assert body["code"] == "rate_limited"
    # A title whose dossier already exists still has a readable GET route while
    # refreshes are rate limited; the ApiError detail says so.
    assert "still readable" in body["detail"]
    assert f"/api/v1/dossiers/{page_id}" in body["detail"]


async def test_refresh_limit_also_names_the_readable_partial_dossier(
    app, partial_built_page
) -> None:
    async with app_client(app) as client:
        responses = [
            await client.post("/api/v1/dossiers", json={"title": FIXTURE_TITLE, "refresh": True})
            for _ in range(3)
        ]

    assert responses[2].status_code == 429
    assert f"/api/v1/dossiers/{partial_built_page}" in responses[2].json()["detail"]


async def test_post_202_responses_count_against_build_limit(app) -> None:
    """Only a queued build (202) draws against the 6/minute build limit.

    Reposting the same not-yet-built title dedups to the same in-flight job each
    time (still a 202), so six requests exhaust the limit and a seventh is rejected.
    """
    async with app_client(app) as client:
        responses = [
            await client.post("/api/v1/dossiers", json={"title": NEW_TITLE}) for _ in range(7)
        ]

    for response in responses[:6]:
        assert response.status_code == 202
    assert responses[6].status_code == 429
    assert responses[6].json()["code"] == "rate_limited"
    assert responses[6].headers["retry-after"] == "60"


async def test_build_limit_exhaustion_does_not_block_reading_a_ready_dossier(
    app, built_page
) -> None:
    """A POST that resolves to an already built title never draws on the build limit.

    Ten such POSTs return 200, and once the limit is spent on another title the
    built title still answers POST with 200 and GET with 200.
    """
    async with app_client(app) as client:
        for _ in range(10):
            repeated = await client.post("/api/v1/dossiers", json={"title": FIXTURE_TITLE})
            assert repeated.status_code == 200

        for _ in range(6):
            queued = await client.post("/api/v1/dossiers", json={"title": NEW_TITLE})
            assert queued.status_code == 202
        exhausted = await client.post("/api/v1/dossiers", json={"title": NEW_TITLE})
        assert exhausted.status_code == 429

        still_ready = await client.post("/api/v1/dossiers", json={"title": FIXTURE_TITLE})
        get_response = await client.get(f"/api/v1/dossiers/{built_page}")

    assert still_ready.status_code == 200
    assert get_response.status_code == 200


async def test_post_missing_title_field_is_422(app) -> None:
    async with app_client(app) as client:
        response = await client.post("/api/v1/dossiers", json={"refresh": True})

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


async def test_post_non_boolean_refresh_is_422(app) -> None:
    async with app_client(app) as client:
        response = await client.post(
            "/api/v1/dossiers", json={"title": FIXTURE_TITLE, "refresh": "yes"}
        )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


async def test_cold_build_is_three_requests_then_warm_get_is_zero(
    redis_client, fake_redis, counting_wikimedia_client, ml_client_ok, settings
) -> None:
    wikimedia, calls = counting_wikimedia_client
    job_queue = JobQueue(redis_client, PIPELINE_VERSION, queue_cap=20)
    service = DossierService(redis_client, wikimedia, job_queue, PIPELINE_VERSION)

    admitted = await service.request_build(FIXTURE_TITLE)
    assert admitted != "ready"
    assert len(calls) == 1, calls

    await run_build(
        admitted,
        redis=redis_client,
        wikimedia=wikimedia,
        ml=ml_client_ok,
        job_queue=job_queue,
        pipeline_version=PIPELINE_VERSION,
        summary_sections=1,
        wikipedia_api_url="https://en.wikipedia.org/w/api.php",
        background=False,
    )

    assert len(calls) == 3, calls

    # rev_timestamp comes from the wm:revts cache service.request_build
    # populated at resolve time, not from a fourth Wikimedia call.
    assert admitted.rev_id is not None
    dossier_key = keys.dossier(admitted.page_id, admitted.rev_id, PIPELINE_VERSION)
    raw = await redis_client.get(dossier_key)
    dossier = Dossier.model_validate_json(raw)
    seed_pin = next(c.pin for c in dossier.citations if c.role == "seed")
    assert seed_pin.rev_timestamp == datetime.fromisoformat(FIXTURE_REV_TIMESTAMP)
    assert seed_pin.rev_timestamp != seed_pin.retrieved_at

    app = make_app(
        fake_redis,
        settings,
        wikimedia_http=wikimedia._http,
        ml_http=ml_client_ok._http,
        start_worker=True,
    )
    async with app_client(app) as client:
        response = await client.get(f"/api/v1/dossiers/{admitted.page_id}")

    assert response.status_code == 200
    assert len(calls) == 3, calls


async def test_rate_limited_post_queues_no_job_and_calls_no_wikimedia(
    redis_client, fake_redis, counting_wikimedia_client, ml_client_ok, settings
) -> None:
    """A 429 on POST /api/v1/dossiers must leave the queue and Wikimedia untouched."""
    wikimedia, calls = counting_wikimedia_client
    app = make_app(
        fake_redis,
        settings,
        wikimedia_http=wikimedia._http,
        ml_http=ml_client_ok._http,
        start_worker=False,
    )
    limiter = app.state.limiter
    build_limit = limits.parse(POST_DOSSIERS_RATE_LIMIT)
    title = "Grace Hopper"
    async with app_client(app) as client:
        first = await client.post("/api/v1/dossiers", json={"title": title})
        assert first.status_code == 202
        # Drop the job so the refused request would have to create a new one.
        job_queue: JobQueue = app.state.service._job_queue
        job = first.json()
        await redis_client.delete(keys.job(job["id"]), keys.jobkey(job["page_id"], job["rev_id"]))
        await redis_client.delete(keys.QUEUE_INTERACTIVE)
        for _ in range(5):
            assert limiter.limiter.hit(build_limit, "dossiers", "127.0.0.1")
        calls_before = len(calls)

        refused = await client.post("/api/v1/dossiers", json={"title": title})

    assert refused.status_code == 429
    assert refused.json()["code"] == "rate_limited"
    assert await job_queue.queue_depth() == 0
    assert await job_queue.get_job(job["id"]) is None
    assert not await redis_client.exists(keys.jobkey(job["page_id"], job["rev_id"]))
    assert len(calls) == calls_before


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({}, id="empty-object"),
        pytest.param({"title": ""}, id="empty-title"),
        pytest.param({"title": "x" * 256}, id="title-256-chars"),
        pytest.param({"title": "Jesus #Christ"}, id="hash"),
        pytest.param({"title": "<x>"}, id="angle-brackets"),
        pytest.param({"title": "[a]"}, id="square-brackets"),
        pytest.param({"title": "Jesus\x07Christ"}, id="control-char"),
        pytest.param({"title": "Jesus Christ\n"}, id="trailing-newline"),
        pytest.param({"title": FIXTURE_PAGE_ID}, id="non-string-title"),
        pytest.param([FIXTURE_TITLE], id="list-body"),
    ],
)
async def test_post_invalid_body_is_422(app, body) -> None:
    async with app_client(app) as client:
        response = await client.post("/api/v1/dossiers", json=body)

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "validation_error"


async def test_refresh_limit_for_an_unbuilt_title_has_a_plain_detail(app) -> None:
    async with app_client(app) as client:
        allowed = [
            await client.post("/api/v1/dossiers", json={"title": NEW_TITLE, "refresh": True})
            for _ in range(2)
        ]
        refused = await client.post("/api/v1/dossiers", json={"title": NEW_TITLE, "refresh": True})

    assert [response.status_code for response in allowed] == [202, 202]
    assert refused.status_code == 429
    assert refused.headers["retry-after"] == "3600"
    assert refused.json()["detail"] == "Refresh limit reached (2 per hour per IP)."
