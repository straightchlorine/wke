"""SSEParser: incremental line parsing, robust to arbitrary chunk splits."""

from __future__ import annotations

from collections.abc import Iterable

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from wke.watcher.stream import SSEEvent, SSEParser


def _split_by_sizes(data: bytes, sizes: list[int]) -> list[bytes]:
    """Split data into consecutive chunks of the given (cycled) sizes.

    Args:
        data: bytes to split.
        sizes: chunk sizes, cycled until data is exhausted.

    Returns:
        list[bytes]: chunks that concatenate back to data exactly.
    """
    chunks: list[bytes] = []
    index = 0
    position = 0
    total = len(data)
    while position < total:
        size = sizes[index % len(sizes)]
        chunks.append(data[position : position + size])
        position += size
        index += 1
    return chunks


def _events_from_chunks(chunks: Iterable[bytes]) -> list[SSEEvent]:
    parser = SSEParser()
    events: list[SSEEvent] = []
    for chunk in chunks:
        events.extend(parser.feed(chunk))
    return events


def test_whole_fixture_parses_to_events(sse_bytes: bytes) -> None:
    events = _events_from_chunks([sse_bytes])
    assert len(events) == 200
    assert all(event.event == "message" for event in events)
    assert all(event.id is not None for event in events)


def test_byte_by_byte_split_matches_whole(sse_bytes: bytes) -> None:
    baseline = _events_from_chunks([sse_bytes])
    byte_by_byte = _events_from_chunks(sse_bytes[i : i + 1] for i in range(len(sse_bytes)))
    assert byte_by_byte == baseline


@given(chunk_sizes=st.lists(st.integers(min_value=1, max_value=97), min_size=1, max_size=40))
@settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_arbitrary_chunk_split_matches_whole(sse_bytes: bytes, chunk_sizes: list[int]) -> None:
    baseline = _events_from_chunks([sse_bytes])
    split_chunks = _split_by_sizes(sse_bytes, chunk_sizes)
    assert _events_from_chunks(split_chunks) == baseline


def test_multiline_data_field_joins_with_newline() -> None:
    parser = SSEParser()
    events = parser.feed(b"event: message\nid: 1\ndata: line1\ndata: line2\n\n")
    assert events == [SSEEvent(id="1", event="message", data="line1\nline2")]


def test_comment_lines_ignored() -> None:
    parser = SSEParser()
    events = parser.feed(b": heartbeat\nid: 2\ndata: payload\n\n")
    assert events == [SSEEvent(id="2", event="message", data="payload")]


def test_id_persists_across_events_when_not_resent() -> None:
    parser = SSEParser()
    events = parser.feed(b"id: 5\ndata: a\n\ndata: b\n\n")
    assert [event.id for event in events] == ["5", "5"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (b"id: 1\r\ndata: a\r\n\r\n", [SSEEvent(id="1", event="message", data="a")]),
        (b"data:a\n\n", [SSEEvent(id=None, event="message", data="a")]),
        (
            b"event: ping\ndata: a\n\ndata: b\n\n",
            [
                SSEEvent(id=None, event="ping", data="a"),
                SSEEvent(id=None, event="message", data="b"),
            ],
        ),
        (b"retry: 10\nunknown: x\ndata: a\n\n", [SSEEvent(id=None, event="message", data="a")]),
        (b"event: ping\n\ndata: a\n\n", [SSEEvent(id=None, event="message", data="a")]),
        (b"data: a\n", []),
        (b"data: caf\xff\n\n", [SSEEvent(id=None, event="message", data="caf\ufffd")]),
    ],
    ids=[
        "crlf",
        "no-space-after-colon",
        "event-type-resets",
        "unknown-fields-ignored",
        "no-data-no-event",
        "undispatched-until-blank-line",
        "invalid-utf8-replaced",
    ],
)
def test_line_level_rules(raw: bytes, expected: list[SSEEvent]) -> None:
    assert SSEParser().feed(raw) == expected
