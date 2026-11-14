"""Trending snapshot and live edit stream models."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import Field, HttpUrl

from wke.core.models.base import WkeModel
from wke.core.models.catalog import DossierState
from wke.core.models.dossier import GraphEdge


class TrendingTopic(WkeModel):
    """One most-read topic of the trending snapshot."""

    rank: int
    page_id: int
    title: str
    description: str | None = None
    views: int
    rev_id: int
    lead_excerpt: str | None = Field(default=None, max_length=280)
    dossier_state: DossierState
    edits_last_hour: int | None = None


class TrendingSnapshot(WkeModel):
    """Yesterday's most-read topics with their similarity graph."""

    schema_version: Literal["1"] = "1"
    date: date
    source: Literal["wikifeeds_mostread", "pageviews_top"]
    source_url: HttpUrl | None = None
    generated_at: datetime
    next_refresh: datetime | None = None
    topics: list[TrendingTopic] = Field(max_length=40)
    edges: list[GraphEdge]


class EditEvent(WkeModel):
    """One edit of a tracked page from the Recent Changes stream."""

    cursor: int
    page_id: int | None = None
    title: str
    rev_new: int
    rev_old: int | None = None
    ts: datetime
    user_kind: Literal["registered", "anonymous", "bot"]
    byte_delta: int | None = None
    diff_url: HttpUrl | None = None


class LiveCounters(WkeModel):
    """Rolling edit and build counters of the live feed."""

    enwiki_edits_last_hour: int
    tracked_edits_last_hour: int
    window_complete: bool
    window_since: datetime | None = None
    dossiers_built_today: int
    topics_tracked: int
    index_date: date | None = None
    next_refresh: datetime | None = None


class LiveResponse(WkeModel):
    """The live feed: recent edits, cursor, stream state and counters."""

    stream: Literal["connected", "reconnecting", "down"]
    server_time: datetime
    cursor: int
    last_event_at: datetime | None = None
    edits: list[EditEvent] = Field(max_length=50)
    counters: LiveCounters
