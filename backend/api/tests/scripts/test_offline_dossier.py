"""The offline script writes pull.py-style folders for the stored dossiers."""

from __future__ import annotations

import json
from pathlib import Path

import fakeredis

from tests.factories.dossier import FACTORY_PAGE_ID, FACTORY_TITLE, make_fixture_dossier
from tests.support.offline import store_dossier
from tests.support.scripts import load_script

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
