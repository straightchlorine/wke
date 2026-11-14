"""The pack coverage script says how the top sections of a stored dossier reach a pack."""

from __future__ import annotations

import fakeredis
import pytest

from tests.factories.dossier import FACTORY_TITLE, make_budget_dossier, make_fixture_dossier
from tests.support.offline import store_dossier
from tests.support.scripts import load_script

coverage = load_script("pack_coverage.py")


def test_classify_says_how_each_top_section_reaches_the_pack() -> None:
    rows = coverage.classify(make_budget_dossier(), 2000)
    assert [(label, how) for label, how, _ in rows] == [
        ("Huger", "none"),
        ("Huge", "summary"),
        ("Busy", "passage"),
    ]
    scores = [score for _, _, score in rows]
    assert scores == sorted(scores, reverse=True)


def test_classify_with_everything_lists_every_ranked_section() -> None:
    dossier = make_budget_dossier()
    assert len(coverage.classify(dossier, 2000, everything=True)) > len(
        coverage.classify(dossier, 2000)
    )


@pytest.mark.parametrize("title", [FACTORY_TITLE, FACTORY_TITLE.lower()])
def test_find_dossier_matches_a_stored_title_in_any_case(title: str) -> None:
    client = fakeredis.FakeRedis(decode_responses=True)
    store_dossier(client, make_fixture_dossier())
    found = coverage.find_dossier(client, title)
    assert found is not None
    assert found.topic.title == FACTORY_TITLE


def test_find_dossier_is_none_for_an_unknown_title() -> None:
    assert coverage.find_dossier(fakeredis.FakeRedis(decode_responses=True), "Ghost") is None
