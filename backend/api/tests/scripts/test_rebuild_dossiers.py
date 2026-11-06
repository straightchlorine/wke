"""The rebuild script's own helpers: scratch db, compat copy and sidecar files."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.factories.dossier import make_fixture_dossier, make_freshness, make_links
from tests.support.scripts import load_script

rebuild = load_script("rebuild_dossiers.py")


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("redis://localhost:6379/0", "redis://localhost:6379/15"),
        ("redis://localhost:6379", "redis://localhost:6379/15"),
        ("redis://:secret@cache.local:6380/3", "redis://:secret@cache.local:6380/15"),
    ],
)
def test_scratch_url_replaces_only_the_database(url: str, expected: str) -> None:
    assert rebuild.scratch_url(url) == expected


def test_compat_payload_drops_what_older_code_rejects() -> None:
    dossier = make_fixture_dossier()
    dossier.sections[0].summary_state = "no_prose"
    data = json.loads(rebuild.compat_payload(dossier))
    assert data["sections"][0]["summary_state"] == "skipped"
    assert all("heading_path" not in s and "dropped_non_prose" not in s for s in data["sections"])
    assert data["topic"]["page_id"] == dossier.topic.page_id


def test_sidecars_carry_the_summaries_the_fidelity_script_reads(tmp_path: Path) -> None:
    dossier = make_fixture_dossier()
    rebuild.write_sidecars(tmp_path, dossier, make_links(dossier), make_freshness(dossier))
    pid = dossier.topic.page_id
    view = json.loads((tmp_path / "after_cache" / f"{pid}.json").read_text())
    summarised = [s.id for s in dossier.sections if s.summary is not None]
    assert summarised
    assert [s["id"] for s in view["sections"] if s.get("summary")] == summarised
    first = next(s.summary.text for s in dossier.sections if s.summary is not None)
    assert first[:30] in (tmp_path / "md_after" / f"{pid}.md").read_text()
    assert (tmp_path / "native" / f"{pid}.json").exists()
