"""Tests for the selectable response parts: block order, per-part content, parse_parts."""

from __future__ import annotations

import json
import re

import pytest

from tests.factories.dossier import (
    FACTORY_TITLE,
    make_fixture_dossier,
    make_freshness,
    make_links,
)
from wke.core import render
from wke.core.errors import ApiException
from wke.core.models import DossierView
from wke.core.pack.header import PROVENANCE_NOTICE
from wke.core.render.markdown import SOURCES_HEADING, SourceList
from wke.core.render.parts import (
    ALL_PARTS,
    DEFAULT_PARTS,
    Part,
    parse_parts,
    parts_code,
    response_json,
    to_response,
)

TAG_RE = re.compile(r"\[c[0-9]+\]")


def _view() -> DossierView:
    dossier = make_fixture_dossier()
    return render.build_view(
        dossier, 32000, make_freshness(dossier), make_links(dossier), include_summaries=True
    )


def _render(parts: frozenset[Part]) -> str:
    return render.render_markdown(_view(), include_summaries=True, parts=parts)


def test_blocks_come_in_fixed_order_with_the_licence_last() -> None:
    view = _view()
    text = _render(ALL_PARTS)
    title = text.index(f"# {view.topic.title}")
    first_passage = text.index("\n>")
    sources = text.index(SOURCES_HEADING)
    licence = text.index(view.license_notice)
    assert title < first_passage < sources < licence
    assert text.rstrip().endswith(view.license_notice)


def test_dossier_part_alone_is_the_bare_content_and_the_licence() -> None:
    view = _view()
    text = _render(frozenset({"dossier"}))
    assert text.startswith("##")
    assert f"# {FACTORY_TITLE}" not in text.splitlines()
    assert "Pinned at revision" not in text
    assert PROVENANCE_NOTICE not in text
    assert SOURCES_HEADING not in text.splitlines()
    assert not TAG_RE.search(text)
    assert "\n>" in text or text.startswith(">")
    assert text.rstrip().endswith(view.license_notice)


def test_sources_keep_the_markers_and_the_sources_block() -> None:
    text = _render(frozenset({"dossier", "sources"}))
    assert text.startswith("##")
    assert "Pinned at revision" not in text
    assert TAG_RE.search(text)
    assert SOURCES_HEADING in text.splitlines()


def test_metadata_adds_the_head_without_markers_or_sources() -> None:
    text = _render(frozenset({"dossier", "metadata"}))
    assert text.startswith("# ")
    assert "Pinned at revision" in text
    assert SOURCES_HEADING not in text.splitlines()
    assert not TAG_RE.search(text)


def test_dossier_part_is_the_full_content_without_marker_lines() -> None:
    full = _render(ALL_PARTS).splitlines()
    bare = _render(DEFAULT_PARTS).splitlines()
    content = full[next(i for i, line in enumerate(full) if line.startswith("##")) :]
    content = content[: content.index(SOURCES_HEADING)]
    expected = [line for line in content if not TAG_RE.fullmatch(line)]
    assert bare[: len(expected)] == expected


def test_unknown_citation_is_tagged_only_when_markers_are_on() -> None:
    view = _view()
    assert SourceList(view).tag("c99") == "[?]"
    assert SourceList(view, markers=False).tag("c99") == ""
    assert SourceList(view, markers=False).tag(view.citations[0].id) == ""


@pytest.mark.parametrize("parts", [DEFAULT_PARTS, frozenset({"dossier", "metadata"}), ALL_PARTS])
def test_json_response_carries_only_the_selected_parts(parts: frozenset[Part]) -> None:
    view = _view()
    body = json.loads(response_json(to_response(view, parts)))
    assert set(body) == {
        "schema_version",
        "license_notice",
        "dossier",
        *(p for p in parts if p != "dossier"),
    }
    assert body["license_notice"] == view.license_notice
    assert [c["id"] for c in body["dossier"]["chunks"]] == [c.id for c in view.chunks]
    if "metadata" in parts:
        assert body["metadata"]["links"]["self"] == str(view.links.self_)
        assert "self_" not in body["metadata"]["links"]
        assert body["metadata"]["budget"]["requested"] == view.budget.requested
    if "sources" in parts:
        assert [c["id"] for c in body["sources"]] == [c.id for c in view.citations]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, frozenset({"dossier"})),
        ("dossier", frozenset({"dossier"})),
        ("sources,dossier,metadata", ALL_PARTS),
        ("dossier,dossier,sources", frozenset({"dossier", "sources"})),
        (" Dossier , metadata ", frozenset({"dossier", "metadata"})),
    ],
)
def test_parse_parts_accepts_and_normalises(raw: str | None, expected: frozenset[Part]) -> None:
    assert parse_parts(raw) == expected


@pytest.mark.parametrize(
    ("raw", "detail"),
    [
        ("metadata", "parts must include dossier"),
        ("metadata,sources", "parts must include dossier"),
        ("dossier,bogus", "unknown part 'bogus'; use dossier, metadata, sources"),
        ("", "unknown part ''; use dossier, metadata, sources"),
        ("dossier,", "unknown part ''; use dossier, metadata, sources"),
    ],
)
def test_parse_parts_rejects_with_422(raw: str, detail: str) -> None:
    with pytest.raises(ApiException) as caught:
        parse_parts(raw)
    assert caught.value.status_code == 422
    assert caught.value.code == "validation_error"
    assert caught.value.detail == detail


@pytest.mark.parametrize(
    ("parts", "code"),
    [
        (frozenset({"dossier"}), "pd"),
        (frozenset({"dossier", "metadata"}), "pdm"),
        (frozenset({"dossier", "sources"}), "pds"),
        (ALL_PARTS, "pdms"),
    ],
)
def test_parts_code(parts: frozenset[Part], code: str) -> None:
    assert parts_code(parts) == code
