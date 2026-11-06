"""Markdown for key facts, tables, withheld summaries, exact Sources and the budget line."""

from __future__ import annotations

import pytest

from tests.factories.dossier import (
    FACTORY_REV_ID,
    make_fixture_dossier,
    make_freshness,
    make_links,
)
from wke.core import pack, render
from wke.core.models import Dossier
from wke.core.models.budgets import BUDGETS, BudgetTokens
from wke.core.text.navigation import points_elsewhere


def _markdown(dossier: Dossier, budget: BudgetTokens = 32000) -> str:
    view = render.build_view(
        dossier, budget, make_freshness(dossier), make_links(dossier), include_summaries=True
    )
    return render.render_markdown(view, include_summaries=True)


def test_facts_are_a_quoted_bullet_list_with_the_lead_citation() -> None:
    text = _markdown(make_fixture_dossier())
    block = text.split("**Key facts**\n\n")[1].split("\n\n")[0]
    assert block == (
        "> - Born: c. 6 to 4 BC, Herodian kingdom, Roman Empire\n"
        "> - Cause of death: Crucifixion\n"
        "[c1]"
    )


def test_table_is_a_quoted_caption_and_pipe_table_with_its_section_citation() -> None:
    text = _markdown(make_fixture_dossier())
    assert (
        "> Ministry settings\n>\n> | Setting | Region |\n> | --- | --- |\n"
        "> | Galilee | North of Judea |\n[c4]\n"
    ) in text


def test_sources_list_the_exact_section_urls_and_only_cited_sections() -> None:
    text = _markdown(make_fixture_dossier())
    sources = text.split("## Sources\n\n")[1].split("\n\n")[0].splitlines()
    assert sources == [
        f"- [c1] https://en.wikipedia.org/w/index.php?oldid={FACTORY_REV_ID}",
        f"- [c3] https://en.wikipedia.org/w/index.php?oldid={FACTORY_REV_ID}#Early_life,_family,_and_profession",
        f"- [c4] https://en.wikipedia.org/w/index.php?oldid={FACTORY_REV_ID}#Public_ministry",
        f"- [c5] https://en.wikipedia.org/w/index.php?oldid={FACTORY_REV_ID}#Artistic_depictions",
    ]


def test_budget_line_names_what_the_extraction_left_out() -> None:
    dossier = make_fixture_dossier()
    sections = [
        s.model_copy(update={"dropped_lists": 2, "dropped_tables": 1}) if s.id == "s2" else s
        for s in dossier.sections
    ]
    text = _markdown(dossier.model_copy(update={"sections": sections}))
    assert "\nBudget 32,000 tokens: all 6 passages; 2 lists and 1 table not included\n" in text
    text = _markdown(dossier)
    assert "all 6 passages; 1 list not included\n" in text


def test_budget_line_counts_prose_only_and_names_tables_the_budget_dropped() -> None:
    dossier = make_fixture_dossier()
    heavy = dossier.chunks[-1].model_copy(
        update={
            "text": "x" * 8100,
            "est_tokens": 2025,
            "kind": "table",
            "id": f"{FACTORY_REV_ID}:legacy:table0",
        }
    )
    sections = [
        s.model_copy(update={"chunk_ids": [*s.chunk_ids, heavy.id]}) if s.id == "s3" else s
        for s in dossier.sections
    ]
    dossier = dossier.model_copy(update={"sections": sections, "chunks": [*dossier.chunks, heavy]})
    assert pack.chunk_kind(heavy.id) == "table"
    text = _markdown(dossier, 2000)
    assert "all 6 passages; 1 table left out at this budget; 1 list not included\n" in text
    assert "_1 table of this section is left out at this budget._" in text


@pytest.mark.parametrize(
    ("reason", "notice"),
    [
        (None, "_Summary withheld: no reason was stored._"),
        (
            "the text does not end at a sentence end",
            "_Summary withheld: the text does not end at a sentence end._",
        ),
        (
            "a stored reason with a full stop. ",
            "_Summary withheld: a stored reason with a full stop._",
        ),
    ],
)
def test_withheld_summary_has_its_own_notice_and_no_text(reason: str | None, notice: str) -> None:
    dossier = make_fixture_dossier()
    sections = [
        s.model_copy(
            update={"summary": None, "summary_state": "withheld", "withheld_reason": reason}
        )
        if s.id == "s1"
        else s
        for s in dossier.sections
    ]
    text = _markdown(dossier.model_copy(update={"sections": sections}))
    assert notice in text
    assert "Machine summary" not in text


def test_summary_is_followed_by_its_own_section_citation() -> None:
    text = _markdown(make_fixture_dossier())
    after = text.split(f"**{render.SUMMARY_LABEL}**\n\n")[1].splitlines()
    assert after[0].startswith("Jesus grew up in Nazareth")
    assert after[1] == "[c3]"


def test_view_summary_carries_its_section_citation_in_json() -> None:
    dossier = make_fixture_dossier()
    view = render.build_view(
        dossier, 32000, make_freshness(dossier), make_links(dossier), include_summaries=True
    )
    section = next(s for s in view.sections if s.summary is not None)
    assert section.summary is not None
    assert section.summary.citation_id == section.citation_id == "c3"


def test_no_text_points_the_reader_anywhere_but_to_a_citation() -> None:
    for budget in BUDGETS:
        text = _markdown(make_fixture_dossier(), budget)
        body = text.split("## Sources")[0]
        for line in body.splitlines():
            assert not points_elsewhere(line), line
