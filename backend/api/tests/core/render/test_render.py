"""Unit tests for wke.core.render: citation tags, machine-summary label,
summary_state notices, licence footer and the structure-injection
defence.
"""

from __future__ import annotations

import re
from collections.abc import Callable

import pytest

from tests.factories.dossier import (
    make_fixture_dossier,
    make_freshness,
    make_links,
    make_overflowing_fixture_dossier,
)
from wke.core import render
from wke.core.models import Dossier, DossierView
from wke.core.models.budgets import BudgetTokens
from wke.core.render.escape import STRUCTURE_MARKER_RE, neutralise
from wke.core.render.markdown import content_text
from wke.core.text.tokens import est_tokens


def _view(budget: BudgetTokens = 32000) -> DossierView:
    dossier = make_fixture_dossier()
    freshness = make_freshness(dossier)
    links = make_links(dossier)
    return render.build_view(dossier, budget, freshness, links, include_summaries=True)


def test_every_quoted_passage_has_a_citation_tag() -> None:
    view = _view()
    text = render.render_markdown(view, include_summaries=True)
    quote_blocks = re.findall(r"(?:^>.*\n?)+", text, flags=re.MULTILINE)
    assert quote_blocks
    for block in quote_blocks:
        after = text[text.index(block) + len(block) :]
        first_line = after.splitlines()[0]
        assert re.match(r"^\[c[0-9]+\]$", first_line), first_line


def test_machine_summary_label_only_for_done_sections() -> None:
    view = _view()
    text = render.render_markdown(view, include_summaries=True)
    assert f"**{render.SUMMARY_LABEL}**" in text
    label_count = text.count(f"**{render.SUMMARY_LABEL}**")
    done_sections = [s for s in view.sections if s.summary is not None]
    assert label_count == len(done_sections)
    assert len(done_sections) >= 1


def test_pending_and_unavailable_render_as_notice_not_text() -> None:
    view = _view()
    text = render.render_markdown(view, include_summaries=True)
    assert "Summary pending" in text
    assert "Summary unavailable" in text
    assert "Summary skipped" not in text


def test_a_render_with_summaries_off_carries_no_summary_notice() -> None:
    text = render.render_markdown(_view(), include_summaries=False)
    assert "Summary pending" not in text
    assert "Summary unavailable" not in text


def test_licence_footer_present() -> None:
    view = _view()
    text = render.render_markdown(view, include_summaries=True)
    assert text.rstrip().endswith(view.license_notice)
    assert "CC BY-SA 4.0" in text


def test_sources_list_has_permalink_per_citation() -> None:
    view = _view()
    text = render.render_markdown(view, include_summaries=True)
    assert "## Sources" in text
    for citation in view.citations:
        if any(c.citation_id == citation.id for c in view.chunks):
            assert str(citation.pin.permalink) in text


