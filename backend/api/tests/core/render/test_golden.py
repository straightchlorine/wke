"""Golden .md/.json output for the fixture Dossier at 2000/8000/32000.

Regenerate with WKE_UPDATE_GOLDEN=1 (writes tests/core/render/golden/*) rather
than hand-editing the committed files.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests.factories.dossier import (
    make_fixture_dossier,
    make_freshness,
    make_heading_map,
    make_links,
    make_overflowing_fixture_dossier,
)
from wke.core import render
from wke.core.models import DossierLinks, DossierView
from wke.core.models.budgets import BUDGETS, BudgetTokens
from wke.core.validate import validate_view

GOLDEN_DIR = Path(__file__).parent / "golden"


def _overflow_links() -> DossierLinks:
    return DossierLinks.model_validate(
        {
            "self": "https://wke.example/api/v1/dossiers/42",
            "pinned": "https://wke.example/api/v1/dossiers/42/rev/7000000",
            "markdown": "https://wke.example/api/v1/dossiers/42.md",
            "wikipedia": "https://en.wikipedia.org/wiki/Overflow_Topic",
        }
    )


def _check_golden(stem: str, view: DossierView) -> None:
    """Compare a view and its Markdown with the golden pair, or rewrite the pair.

    Args:
        stem: file name of the pair without extension.
        view: the view to render and serialise.
    """
    markdown = render.render_markdown(view, include_summaries=True)
    payload = json.loads(view.model_dump_json(by_alias=True, indent=2))
    payload_text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    md_path = GOLDEN_DIR / f"{stem}.md"
    json_path = GOLDEN_DIR / f"{stem}.json"

    if os.environ.get("WKE_UPDATE_GOLDEN") == "1":
        md_path.write_text(markdown, encoding="utf-8")
        json_path.write_text(payload_text, encoding="utf-8")
        pytest.skip("golden files regenerated (WKE_UPDATE_GOLDEN=1)")

    assert md_path.exists(), f"missing golden file {md_path}; run with WKE_UPDATE_GOLDEN=1"
    assert json_path.exists(), f"missing golden file {json_path}; run with WKE_UPDATE_GOLDEN=1"
    assert markdown == md_path.read_text(encoding="utf-8")
    assert payload_text == json_path.read_text(encoding="utf-8")


@pytest.mark.parametrize("budget", BUDGETS)
def test_golden_markdown_and_json(budget: BudgetTokens) -> None:
    dossier = make_fixture_dossier()
    view = render.build_view(
        dossier, budget, make_freshness(dossier), make_links(), include_summaries=True
    )
    _check_golden(f"dossier_{budget}", view)


def test_golden_dossier_2000_truncates_and_omits_chunks() -> None:
    """The other goldens fit under every budget uncut; this one actually truncates."""
    dossier = make_overflowing_fixture_dossier()
    view = render.build_view(
        dossier, 2000, make_freshness(dossier), _overflow_links(), include_summaries=True
    )
    assert view.budget.omitted_chunks > 0
    _check_golden("dossier_2000_truncated", view)


@pytest.mark.parametrize("budget", BUDGETS)
def test_rendered_fixture_passes_the_validator_at_every_budget(budget: BudgetTokens) -> None:
    dossier = make_fixture_dossier()
    view = render.build_view(
        dossier, budget, make_freshness(dossier), make_links(), include_summaries=True
    )
    headings = make_heading_map(view)
    report = validate_view(
        view, render.render_markdown(view, include_summaries=True), lambda _rev: headings
    )
    assert report.ok, report.problems
    assert report.counts["anchors_checked"] == len(headings)
