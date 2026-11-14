"""GET /metrics: every metric added in wke.metrics carries the expected
labels once the code path that touches it has actually run.

Counters are module-global and shared across the whole test session, so
assertions here check for a label combination's presence or the delta
this test's own actions produced, never an absolute counter value.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime

import pytest

from tests.support.apps import app_client
from tests.support.constants import FIXTURE_TITLE
from tests.support.metrics import metric_sample
from tests.support.snapshots import make_snapshot
from wke import metrics
from wke.clients.redis import RedisClient
from wke.core import keys

NEVER_BUILT_PAGE_ID = 999999999


async def test_metrics_route_reports_http_cache_and_pipeline_metrics(
    app, built_page, redis_client: RedisClient
) -> None:
    """A search, a dossier miss/hit and the built_page cold build all show up."""
    # A ptr with no matching dossier: get_dossier_view reaches its dossier
    # cache lookup (and misses), rather than bailing out earlier on a
    # missing ptr, which never touches the "dossier" cache kind at all.
    await redis_client.set(keys.ptr(NEVER_BUILT_PAGE_ID), json.dumps({"rev_id": 1}))

    before_search_miss = metric_sample(
        "wke_cache_requests_total", {"kind": "search", "result": "miss"}
    )
    before_search_hit = metric_sample(
        "wke_cache_requests_total", {"kind": "search", "result": "hit"}
    )
    before_dossier_miss = metric_sample(
        "wke_cache_requests_total", {"kind": "dossier", "result": "miss"}
    )
    before_dossier_hit = metric_sample(
        "wke_cache_requests_total", {"kind": "dossier", "result": "hit"}
    )

    async with app_client(app) as client:
        await client.get("/api/v1/search", params={"q": FIXTURE_TITLE})
        await client.get("/api/v1/search", params={"q": FIXTURE_TITLE})

        await client.get(f"/api/v1/dossiers/{NEVER_BUILT_PAGE_ID}")
        await client.get(f"/api/v1/dossiers/{built_page}")

        response = await client.get("/metrics")

    assert response.status_code == 200
    body = response.text

    assert 'wke_http_requests_total{method="GET",route="/api/v1/search",status_class="2xx"}' in body
    assert (
        'wke_http_requests_seconds_count{method="GET",route="/api/v1/search",'
        'status_class="2xx"}' in body
    )

    # search: one miss (first call), one hit (second, identical call).
    assert (
        metric_sample("wke_cache_requests_total", {"kind": "search", "result": "miss"})
        == before_search_miss + 1
    )
    assert (
        metric_sample("wke_cache_requests_total", {"kind": "search", "result": "hit"})
        == before_search_hit + 1
    )
    # dossier: one miss (never-built page), one hit (built_page).
    assert (
        metric_sample("wke_cache_requests_total", {"kind": "dossier", "result": "miss"})
        == before_dossier_miss + 1
    )
    assert (
        metric_sample("wke_cache_requests_total", {"kind": "dossier", "result": "hit"})
        == before_dossier_hit + 1
    )

    # html/related/sum: cache misses from the built_page fixture's cold build
    # (fresh fake_redis, so every one of these is a first-time miss).
    assert 'wke_cache_requests_total{kind="html",result="miss"}' in body
    assert 'wke_cache_requests_total{kind="related",result="miss"}' in body
    assert 'wke_cache_requests_total{kind="sum",result="miss"}' in body

    # build/summarize stage timing comes from the built_page fixture's own
    # pipeline.run_build/run_summary_item calls (fixture setup, not this
    # test's HTTP calls), so only presence is checked, not a delta.
    assert 'wke_job_stage_seconds_count{stage="build"}' in body
    assert 'wke_job_stage_seconds_count{stage="summarize"}' in body
    assert 'wke_dossier_build_seconds_count{analysis="ml",outcome="complete"}' in body

    assert 'wke_wikimedia_requests_total{op="action",status="200"}' in body
    assert 'wke_wikimedia_requests_total{op="rest",status="200"}' in body


async def test_metrics_route_reports_queue_depth_and_trending_timestamp(
    app, redis_client: RedisClient
) -> None:
    await redis_client.rpush(keys.QUEUE_INTERACTIVE, "job-a")
    generated_at = datetime(2026, 9, 27, 3, 0, tzinfo=UTC)
    snapshot = make_snapshot(topics=[], generated_at=generated_at.isoformat())
    await redis_client.set(keys.TRENDING_LATEST, json.dumps(snapshot))

    async with app_client(app) as client:
        response = await client.get("/metrics")

    body = response.text
    # A plain .set() gauge, not a counter: exact value is safe even with
    # other tests sharing the process-wide registry, since fake_redis
    # (and so the queue this reads) is fresh per test.
    assert 'wke_jobs_queued{queue="q:interactive"} 1.0' in body
    match = re.search(r"^wke_trending_last_success_timestamp (\S+)$", body, re.MULTILINE)
    assert match is not None
    assert float(match.group(1)) == pytest.approx(generated_at.timestamp())


def _get_metric_family_names() -> list[str]:
    """Extract metric family names from metrics module."""
    names = []
    for attr_name in dir(metrics):
        attr = getattr(metrics, attr_name)
        if hasattr(attr, "_name"):
            names.append(attr._name)
    return sorted(names)


async def test_metrics_contains_all_families(app) -> None:
    expected_names = _get_metric_family_names()
    async with app_client(app) as client:
        response = await client.get("/metrics")
        body = response.text
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]
        for name in expected_names:
            assert name in body, f"Metric {name} not found in /metrics response"


async def test_unmatched_path_uses_bounded_route_label(app) -> None:
    """A scanner path must not become a label value (cardinality, title leak)."""
    async with app_client(app) as client:
        await client.get("/wp-login-probe-9f3a")
        body = (await client.get("/metrics")).text
    assert "wp-login-probe-9f3a" not in body
    assert re.search(r'wke_http_requests_total\{[^}]*route="unmatched"', body)