def test_injection_defence_no_forged_heading_or_rule() -> None:
    view = _view()
    text = render.render_markdown(view, include_summaries=True)
    lines = text.splitlines()
    heading_lines = [ln for ln in lines if ln.startswith("## Sources")]
    assert len(heading_lines) == 1
    rule_lines = [ln for ln in lines if ln.strip() == "---"]
    assert rule_lines == []
    fence_lines = [ln for ln in lines if ln.startswith("```")]
    assert fence_lines == []
    assert text == text.encode("ascii", "ignore").decode("ascii")


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param("## Forged heading", id="atx_heading"),
        pytest.param("---", id="thematic_break_dashes"),
        pytest.param("***", id="thematic_break_stars"),
        pytest.param("___", id="thematic_break_underscores"),
        pytest.param("- - -", id="thematic_break_spaced"),
        pytest.param("Setext text\n===", id="setext_h1"),
        pytest.param("Setext text\n---", id="setext_h2"),
        pytest.param("```\nrm -rf /\n```", id="fenced_code_block"),
        pytest.param("~~~\nrm -rf /\n~~~", id="tilde_fence"),
        pytest.param("> forged blockquote", id="blockquote"),
        pytest.param("- forged bullet", id="dash_bullet"),
        pytest.param("+ forged bullet", id="plus_bullet"),
        pytest.param("* forged bullet", id="star_bullet"),
        pytest.param("1. forged ordered item", id="ordered_dot"),
        pytest.param("1) forged ordered item", id="ordered_paren"),
    ],
)
def test_neutralise_defangs_every_structural_construct(payload: str) -> None:
    neutralised = neutralise(payload)
    assert neutralised != payload
    assert neutralised == neutralised.encode("ascii", "ignore").decode("ascii")
    for line in neutralised.splitlines():
        assert not STRUCTURE_MARKER_RE.match(line), line


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        pytest.param("## Forged", "\\## Forged", id="no_indent"),
        pytest.param("   ## Forged", "   \\## Forged", id="three_space_indent_keeps_the_indent"),
        pytest.param("  - item", "  \\- item", id="indented_bullet"),
        pytest.param("2) item", "\\2) item", id="ordered_paren"),
        pytest.param("Plain text, 2 - 1 = 1.", "Plain text, 2 - 1 = 1.", id="prose_is_left_alone"),
    ],
)
def test_neutralise_puts_the_backslash_right_before_the_marker(line: str, expected: str) -> None:
    assert neutralise(line) == expected


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param("[c1]: https://evil.example", id="link_reference_definition"),
        pytest.param("[click me](https://evil.example)", id="link"),
        pytest.param("![img](https://evil.example)", id="image"),
        pytest.param("<https://evil.example>", id="autolink"),
        pytest.param("<script>alert(1)</script>", id="raw_html"),
        pytest.param("`inline code`", id="backtick"),
    ],
)
def test_escape_inline_markup_defangs_every_construct(payload: str) -> None:
    escaped = render.escape_inline_markup(payload)
    assert escaped != payload
    assert "[" not in escaped.replace("\\[", "")
    assert "]" not in escaped.replace("\\]", "")
    assert "<" not in escaped.replace("\\<", "")
    assert ">" not in escaped.replace("\\>", "")
    assert "`" not in escaped.replace("\\`", "")


def test_forged_link_reference_definition_is_defanged_end_to_end() -> None:
    dossier = make_fixture_dossier()
    dossier.chunks[0].text = '[c1]: https://evil.example "forged"'
    freshness = make_freshness(dossier)
    links = make_links(dossier)
    view = render.build_view(dossier, 32000, freshness, links, include_summaries=True)
    text = render.render_markdown(view, include_summaries=True)
    assert "\\[c1\\]: https://evil.example" in text
    assert "[c1]: https://evil.example" not in text


def test_budget_is_monotone_within_view() -> None:
    small = _view(2000)
    large = _view(32000)
    small_ids = {c.id for c in small.chunks}
    large_ids = {c.id for c in large.chunks}
    assert small_ids <= large_ids


@pytest.mark.parametrize("budget", [2000, 8000, 32000])
@pytest.mark.parametrize("build", [make_fixture_dossier, make_overflowing_fixture_dossier])
def test_content_fits_budget_and_is_what_is_reported(
    build: Callable[[], Dossier], budget: BudgetTokens
) -> None:
    dossier = build()
    links = make_links(dossier)
    view = render.build_view(
        dossier, budget, make_freshness(dossier), links, include_summaries=True
    )
    content, _ = content_text(view, include_summaries=True)
    assert view.budget.used_est_tokens == est_tokens(content) <= budget


def test_many_dropped_sections_at_2000_keep_lead_and_stay_in_budget() -> None:
    dossier = make_overflowing_fixture_dossier()
    links = make_links(dossier)
    view = render.build_view(dossier, 2000, make_freshness(dossier), links, include_summaries=False)
    markdown = render.render_markdown(view, include_summaries=False)
    assert view.budget.omitted_chunks > 40
    assert dossier.chunks[0].id in view.budget.included_chunk_ids
    assert "Left out: 6 sections left out at this budget: Section 2, Section 3" in markdown
    assert "first passage is cut" not in markdown
    content, _ = content_text(view, include_summaries=True)
    assert view.budget.used_est_tokens == est_tokens(content) <= 2000


def test_render_defaults_leave_summaries_and_their_notices_out() -> None:
    dossier = make_fixture_dossier()
    default_view = render.build_view(dossier, 32000, make_freshness(dossier), make_links(dossier))
    default = render.render_markdown(default_view)
    opted_in = render.render_markdown(_view(), include_summaries=True)

    assert render.SUMMARY_LABEL not in default
    assert "Summary withheld" not in default
    assert render.SUMMARY_LABEL in opted_in
