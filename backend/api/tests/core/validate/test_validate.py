"""The dossier validator: a sound view passes, each rule catches its own defect."""

from __future__ import annotations

from collections.abc import Callable, Mapping

import pytest

from tests.factories.dossier import make_fixture_view, make_heading_map
from wke.core.models import ChunkKind, DossierView, FormulaSpan
from wke.core.validate import heading_map, validate_view

Headings = Callable[[int], Mapping[str, str] | None]


def _with_chunk(kind: ChunkKind, update: dict[str, object]) -> DossierView:
    """Return the fixture view with its first chunk of a kind changed.

    The fixture has no list chunk; a list case turns its table into one.
    """
    view = make_fixture_view()
    target = next(c for c in view.chunks if c.kind == kind)
    chunks = [c.model_copy(update=update) if c is target else c for c in view.chunks]
    return view.model_copy(update={"chunks": chunks})


def _with_summary(update: dict[str, object]) -> DossierView:
    """Return the fixture view with its summary changed."""
    view = make_fixture_view()
    sections = [
        s.model_copy(update={"summary": s.summary.model_copy(update=update)}) if s.summary else s
        for s in view.sections
    ]
    return view.model_copy(update={"sections": sections})


def test_a_sound_view_passes_and_checks_every_anchor() -> None:
    view = make_fixture_view()
    headings = make_heading_map(view)
    report = validate_view(view, None, lambda _rev: headings)
    assert report.ok, report.problems
    assert report.counts["anchors_checked"] == len(headings) > 0


def _cold_cache(_rev: int) -> None:
    """Stand for a revision whose HTML is not cached."""
    return None


@pytest.mark.parametrize("headings", [None, _cold_cache], ids=["not-given", "cold-cache"])
def test_without_revision_html_the_anchor_checks_are_skipped(headings: Headings | None) -> None:
    report = validate_view(make_fixture_view(), None, headings)
    assert report.ok
    assert report.counts["anchors_checked"] == 0 and report.counts["anchors_skipped"] > 0


@pytest.mark.parametrize(
    ("kind", "update", "rule"),
    [
        ("prose", {"text": "Jesus taught in Galilee during the"}, "fragment_passages"),
        ("prose", {"text": "and then he left."}, "fragment_passages"),
        ("prose", {"text": "See also the article on Nazareth."}, "navigation_passages"),
        ("prose", {"citation_id": "c2"}, "wrong_chunk_citation"),
        ("prose", {"id": "1:nowhere:0"}, "orphan_chunk"),
        (
            "prose",
            {"text": "The parts are:", "heading_path": ["Public ministry"]},
            "fragment_passages",
        ),
        (
            "table",
            {"text": "Settings\n| Setting | Region |\n| --- | --- |\n| Galilee | No"},
            "cut_table_row",
        ),
        ("table", {"kind": "list", "text": "- a\nstray text"}, "cut_list_item"),
        ("facts", {"text": "Born: c. 6 to 4 BC\nBethlehem"}, "cut_fact_row"),
    ],
    ids=[
        "stops-mid-sentence",
        "starts-mid-sentence",
        "navigation",
        "wrong-citation",
        "in-no-section",
        "headed-passage-ending-on-a-colon",
        "cut-table-row",
        "cut-list-item",
        "cut-fact-row",
    ],
)
def test_a_defective_chunk_is_reported(
    kind: ChunkKind, update: dict[str, object], rule: str
) -> None:
    report = validate_view(_with_chunk(kind, update))
    assert report.counts[rule] == 1
    assert not report.ok and len(report.problems) == 1


@pytest.mark.parametrize(
    "update",
    [
        {"text": "The value is therefore x=1", "formulas": [FormulaSpan(start=23, end=26)]},
        {"text": "The topics covered are:", "heading_path": []},
    ],
    ids=["ends-on-an-equation", "lead-introduction"],
)
def test_a_passage_the_parser_keeps_is_not_a_fragment(update: dict[str, object]) -> None:
    assert validate_view(_with_chunk("prose", update)).ok


