"""Tables and lists in the Markdown: quoting, cut notes and the budget line."""

from __future__ import annotations

from typing import Literal

import pytest

from tests.factories.dossier import make_freshness, make_links
from tests.factories.synthetic import (
    dossier_of,
    list_chunk_text,
    prose,
    section,
    table_chunk_text,
)
from wke.core import render
from wke.core.models import Dossier
from wke.core.text.tokens import est_tokens


def _dossier(kind: Literal["table", "list"], text: str, count: int = 1) -> Dossier:
    """Build a lead and a "Data" section holding a passage and `count` structured chunks."""
    structured = [
        prose(f"s1:{kind}{n}", ["Data"], 2 + n, text).model_copy(update={"kind": kind})
        for n in range(count)
    ]
    ids = ["s1:0", *(chunk.id for chunk in structured)]
    return dossier_of(
        [section("s0", [], ["l0"]), section("s1", ["Data"], ids)],
        [
            prose("l0", [], 0, "Alpha builds boats."),
            prose("s1:0", ["Data"], 1, "Harbour rules."),
            *structured,
        ],
    )


def _markdown(dossier: Dossier, budget: Literal[2000, 8000, 32000]) -> str:
    view = render.build_view(dossier, budget, make_freshness(dossier), make_links(dossier))
    return render.render_markdown(view, parts=frozenset({"dossier", "metadata"}))


def test_a_list_is_a_quoted_bullet_list_with_nested_items_and_the_cut_note() -> None:
    text = _markdown(_dossier("list", list_chunk_text(400)), 2000)
    assert "> - Item number 1\n>   - Detail of item 1\n> - Item number 2\n" in text
    assert "\n> (400 items; " in text


def test_a_table_cut_at_a_row_shows_its_note_not_the_lead_cut_notice() -> None:
    text = _markdown(_dossier("table", table_chunk_text(400)), 2000)
    assert "> (400 rows; " in text
    assert "shortened at a sentence end" not in text


def test_a_whole_table_at_a_large_budget_carries_no_cut_note() -> None:
    text = _markdown(_dossier("table", table_chunk_text(40)), 32000)
    assert "> | " in text
    assert "rows;" not in text


def test_the_budget_line_names_lists_left_out_and_the_section_gets_a_note() -> None:
    items = "\n".join(f"- {'word ' * 120}{n}" for n in range(10))
    text = _markdown(_dossier("list", items), 2000)
    budget_line = next(ln for ln in text.splitlines() if ln.startswith("Budget "))
    assert budget_line.endswith("1 list left out at this budget")
    assert "_1 list of this section is left out at this budget._" in text


def test_two_structured_chunks_left_out_are_counted_in_the_plural() -> None:
    items = "\n".join(f"- {'word ' * 120}{n}" for n in range(10))
    assert est_tokens(items) > 400
    text = _markdown(_dossier("list", items, count=2), 2000)
    assert "2 lists left out at this budget" in text
    assert "_2 lists of this section are left out at this budget._" in text


@pytest.mark.parametrize("budget", [2000, 8000])
def test_a_cut_table_is_not_named_as_a_shortened_opening(budget: Literal[2000, 8000]) -> None:
    text = _markdown(_dossier("table", table_chunk_text(400)), budget)
    note = next((ln for ln in text.splitlines() if ln.startswith("Opening passages")), "")
    assert "shortened" not in note
