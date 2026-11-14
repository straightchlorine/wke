"""Tests for wke.offline.validate over stored dossiers and cached HTML."""

from __future__ import annotations

from datetime import UTC, datetime

import fakeredis

from tests.support.constants import PIPELINE_VERSION
from tests.support.offline import cache_html, store_dossier
from tests.support.wikimedia import WmFixtures
from wke.core import keys
from wke.core.citations import seed_pin
from wke.core.models import Dossier
from wke.core.models.budgets import BUDGETS
from wke.jobs.build.payload import ptr_json
from wke.offline.validate import validate_stored

NO_MATCHING_HEADINGS = "<html><body><h2 id='Other'>Other</h2></body></html>"


def test_validate_stored_skips_anchor_checks_while_the_html_cache_is_cold(
    client: fakeredis.FakeRedis, stored: Dossier
):
    result = validate_stored(client)
    assert result["dossiers_checked"] == 1
    assert result["problem_count"] == 0
    assert result["totals"]["passages"] > 0
    assert result["totals"]["anchors_skipped"] > 0
    assert "anchors_checked" not in result["totals"]


def test_validate_stored_checks_anchors_against_the_cached_headings(
    client: fakeredis.FakeRedis, stored: Dossier, wm_fixtures: WmFixtures
):
    cache_html(client, seed_pin(stored).rev_id, wm_fixtures.text("parsoid.html"))
    result = validate_stored(client, budgets=(2000, 8000))
    assert result["totals"]["anchors_checked"] > 0
    assert result["problem_count"] == 0


def test_validate_stored_reports_problems_with_page_id_and_budget(
    client: fakeredis.FakeRedis, stored: Dossier
):
    cache_html(client, seed_pin(stored).rev_id, NO_MATCHING_HEADINGS)
    result = validate_stored(client, budgets=(2000,))
    assert result["problem_count"] == result["totals"]["bad_anchor"] > 0
    assert result["problems"][0].startswith(f"{stored.topic.page_id}@2000 bad_anchor: ")


def test_validate_stored_lists_at_most_30_problems_but_counts_all(
    client: fakeredis.FakeRedis, stored: Dossier
):
    for page_id in range(1, 5):
        copy = stored.model_copy(
            update={"topic": stored.topic.model_copy(update={"page_id": page_id})}
        )
        store_dossier(client, copy)
    cache_html(client, seed_pin(stored).rev_id, NO_MATCHING_HEADINGS)
    result = validate_stored(client)
    assert result["problem_count"] > 30
    assert len(result["problems"]) == 30


def test_validate_stored_with_reparse_counts_a_cold_html_dossier_as_skipped(
    client: fakeredis.FakeRedis, stored: Dossier
):
    result = validate_stored(client, do_reparse=True)
    assert result["skipped_cold_html"] == 1
    assert result["dossiers_checked"] == 0


def test_validate_stored_with_reparse_validates_the_dossier_the_parser_builds(
    client: fakeredis.FakeRedis, stored: Dossier, wm_fixtures: WmFixtures
):
    cache_html(client, seed_pin(stored).rev_id, wm_fixtures.text("parsoid.html"))
    plain = validate_stored(client)
    reparsed = validate_stored(client, do_reparse=True)
    assert reparsed["dossiers_checked"] == 1
    assert reparsed["problem_count"] == 0
    assert reparsed["totals"]["passages"] > plain["totals"]["passages"]


def test_validate_stored_sums_the_counts_of_the_three_default_budgets(
    client: fakeredis.FakeRedis, stored: Dossier
):
    default = validate_stored(client)["totals"]
    per_budget = [validate_stored(client, budgets=(budget,))["totals"] for budget in BUDGETS]
    assert default == {k: sum(t[k] for t in per_budget) for k in default}


def test_validate_stored_ignores_a_pointer_whose_dossier_has_expired(
    client: fakeredis.FakeRedis, stored: Dossier
):
    client.set(keys.ptr(7), ptr_json(1, PIPELINE_VERSION, datetime.now(UTC)))
    assert validate_stored(client)["dossiers_checked"] == 1


def test_validate_stored_only_checks_the_requested_pages(
    client: fakeredis.FakeRedis, stored: Dossier
):
    assert validate_stored(client, page_ids=[stored.topic.page_id + 1])["dossiers_checked"] == 0
    assert validate_stored(client, page_ids=[stored.topic.page_id])["dossiers_checked"] == 1
