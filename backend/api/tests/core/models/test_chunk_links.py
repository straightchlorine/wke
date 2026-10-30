"""Chunk.links: the optional link spans of a passage."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from wke.core.models import Chunk, LinkSpan


def _chunk(links: list[LinkSpan] | None = None) -> Chunk:
    return Chunk(
        id="1:0:0",
        citation_id="c1",
        heading_path=[],
        order=0,
        text="Turing studied at King's College.",
        est_tokens=9,
        relevance=0.5,
        links=links or [],
    )


def test_links_default_to_empty_so_stored_dossiers_still_load() -> None:
    assert _chunk().links == []
    assert Chunk.model_validate(_chunk().model_dump(exclude={"links"})).links == []


def test_a_link_span_round_trips_through_json() -> None:
    chunk = _chunk(links=[LinkSpan(start=18, end=32, title="King's College, Cambridge")])
    again = Chunk.model_validate_json(chunk.model_dump_json())
    assert again.links == [LinkSpan(start=18, end=32, title="King's College, Cambridge")]


@pytest.mark.parametrize(("start", "end"), [(5, 5), (7, 3), (-1, 4)])
def test_a_link_span_must_cover_at_least_one_character(start: int, end: int) -> None:
    with pytest.raises(ValidationError):
        LinkSpan(start=start, end=end, title="X")


def test_unknown_fields_of_a_link_span_are_rejected() -> None:
    with pytest.raises(ValidationError):
        LinkSpan.model_validate({"start": 0, "end": 1, "title": "X", "href": "./X"})
