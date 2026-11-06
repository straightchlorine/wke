"""Tests for wke.trending.filters."""

from __future__ import annotations

import pytest

from tests.support.constants import FIXTURE_TITLE
from wke.trending.filters import is_trending_candidate, select_candidates


@pytest.mark.parametrize(
    "raw_title",
    [
        "Main_Page",
        "-",
        "Special:Search",
        "Wikipedia:Featured_pictures",
        "File:Example.jpg",
        "Portal:Current_events",
        "Help:Contents",
        "Template:Infobox",
        "Category:Living_people",
        f"Talk:{FIXTURE_TITLE}",
        "User:Example",
        "Draft:New_article",
        "Module:Citation",
        "List_of_countries",
        "List of countries",
        "Deaths_in_2026",
        "Deaths in 2026",
        "2026",
    ],
)
def test_filtered_titles_are_rejected(raw_title: str) -> None:
    assert is_trending_candidate(raw_title) is False


@pytest.mark.parametrize("raw_title", ["Lizzie_Borden", "Ted Kaczynski", "Roblox"])
def test_ordinary_titles_pass(raw_title: str) -> None:
    assert is_trending_candidate(raw_title) is True


def test_select_candidates_filters_and_caps() -> None:
    items = [
        {"raw_title": "Main_Page"},
        {"raw_title": "Lizzie_Borden"},
        {"raw_title": "Ted_Kaczynski"},
        {"raw_title": "List_of_countries"},
        {"raw_title": "Roblox"},
    ]
    result = select_candidates(items, limit=2)
    assert [item["raw_title"] for item in result] == ["Lizzie_Borden", "Ted_Kaczynski"]


def test_select_candidates_dedupes_by_normalized_title() -> None:
    items = [{"raw_title": "Lizzie_Borden"}, {"raw_title": "Lizzie Borden"}]
    result = select_candidates(items, limit=40)
    assert result == [{"raw_title": "Lizzie_Borden"}]
