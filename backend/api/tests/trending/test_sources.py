"""Tests for wke.trending.sources.fetch_mostread_with_fallback."""

from __future__ import annotations

import httpx
import pytest

from tests.support.trending import FeedAnswer, feed_answer, feed_article, logged, trending_handler
from tests.support.wikimedia import WmFixtures, make_wikimedia_client
from wke.clients.redis import RedisClient
from wke.core.errors import ApiException
from wke.trending.filters import select_candidates
from wke.trending.sources import fetch_mostread_with_fallback

# mostread.json was recorded from the feed of 2026-09-27, which carries the
# most-read list of 2026-09-26.
TARGET_DATE = "2026-09-26"
FEED_DATE_PATH = "feed/featured/2026/09/27"


def _counting_sleep(calls: list[float]):
    async def sleep(seconds: float) -> None:
        calls.append(seconds)

    return sleep


def _feed_status(status: int, text: str = "") -> FeedAnswer:
    return lambda _request: httpx.Response(status, text=text)


async def test_mostread_rows_come_from_the_feed_of_the_next_day(
    redis_client: RedisClient, wm_fixtures: WmFixtures
) -> None:
    log: list[str] = []
    wikimedia = make_wikimedia_client(redis_client, logged(trending_handler(wm_fixtures), log))

    rows, source = await fetch_mostread_with_fallback(wikimedia, TARGET_DATE, _counting_sleep([]))

    assert source == "wikifeeds_mostread"
    assert [url for url in log if "feed/featured" in url][0].endswith(FEED_DATE_PATH)
    assert len(log) == 1
    recorded = wm_fixtures.json("mostread.json")["articles"]
    assert len(rows) == len(recorded)
    assert rows[0] == {
        "raw_title": recorded[0]["title"],
        "title": recorded[0]["normalizedtitle"],
        "page_id": recorded[0]["pageid"],
        "rev_id": int(recorded[0]["revision"]),
        "description": recorded[0]["description"],
        "views": recorded[0]["views"],
        "extract": recorded[0]["extract"],
    }


async def test_mostread_entries_without_page_id_or_revision_are_dropped(
    redis_client: RedisClient, wm_fixtures: WmFixtures
) -> None:
    articles = [
        feed_article(wm_fixtures, 0),
        feed_article(wm_fixtures, 1, pageid=None),
        feed_article(wm_fixtures, 2, revision=None),
    ]
    handler = trending_handler(wm_fixtures, feed_answer(wm_fixtures, articles=articles))
    wikimedia = make_wikimedia_client(redis_client, handler)

    rows, _source = await fetch_mostread_with_fallback(wikimedia, TARGET_DATE, _counting_sleep([]))

    assert [row["page_id"] for row in rows] == [articles[0]["pageid"]]


async def test_mostread_titles_fall_back_between_title_and_normalizedtitle(
    redis_client: RedisClient, wm_fixtures: WmFixtures
) -> None:
    articles = [
        feed_article(wm_fixtures, 0, title="Under_score_title", normalizedtitle=None),
        feed_article(wm_fixtures, 1, title=None, normalizedtitle="Normalized name"),
    ]
    handler = trending_handler(wm_fixtures, feed_answer(wm_fixtures, articles=articles))
    wikimedia = make_wikimedia_client(redis_client, handler)

    rows, _source = await fetch_mostread_with_fallback(wikimedia, TARGET_DATE, _counting_sleep([]))

    assert [(row["raw_title"], row["title"]) for row in rows] == [
        ("Under_score_title", "Under score title"),
        ("Normalized name", "Normalized name"),
    ]


async def test_persistent_404_retries_for_the_whole_budget_then_falls_back(
    redis_client: RedisClient, wm_fixtures: WmFixtures
) -> None:
    handler = trending_handler(wm_fixtures, _feed_status(404))
    wikimedia = make_wikimedia_client(redis_client, handler)
    sleeps: list[float] = []

    _rows, source = await fetch_mostread_with_fallback(
        wikimedia, TARGET_DATE, _counting_sleep(sleeps)
    )

    assert source == "pageviews_top"
    # Retries every 60 s for 10 minutes before giving up on the feed.
    assert sleeps == [60] * 10


async def test_404_once_then_recovers_without_falling_back(
    redis_client: RedisClient, wm_fixtures: WmFixtures
) -> None:
    answers = iter([_feed_status(404), feed_answer(wm_fixtures)])
    handler = trending_handler(wm_fixtures, lambda request: next(answers)(request))
    wikimedia = make_wikimedia_client(redis_client, handler)
    sleeps: list[float] = []

    _rows, source = await fetch_mostread_with_fallback(
        wikimedia, TARGET_DATE, _counting_sleep(sleeps)
    )

    assert source == "wikifeeds_mostread"
    assert sleeps == [60]


async def test_persistent_5xx_falls_back_without_the_404_retry_loop(
    redis_client: RedisClient, wm_fixtures: WmFixtures
) -> None:
    handler = trending_handler(wm_fixtures, _feed_status(500, "oops"))
    wikimedia = make_wikimedia_client(redis_client, handler)
    sleeps: list[float] = []

    _rows, source = await fetch_mostread_with_fallback(
        wikimedia, TARGET_DATE, _counting_sleep(sleeps)
    )

    assert source == "pageviews_top"
    assert sleeps == []


@pytest.mark.parametrize("carried_date", ["2026-09-25Z", "2026-09-27Z", None])
async def test_feed_carrying_another_date_falls_back(
    redis_client: RedisClient, wm_fixtures: WmFixtures, carried_date: str | None
) -> None:
    handler = trending_handler(wm_fixtures, feed_answer(wm_fixtures, date=carried_date))
    wikimedia = make_wikimedia_client(redis_client, handler)

    _rows, source = await fetch_mostread_with_fallback(wikimedia, TARGET_DATE, _counting_sleep([]))

    assert source == "pageviews_top"


async def test_rate_limited_feed_is_not_swallowed_by_the_fallback(
    redis_client: RedisClient, wm_fixtures: WmFixtures
) -> None:
    handler = trending_handler(wm_fixtures, _feed_status(429))
    wikimedia = make_wikimedia_client(redis_client, handler)

    with pytest.raises(ApiException) as caught:
        await fetch_mostread_with_fallback(wikimedia, TARGET_DATE, _counting_sleep([]))

    assert caught.value.code == "upstream_rate_limited"


async def test_pageviews_fallback_filters_caps_and_drops_missing_pages(
    redis_client: RedisClient, wm_fixtures: WmFixtures
) -> None:
    log: list[str] = []
    top = wm_fixtures.json("pageviews_top.json")["items"][0]["articles"]
    views = {row["article"]: row["views"] for row in top}
    expected = [
        row["raw_title"]
        for row in select_candidates([{"raw_title": title} for title in views], limit=40)
    ]
    missing = expected.pop(1)
    handler = trending_handler(
        wm_fixtures, _feed_status(500), missing_titles=frozenset({missing.replace("_", " ")})
    )
    wikimedia = make_wikimedia_client(redis_client, logged(handler, log))

    rows, source = await fetch_mostread_with_fallback(wikimedia, TARGET_DATE, _counting_sleep([]))

    assert source == "pageviews_top"
    assert [row["raw_title"] for row in rows] == expected
    assert len(rows) == 39
    # 40 titles, 20 per TextExtracts call.
    assert len([url for url in log if "/w/api.php" in url]) == 2
    sample = rows[0]
    assert sample["views"] == views[sample["raw_title"]]
    assert sample["rev_id"] == sample["page_id"] + 1
    assert sample["extract"] == f"Extract for {sample['title']}."
