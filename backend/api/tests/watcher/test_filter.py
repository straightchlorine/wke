"""Cheapest-first recentchange filter: wiki, namespace, type, canary, bot."""

from __future__ import annotations

import json

import pytest

from tests.support.constants import FIXTURE_TITLE
from tests.support.metrics import metric_sample
from wke.watcher.stream import RcEvent, looks_like_enwiki, parse_kept_event

BASE_EVENT: RcEvent = {
    "wiki": "enwiki",
    "type": "edit",
    "namespace": 0,
    "title": FIXTURE_TITLE,
    "bot": False,
    "user": "SomeEditor",
    "timestamp": 1790595517,
    "revision": {"old": 100, "new": 101},
    "length": {"old": 50, "new": 60},
    "meta": {"domain": "en.wikipedia.org"},
}


def _event(**overrides: object) -> str:
    payload = dict(BASE_EVENT)
    payload.update(overrides)
    return json.dumps(payload, separators=(",", ":"))


def _kind_count(kind: str) -> float:
    return metric_sample("wke_watcher_events_total", {"kind": kind})


def test_looks_like_enwiki_substring_check() -> None:
    assert looks_like_enwiki(_event())
    assert not looks_like_enwiki(_event(wiki="jawiki"))


def test_enwiki_ns0_edit_is_kept_and_counted() -> None:
    before = _kind_count("kept")
    kept = parse_kept_event(_event())
    assert kept is not None
    assert kept["title"] == FIXTURE_TITLE
    assert _kind_count("kept") == before + 1


@pytest.mark.parametrize(
    ("raw", "kind"),
    [
        (_event(wiki="jawiki"), "other_wiki"),
        # Passes the substring pre-filter, then fails the exact wiki check.
        ('{"wiki":"jawiki","origin":{"wiki":"enwiki"}}', "other_wiki"),
        # Not parsed at all: the substring pre-filter rejects it first.
        ("not json at all", "other_wiki"),
        (_event(namespace=2), "non_article_ns"),
        (_event(type="categorize"), "non_edit_type"),
        (_event(bot=True), "bot"),
        (_event(meta={"domain": "canary"}), "canary"),
        ('{"wiki":"enwiki", not json', "unparseable"),
        ('["wiki","enwiki"] "wiki":"enwiki"', "unparseable"),
        ('[{"wiki":"enwiki"}]', "unparseable"),
    ],
)
def test_dropped_event_is_counted_by_reason(raw: str, kind: str) -> None:
    before = _kind_count(kind)
    kept_before = _kind_count("kept")
    assert parse_kept_event(raw) is None
    assert _kind_count(kind) == before + 1
    assert _kind_count("kept") == kept_before
