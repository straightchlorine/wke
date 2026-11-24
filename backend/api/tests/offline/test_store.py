"""Tests for wke.offline.store over a fake Redis and pulled folders."""

from __future__ import annotations

import json
from pathlib import Path

import fakeredis
import pytest

from tests.factories.dossier import make_fixture_dossier
from tests.support.constants import PIPELINE_VERSION
from tests.support.offline import cache_html
from wke.api.etag import etag_is_lean
from wke.core import keys
from wke.core.citations import seed_pin
from wke.core.models import Dossier
from wke.offline.reparse import view_and_markdown
from wke.offline.store import (
    LeanPullError,
    connect,
    find_pulled_by_title,
    load_dossier,
    load_html,
    load_pulled,
    load_pulled_html,
    pulled_etag,
    stored_page_ids,
)


def _pull(root: Path, dossier: Dossier, name: str | None = None) -> Path:
    """Write the 32000-token view of a dossier in the pull folder layout."""
    folder = root / (name or f"{dossier.topic.page_id}-slug")
    folder.mkdir()
    # A pull made before the key facts block left the responses still holds it.
    view, _ = view_and_markdown(dossier, 32000, lean=False)
    (folder / "rest-32000.json").write_text(view.model_dump_json(), encoding="utf-8")
    return folder


def test_stored_page_ids_lists_pointers_sorted(client: fakeredis.FakeRedis, stored: Dossier):
    client.set(keys.ptr(7), "{}")
    client.set(keys.dossier(8, 1, PIPELINE_VERSION), "{}")
    assert stored_page_ids(client) == sorted([7, stored.topic.page_id])


def test_connect_decodes_responses():
    client = connect("redis://localhost:6379/0")
    assert client.connection_pool.connection_kwargs["decode_responses"] is True


def test_load_dossier_follows_the_latest_pointer(client: fakeredis.FakeRedis, stored: Dossier):
    loaded = load_dossier(client, stored.topic.page_id)
    assert loaded is not None
    assert loaded.id == stored.id


def test_load_dossier_needs_no_pointer_when_revision_and_pipeline_are_given(
    client: fakeredis.FakeRedis, stored: Dossier
):
    client.delete(keys.ptr(stored.topic.page_id))
    loaded = load_dossier(client, stored.topic.page_id, seed_pin(stored).rev_id, PIPELINE_VERSION)
    assert loaded is not None
    assert loaded.id == stored.id


def test_load_dossier_prefers_the_given_revision_over_the_pointer(
    client: fakeredis.FakeRedis, stored: Dossier
):
    other = stored.model_copy(update={"id": f"{stored.topic.page_id}@2:{'a' * 12}"})
    client.set(keys.dossier(stored.topic.page_id, 2, PIPELINE_VERSION), other.model_dump_json())
    loaded = load_dossier(client, stored.topic.page_id, 2)
    assert loaded is not None
    assert loaded.id == other.id


def test_load_dossier_prefers_the_given_pipeline_over_the_pointer(
    client: fakeredis.FakeRedis, stored: Dossier
):
    other = stored.model_copy(update={"id": f"{stored.topic.page_id}@2:{'b' * 12}"})
    client.set(
        keys.dossier(stored.topic.page_id, seed_pin(stored).rev_id, "other-pipeline"),
        other.model_dump_json(),
    )
    loaded = load_dossier(client, stored.topic.page_id, None, "other-pipeline")
    assert loaded is not None
    assert loaded.id == other.id


@pytest.mark.parametrize("kind", ["no_pointer", "pointer_without_dossier", "unknown_revision"])
def test_load_dossier_is_none_when_nothing_is_stored(
    client: fakeredis.FakeRedis, stored: Dossier, kind: str
):
    page_id = stored.topic.page_id
    if kind == "no_pointer":
        page_id += 1
    elif kind == "pointer_without_dossier":
        client.delete(keys.dossier(page_id, seed_pin(stored).rev_id, PIPELINE_VERSION))
    rev_id = seed_pin(stored).rev_id + 1 if kind == "unknown_revision" else None
    assert load_dossier(client, page_id, rev_id) is None


def test_load_html_decodes_the_cached_parsoid_payload(client: fakeredis.FakeRedis):
    html = "<p>caf\u00e9</p>"
    cache_html(client, 5, html)
    assert load_html(client, 5) == html
    assert load_html(client, 6) is None


def test_load_pulled_rebuilds_a_dossier_from_the_32000_view(tmp_path: Path):
    dossier = make_fixture_dossier()
    _pull(tmp_path, dossier)
    loaded = load_pulled(str(tmp_path), dossier.topic.page_id)
    assert loaded is not None
    assert loaded.chunks == dossier.chunks
    assert [s.id for s in loaded.sections] == [s.id for s in dossier.sections]


