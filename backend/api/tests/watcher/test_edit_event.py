"""Pure pieces of the watcher: user kind, edit event fields, page id lookup, minute bucket."""

from __future__ import annotations

import pytest

from wke.clients.redis import RedisClient
from wke.core import keys
from wke.core.titles import normalize_title
from wke.watcher.stream import (
    RcEvent,
    UserKind,
    build_edit_event,
    classify_user_kind,
    minute_bucket,
    resolve_tracked_page_id,
)


@pytest.mark.parametrize(
    ("event", "kind"),
    [
        ({"user": "Example user 1"}, "registered"),
        ({"user": "192.0.2.7"}, "anonymous"),
        ({"user": "2001:db8::1"}, "anonymous"),
        ({"user": "~2026-00000-45"}, "anonymous"),
        ({"user": "ExampleBot", "bot": True}, "bot"),
        ({"user": "192.0.2.7", "bot": True}, "bot"),
        ({}, "registered"),
    ],
)
def test_classify_user_kind(event: RcEvent, kind: UserKind) -> None:
    assert classify_user_kind(event) == kind


def test_minute_bucket_is_the_utc_minute() -> None:
    assert minute_bucket(1790595540.0) == "202609281139"
    assert minute_bucket(1790595599.9) == "202609281139"
    assert minute_bucket(1790595600.0) == "202609281140"


def test_build_edit_event_maps_the_stream_fields() -> None:
    event: RcEvent = {
        "title": "Some Page",
        "user": "Example user 1",
        "comment": "secret",
        "timestamp": 1790595517,
        "revision": {"old": 100, "new": 101},
        "length": {"old": 50, "new": 42},
    }
    edit = build_edit_event(event, cursor=7, page_id=9)

    assert edit.model_dump(mode="json", exclude={"diff_url"}) == {
        "cursor": 7,
        "page_id": 9,
        "title": "Some Page",
        "rev_new": 101,
        "rev_old": 100,
        "ts": "2026-09-28T11:38:37Z",
        "user_kind": "registered",
        "byte_delta": -8,
    }


@pytest.mark.parametrize(
    "length", [{}, {"new": 60}, {"old": 50}, {"new": "60", "old": 50}, None], ids=repr
)
def test_build_edit_event_without_a_full_length_pair_has_no_byte_delta(
    length: object,
) -> None:
    edit = build_edit_event({"title": "T", "length": length}, cursor=1, page_id=None)
    assert edit.byte_delta is None


def test_build_edit_event_defaults_a_sparse_event() -> None:
    edit = build_edit_event({"title": "T"}, cursor=1, page_id=None)
    assert (edit.page_id, edit.rev_new, edit.rev_old) == (None, 0, None)


async def test_resolve_tracked_page_id_reads_the_title_hash(redis_client: RedisClient) -> None:
    await redis_client.hset(keys.TRACKED_PAGE_IDS, normalize_title("Some Page"), "123")
    assert await resolve_tracked_page_id(redis_client, "Some_Page") == 123


@pytest.mark.parametrize("title", ["Unknown_Page", "", "[bad]"])
async def test_resolve_tracked_page_id_misses_are_none(
    redis_client: RedisClient, title: str
) -> None:
    assert await resolve_tracked_page_id(redis_client, title) is None


async def test_resolve_tracked_page_id_ignores_a_corrupt_entry(redis_client: RedisClient) -> None:
    await redis_client.hset(keys.TRACKED_PAGE_IDS, normalize_title("Some Page"), "not-a-number")
    assert await resolve_tracked_page_id(redis_client, "Some_Page") is None
