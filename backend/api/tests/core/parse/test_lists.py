"""List harvesting on small inline HTML: when it applies, what a line holds, what is counted."""

from __future__ import annotations

import pytest

from tests.factories.parsed import LEAD, REV_ID, parse_sections, texts
from wke.core.parse import ParsedArticle

PROSE = "<p>" + "A full sentence of ordinary prose. " * 8 + "</p>"


def _parse(body: str, anchor: str = "Cast") -> ParsedArticle:
    return parse_sections(LEAD, body, anchor=anchor)


def _lists(article: ParsedArticle) -> list[str]:
    return texts(article, "list")


def test_each_item_is_one_verbatim_dash_line_with_links_reduced_to_text() -> None:
    article = _parse(
        "<ul><li><a href='./X'>Jane Doe</a> as <i>Dorothy</i></li>"
        "<li>Sam Roe as Toto<sup class='reference'>[1]</sup></li></ul>"
    )
    assert _lists(article) == ["- Jane Doe as Dorothy\n- Sam Roe as Toto"]
    chunk = next(c for c in article.chunks if c.kind == "list")
    assert chunk.id == f"{REV_ID}:1:list0"
    assert article.sections[1].dropped_lists == 0


def test_nested_items_are_indented_lines_under_their_parent() -> None:
    article = _parse(
        "<ul><li>Albums<ul><li>First</li><li>Second</li></ul></li><li>Singles</li></ul>"
    )
    assert _lists(article) == ["- Albums\n  - First\n  - Second\n- Singles"]
    assert article.sections[1].dropped_lists == 0


def test_only_outermost_lists_become_chunks_and_each_gets_its_own() -> None:
    article = _parse("<ul><li>a</li></ul><ol><li>b</li></ol>")
    assert _lists(article) == ["- a", "- b"]
    ids = [c.id for c in article.chunks if c.kind == "list"]
    assert ids == [f"{REV_ID}:1:list0", f"{REV_ID}:1:list1"]


def test_a_section_with_prose_counts_its_lists_instead() -> None:
    article = _parse(f"{PROSE}<ul><li>a</li></ul>")
    assert _lists(article) == []
    assert article.sections[1].dropped_lists == 1
    assert article.sections[1].dropped_non_prose is True


@pytest.mark.parametrize(
    ("body", "anchor"),
    [
        ("<ul><li>Smith (2001). A book.</li></ul>", "Works_cited"),
        ("<ul class='gallery'><li>A caption</li></ul>", "Cast"),
    ],
    ids=["reference-section", "gallery"],
)
def test_reference_sections_and_galleries_are_neither_emitted_nor_counted(
    body: str, anchor: str
) -> None:
    article = _parse(body, anchor=anchor)
    assert _lists(article) == []
    assert article.sections[1].dropped_lists == 0


@pytest.mark.parametrize("anchor", ["See_also", "Notes_and_references", "Footnotes"])
def test_appendix_sections_are_dropped_with_their_subsections(anchor: str) -> None:
    sub = (
        "<section data-mw-section-id='2'><h3 id='Books'>Books</h3>"
        "<ul><li>A book</li></ul></section>"
    )
    article = _parse(f"<ul><li>Other page</li></ul>{sub}", anchor=anchor)
    assert [s.anchor for s in article.sections] == [""]
    assert _lists(article) == []


def test_subsections_of_a_reference_list_section_neither_emit_nor_count_lists() -> None:
    sub = (
        "<section data-mw-section-id='2'><h3 id='Books'>Books</h3>"
        "<ul><li>Smith (2001). A book.</li></ul></section>"
    )
    article = _parse(sub, anchor="Works_cited")
    assert [s.anchor for s in article.sections] == ["", "Works_cited", "Books"]
    assert _lists(article) == []
    assert article.sections[2].dropped_lists == 0


def test_a_list_over_200_items_is_cut_at_an_item_with_the_note() -> None:
    items = "".join(f"<li>item {n}</li>" for n in range(1, 251))
    article = _parse(f"<ul>{items}</ul>")
    lines = _lists(article)[0].splitlines()
    assert lines[-2:] == ["- item 200", "(250 items; 200 shown)"]


def test_empty_items_are_left_out_and_spaces_collapsed() -> None:
    article = _parse("<ul><li></li><li>  spaced   out  </li></ul>")
    assert _lists(article) == ["- spaced out"]