def test_load_pulled_is_none_when_the_view_left_chunks_out(tmp_path: Path):
    dossier = make_fixture_dossier()
    folder = _pull(tmp_path, dossier)
    path = folder / "rest-32000.json"
    view = json.loads(path.read_text(encoding="utf-8"))
    view["budget"]["omitted_chunks"] = 3
    path.write_text(json.dumps(view), encoding="utf-8")
    assert load_pulled(str(tmp_path), dossier.topic.page_id) is None


def test_load_pulled_is_none_without_a_pull_of_that_page(tmp_path: Path):
    dossier = make_fixture_dossier()
    _pull(tmp_path, dossier, name=f"{dossier.topic.page_id + 1}-other")
    _pull(tmp_path, dossier, name=f"{dossier.topic.page_id}0-longer-id")
    assert load_pulled(str(tmp_path), dossier.topic.page_id) is None
    (tmp_path / f"{dossier.topic.page_id}-empty").mkdir()
    assert load_pulled(str(tmp_path), dossier.topic.page_id) is None


def test_load_pulled_html_reads_the_source_of_the_pinned_revision(tmp_path: Path):
    (tmp_path / "source-5.html").write_text("<p>caf\u00e9</p>", encoding="utf-8")
    assert load_pulled_html(tmp_path, 5) == "<p>caf\u00e9</p>"
    assert load_pulled_html(tmp_path, 6) is None
    assert load_pulled_html(None, 5) is None


def _record_etag(folder: Path, etag: str | None) -> None:
    """Write the manifest.json entry pull.py writes for rest-32000.json."""
    entry: dict[str, object] = {"bytes": 1, "status": 200}
    if etag is not None:
        entry["etag"] = etag
    manifest = {"title": "Alma", "files": {"rest-32000.json": entry}}
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


@pytest.mark.parametrize(
    ("etag", "lean"),
    [
        ('"1-pv-32000-json-complete-5-s1-l0-pdms"', False),
        ('"1-pv-32000-json-complete-5-s1-l0-pdmsl"', True),
        ('"1-pv-32000-json-complete-5-s1-l0-pdmsl-r1"', True),
        ('"1-pv-32000-json-complete-5-s1-l0-pdmslh-r0"', True),
        ('"1-pv-32000-json-complete-5-s1-l0-pdmsh"', False),
        ('"1-test-pv-32000-json-complete-5-s0-l1-pdl"', True),
        ('"1377998321-dev-32000-json-complete-5-s1-l0"', False),
        ('W/"1-pv-32000-json-complete-5-s1-l0-pdl"', True),
        ("not an etag", False),
    ],
)
def test_the_lean_letter_of_an_etag_is_read_from_its_parts_code(etag: str, lean: bool) -> None:
    assert etag_is_lean(etag) is lean


@pytest.mark.parametrize(
    "etag",
    ['"1-pv-32000-json-complete-5-s1-l0-pdmsl"', '"1-pv-32000-json-complete-5-s1-l0-pdmslh-r1"'],
)
def test_load_pulled_refuses_a_pull_made_from_a_lean_api(tmp_path: Path, etag: str):
    dossier = make_fixture_dossier()
    _record_etag(_pull(tmp_path, dossier), etag)
    with pytest.raises(LeanPullError, match="LEAN_RESPONSE=false") as caught:
        load_pulled(str(tmp_path), dossier.topic.page_id)
    assert etag in str(caught.value)


@pytest.mark.parametrize("etag", [None, '"1-pv-32000-json-complete-5-s1-l0-pdmsh"'])
def test_load_pulled_takes_a_pull_without_the_lean_letter_as_whole(tmp_path: Path, etag):
    dossier = make_fixture_dossier()
    folder = _pull(tmp_path, dossier)
    _record_etag(folder, etag)
    assert load_pulled(str(tmp_path), dossier.topic.page_id) is not None


def test_load_pulled_takes_a_pull_without_a_manifest_as_whole(tmp_path: Path):
    dossier = make_fixture_dossier()
    _pull(tmp_path, dossier)
    assert pulled_etag(tmp_path / f"{dossier.topic.page_id}-slug") is None
    assert load_pulled(str(tmp_path), dossier.topic.page_id) is not None


def test_find_pulled_by_title_refuses_only_the_lean_pull_of_that_title(tmp_path: Path):
    dossier = make_fixture_dossier()
    lean = _pull(tmp_path, dossier, name="7-lean")
    _record_etag(lean, '"1-pv-32000-json-complete-5-s1-l0-pdmsl"')
    whole = _pull(tmp_path, dossier, name="8-whole")
    _record_etag(whole, None)
    other = json.loads((lean / "manifest.json").read_text(encoding="utf-8"))
    assert find_pulled_by_title(str(tmp_path), dossier.topic.title) is not None
    (lean / "manifest.json").write_text(
        json.dumps({**other, "title": dossier.topic.title}), encoding="utf-8"
    )
    with pytest.raises(LeanPullError):
        find_pulled_by_title(str(tmp_path), dossier.topic.title)
