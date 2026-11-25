"""The offline script writes one folder per stored dossier, laid out like a pulled one."""

from __future__ import annotations

import json
from pathlib import Path

import fakeredis
import pytest

from tests.factories.dossier import FACTORY_PAGE_ID, FACTORY_TITLE, make_fixture_dossier
from tests.support.offline import store_dossier
from tests.support.scripts import load_script
from wke.offline.reparse import view_and_markdown
from wke.offline.store import load_pulled

offline = load_script("offline_dossier.py")


def test_write_offline_folders_writes_every_budget_and_a_manifest(tmp_path: Path) -> None:
    client = fakeredis.FakeRedis(decode_responses=True)
    store_dossier(client, make_fixture_dossier())
    out, pulled = tmp_path / "out", tmp_path / "pulled"
    written = offline.write_offline_folders(client, str(out), pulled_dir=str(pulled))
    assert [Path(w).name for w in written] == [f"{FACTORY_PAGE_ID}-{FACTORY_TITLE.lower()}"]
    folder = Path(written[0])
    manifest = json.loads((folder / "manifest.json").read_text())
    expected = {f"rest-{b}.{ext}" for b in (2000, 8000, 32000) for ext in ("json", "md")}
    assert set(manifest["files"]) == expected
    assert {p.name for p in folder.glob("rest-*")} == expected
    assert manifest["page_id"] == FACTORY_PAGE_ID


def test_the_folder_it_writes_loads_back_as_the_whole_stored_dossier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """LEAN_RESPONSE (on by default) must not strip the Key facts chunk from the archive."""
    monkeypatch.delenv("LEAN_RESPONSE", raising=False)
    stored = make_fixture_dossier()
    assert [c.id for c in stored.chunks if c.kind == "facts"]
    client = fakeredis.FakeRedis(decode_responses=True)
    store_dossier(client, stored)
    out = tmp_path / "out"
    offline.write_offline_folders(client, str(out), pulled_dir=str(tmp_path / "pulled"))
    loaded = load_pulled(str(out), FACTORY_PAGE_ID)
    assert loaded is not None
    assert loaded.chunks == stored.chunks
    assert [s.chunk_ids for s in loaded.sections] == [s.chunk_ids for s in stored.sections]


@pytest.mark.parametrize("lean", ["true", "false"])
def test_the_markdown_follows_lean_response_and_the_json_keeps_the_key_facts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, lean: str
) -> None:
    monkeypatch.setenv("LEAN_RESPONSE", lean)
    client = fakeredis.FakeRedis(decode_responses=True)
    store_dossier(client, make_fixture_dossier())
    out = tmp_path / "out"
    folder = Path(
        offline.write_offline_folders(client, str(out), pulled_dir=str(tmp_path / "p"))[0]
    )

    for budget in (2000, 8000, 32000):
        markdown = (folder / f"rest-{budget}.md").read_text()
        assert ("**Key facts**" in markdown) is (lean == "false")
    for budget in (2000, 8000):
        served = json.loads((folder / f"rest-{budget}.json").read_text())
        has_facts = any(c["kind"] == "facts" for c in served["chunks"])
        assert has_facts is (lean == "false")
    whole = json.loads((folder / "rest-32000.json").read_text())
    assert any(c["kind"] == "facts" for c in whole["chunks"])


def test_a_lean_pull_is_refused_when_redis_no_longer_holds_the_dossier(tmp_path: Path) -> None:
    pulled = tmp_path / "pulled" / f"{FACTORY_PAGE_ID}-jesus"
    pulled.mkdir(parents=True)
    view, _ = view_and_markdown(make_fixture_dossier(), 32000, lean=False)
    (pulled / "rest-32000.json").write_text(view.model_dump_json())
    etag = '"1-pv-32000-json-complete-5-s1-l0-pdmsl"'
    manifest = {"files": {"rest-32000.json": {"etag": etag}}}
    (pulled / "manifest.json").write_text(json.dumps(manifest))
    client = fakeredis.FakeRedis(decode_responses=True)

    with pytest.raises(SystemExit, match="lean response"):
        offline.write_offline_folders(client, str(tmp_path / "out"), pulled_dir=str(pulled.parent))