def test_key_facts_listed_in_the_lead_cite_the_section_that_holds_the_infobox() -> None:
    view = make_fixture_view()
    facts = next(c for c in view.chunks if c.kind == "facts")
    home = view.sections[2]
    moved = facts.model_copy(update={"id": f"1:{home.id}:facts", "citation_id": home.citation_id})
    chunks = [moved if c is facts else c for c in view.chunks]
    lead = view.sections[0]
    listed = [moved.id if cid == facts.id else cid for cid in lead.chunk_ids]
    sections = [lead.model_copy(update={"chunk_ids": listed}), *view.sections[1:]]
    assert validate_view(view.model_copy(update={"chunks": chunks, "sections": sections})).ok


@pytest.mark.parametrize(
    "text",
    [
        "Settings\n| A | B |\n| --- | --- |\n| 1 | 2 |\n(250 rows; 200 shown)",
        "- a\n  - b\n(9 items; 2 shown)",
    ],
    ids=["table-with-row-note", "list-with-nested-item-and-note"],
)
def test_a_structured_chunk_ending_on_its_count_note_is_whole(text: str) -> None:
    kind: ChunkKind = "table" if text.startswith("Settings") else "list"
    view = _with_chunk("table", {"kind": kind, "text": text})
    assert validate_view(view).ok


@pytest.mark.parametrize(
    ("update", "rule"),
    [
        ({"text": "He was born in"}, "fragment_summaries"),
        ({"text": "He was born. Main article: X."}, "navigation_summaries"),
        ({"citation_id": "c4"}, "wrong_summary_citation"),
    ],
    ids=["stops-mid-sentence", "navigation", "cites-another-section"],
)
def test_a_defective_summary_is_reported(update: dict[str, object], rule: str) -> None:
    report = validate_view(_with_summary(update))
    assert report.counts[rule] == 1
    assert len(report.problems) == 1


def _summary_block(marker: str) -> str:
    """Render a summary block the way the Markdown renderer lays it out."""
    lines = ["**Machine summary (model output)**", "", "A summary.", marker, "", "Model: m"]
    return "\n".join(lines)


@pytest.mark.parametrize(
    ("markdown", "rule"),
    [
        (f"Text.\n[c99]\n\n{_summary_block('[c3]')}", "unresolved_markers"),
        (_summary_block("[c4]"), "wrong_summary_marker"),
        # The summary's own block ends at "Model:"; a later marker is not its.
        (f"{_summary_block('')}\n\nNext text.\n[c3]", "wrong_summary_marker"),
        ("Text.\n[c1]\n\n**Machine summary (model output)**\n\nA summary.", "wrong_summary_marker"),
    ],
    ids=[
        "marker-without-citation",
        "summary-cites-another-section",
        "summary-without-marker",
        "summary-at-the-end-without-marker",
    ],
)
def test_a_defective_marker_is_reported(markdown: str, rule: str) -> None:
    report = validate_view(make_fixture_view(), markdown)
    assert report.counts[rule] == 1
    assert len(report.problems) == 1


def test_markers_that_name_citations_and_follow_their_summary_pass() -> None:
    assert validate_view(make_fixture_view(), f"Text.\n[c1]\n\n{_summary_block('[c3]')}").ok


@pytest.mark.parametrize(
    ("change", "rule"),
    [
        ("drop-anchor", "bad_anchor"),
        ("rename-heading", "anchor_names_other_section"),
        ("lead-url", "bad_citation_url"),
        ("section-url", "bad_citation_url"),
    ],
)
def test_a_defective_citation_is_reported(change: str, rule: str) -> None:
    view = make_fixture_view()
    headings = make_heading_map(view)
    anchor = next(iter(headings))
    if change == "drop-anchor":
        del headings[anchor]
    elif change == "rename-heading":
        headings[anchor] = "Another heading"
    else:
        cid = "c1" if change == "lead-url" else next(c.id for c in view.citations if c.anchor)
        citations = [
            c.model_copy(update={"url": "https://en.wikipedia.org/wiki/X"}) if c.id == cid else c
            for c in view.citations
        ]
        view = view.model_copy(update={"citations": citations})
    report = validate_view(view, None, lambda _rev: headings)
    assert report.counts[rule] == 1
    assert len(report.problems) == 1


def test_heading_map_reads_the_real_ids_of_every_heading_level() -> None:
    html = (
        '<h1 id="Title">Title</h1><h2 id="Early_life_(and)_family">Early life (and) family</h2>'
        '<h6 id="X_2">X</h6><h3>No id</h3><p id="p">t</p>'
    )
    assert heading_map(html) == {
        "Title": "Title",
        "Early_life_(and)_family": "Early life (and) family",
        "X_2": "X",
    }
