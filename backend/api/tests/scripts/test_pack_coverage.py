"""The pack coverage script says how the top sections of a stored dossier reach a pack."""

from __future__ import annotations

import json

import fakeredis
import pytest

from tests.factories.dossier import FACTORY_TITLE, make_budget_dossier, make_fixture_dossier
from tests.support.offline import store_dossier
from tests.support.scripts import load_script
from wke.core import pack
from wke.core.models import Dossier
from wke.core.text.tokens import est_tokens
from wke.offline.reparse import view_and_markdown

coverage = load_script("pack_coverage.py")


def test_classify_says_how_each_top_section_reaches_the_pack() -> None:
    rows = coverage.classify(make_budget_dossier(), 2000)
    assert [(label, how) for label, how, _ in rows] == [
        ("Huger", "none"),
        ("Huge", "summary"),
        ("Busy", "passage"),
    ]
    scores = [score for _, _, score in rows]
    assert scores == sorted(scores, reverse=True)


def test_classify_with_everything_lists_every_ranked_section() -> None:
    dossier = make_budget_dossier()
    assert len(coverage.classify(dossier, 2000, everything=True)) > len(
        coverage.classify(dossier, 2000)
    )


@pytest.mark.parametrize("title", [FACTORY_TITLE, FACTORY_TITLE.lower()])
def test_find_dossier_matches_a_stored_title_in_any_case(title: str) -> None:
    client = fakeredis.FakeRedis(decode_responses=True)
    store_dossier(client, make_fixture_dossier())
    found = coverage.find_dossier(client, title)
    assert found is not None
    assert found.topic.title == FACTORY_TITLE


def test_find_dossier_is_none_for_an_unknown_title() -> None:
    assert coverage.find_dossier(fakeredis.FakeRedis(decode_responses=True), "Ghost") is None


def _big_key_facts_dossier() -> Dossier:
    """The fixture dossier with a Key facts chunk that takes most of a 2000-token pack."""
    dossier = make_fixture_dossier()
    text = "word " * 1500
    chunks = [
        c.model_copy(update={"text": text, "est_tokens": est_tokens(text)})
        if c.kind == "facts"
        else c
        for c in dossier.chunks
    ]
    return dossier.model_copy(update={"chunks": chunks})


def _passage_sections(dossier: Dossier, lean: bool, monkeypatch: pytest.MonkeyPatch) -> set[str]:
    monkeypatch.setattr(coverage.settings, "lean_response", lean)
    rows = coverage.classify(dossier, 2000, everything=True)
    return {label for label, how, _ in rows if how == "passage"}


def test_classify_packs_without_the_key_facts_when_the_response_is_lean(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dossier = _big_key_facts_dossier()
    lean = _passage_sections(dossier, True, monkeypatch)
    legacy = _passage_sections(dossier, False, monkeypatch)
    assert lean > legacy


def test_classify_counts_the_key_facts_when_the_response_is_not_lean(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dossier = _big_key_facts_dossier()
    monkeypatch.setattr(coverage.settings, "lean_response", False)
    included = set(pack.pack(dossier, 2000).budget.included_chunk_ids)
    rows = coverage.classify(dossier, 2000, everything=True)
    by_id = {s.label: s for s in dossier.sections}
    for label, how, _ in rows:
        reached = any(cid in included for cid in by_id[label].chunk_ids)
        assert (how == "passage") == reached


def test_find_dossier_refuses_a_lean_pull_of_the_title(tmp_path) -> None:
    folder = tmp_path / "7-jesus"
    folder.mkdir()
    view, _ = view_and_markdown(make_fixture_dossier(), 32000, lean=False)
    (folder / "rest-32000.json").write_text(view.model_dump_json())
    manifest = {
        "title": FACTORY_TITLE,
        "files": {"rest-32000.json": {"etag": '"1-pv-32000-json-complete-5-s1-l0-pdmsl"'}},
    }
    (folder / "manifest.json").write_text(json.dumps(manifest))

    with pytest.raises(SystemExit, match="lean response"):
        coverage.find_dossier(
            fakeredis.FakeRedis(decode_responses=True), FACTORY_TITLE, str(tmp_path)
        )
