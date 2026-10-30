"""Hashed keys: equal inputs share a key, any change to an input gets a new one."""

from __future__ import annotations

import re

import pytest

from wke.core import keys

SUMMARY: tuple[str, str, str, str] = (
    "Jesus taught in Galilee.",
    "sshleifer/distilbart-cnn-6-6",
    "d2fde4ca",
    "1|30|96",
)


def test_summary_key_depends_only_on_its_inputs() -> None:
    # No page or revision in the key, since an unchanged section keeps its summary
    # across an edit of the article.
    key = keys.sum_key(*SUMMARY)
    assert key == keys.sum_key(*SUMMARY)
    assert re.fullmatch(r"sum:[0-9a-f]{64}", key)


@pytest.mark.parametrize("position", range(len(SUMMARY)))
def test_summary_key_changes_with_each_input(position: int) -> None:
    changed: list[str] = list(SUMMARY)
    changed[position] += "x"
    text, model, revision, params = changed
    assert keys.sum_key(text, model, revision, params) != keys.sum_key(*SUMMARY)


def test_search_key_separates_query_and_limit() -> None:
    assert keys.wm_search("Jesus", 8) == keys.wm_search("Jesus", 8)
    assert keys.wm_search("Jesus", 8) != keys.wm_search("Jesus", 10)
    assert keys.wm_search("Jesus", 8) != keys.wm_search("jesus", 8)
