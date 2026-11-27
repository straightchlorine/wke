"""With the new settings off (or one on alone), responses match fixtures/settings_off.

A recording holds, per route and budget (2000, 8000, 32000 tokens), the status, some headers and
a hash of the body, with timestamps removed. before_settings.json comes from code without these
settings, so only its status and headers are compared: the quote-aware sentence split changed one
passage of the body. subsection_headings.json has no "h" ETag suffix, so the test adds it.

To record again, run this test in a copy of the api tree at the code the recording should
describe, with PYTHONPATH on its src and WKE_RECORD_SETTINGS_OFF set to the file to write.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

import pytest

from tests.support.apps import app_client, make_app
from tests.support.constants import FIXTURE_REV_ID

FIXTURES = Path(__file__).parent.parent / "fixtures" / "settings_off"
# When set, the recording test writes to this path and the comparing tests do nothing.
RECORD = os.environ.get("WKE_RECORD_SETTINGS_OFF")
HEADERS = ("etag", "cache-control", "content-type", "vary")
BUDGETS = (2000, 8000, 32000)
CLOCK = re.compile(r'"(built_at|retrieved_at)":"[^"]*"|"stage_seconds":\{[^}]*\}')
OFF = {
    "selection_rating": False,
    "lean_response": False,
    "subsection_headings": False,
    "table_repack": False,
}


async def _capture(app, page_id: int) -> dict[str, dict]:
    urls = {}
    for budget in BUDGETS:
        urls[f"json {budget}"] = (f"/api/v1/dossiers/{page_id}", {"budget": budget})
        urls[f"parts {budget}"] = (
            f"/api/v1/dossiers/{page_id}",
            {"budget": budget, "parts": "dossier,metadata,sources"},
        )
        urls[f"md {budget}"] = (f"/api/v1/dossiers/{page_id}.md", {"budget": budget})
        urls[f"rev {budget}"] = (
            f"/api/v1/dossiers/{page_id}/rev/{FIXTURE_REV_ID}",
            {"budget": budget},
        )
    out = {}
    async with app_client(app) as client:
        for name, (url, params) in urls.items():
            response = await client.get(url, params=params)
            body = CLOCK.sub("", response.text)
            out[name] = {
                "status": response.status_code,
                "headers": {h: response.headers.get(h) for h in HEADERS},
                "body_sha256": hashlib.sha256(body.encode()).hexdigest(),
                "body_chars": len(body),
            }
    return out


async def _app_of(fake_redis, settings, wikimedia_client, ml_client_ok, **overrides: bool):
    return make_app(
        fake_redis,
        settings.model_copy(update=overrides),
        wikimedia_http=wikimedia_client._http,
        ml_http=ml_client_ok._http,
    )


async def _check(
    recording: str, fake_redis, settings, wikimedia_client, ml_client_ok, page_id, **s
):
    app = await _app_of(fake_redis, settings, wikimedia_client, ml_client_ok, **s)
    captured = await _capture(app, page_id)
    recorded = json.loads((FIXTURES / recording).read_text())
    assert captured.keys() == recorded.keys()
    return captured, recorded


async def test_record(fake_redis, settings, wikimedia_client, ml_client_ok, built_page) -> None:
    if not RECORD:
        pytest.skip("only records, when WKE_RECORD_SETTINGS_OFF names the file to write")
    app = await _app_of(fake_redis, settings, wikimedia_client, ml_client_ok)
    captured = await _capture(app, built_page)
    Path(RECORD).write_text(json.dumps(captured, indent=1, sort_keys=True) + "\n")


async def test_every_setting_off_keeps_the_headers_from_before_the_settings(
    fake_redis, settings, wikimedia_client, ml_client_ok, built_page
) -> None:
    if RECORD:
        return
    captured, recorded = await _check(
        "before_settings.json",
        fake_redis,
        settings,
        wikimedia_client,
        ml_client_ok,
        built_page,
        **OFF,
    )
    for name, response in captured.items():
        assert response["status"] == recorded[name]["status"], name
        assert response["headers"] == recorded[name]["headers"], name


async def test_every_setting_off_is_byte_identical_to_the_quote_split_recording(
    fake_redis, settings, wikimedia_client, ml_client_ok, built_page
) -> None:
    if RECORD:
        return
    captured, recorded = await _check(
        "quote_split_only.json",
        fake_redis,
        settings,
        wikimedia_client,
        ml_client_ok,
        built_page,
        **OFF,
    )
    for name, response in captured.items():
        assert response == recorded[name], name


async def test_the_lean_response_alone_is_byte_identical_to_its_recording(
    fake_redis, settings, wikimedia_client, ml_client_ok, built_page
) -> None:
    if RECORD:
        return
    captured, recorded = await _check(
        "lean_response.json",
        fake_redis,
        settings,
        wikimedia_client,
        ml_client_ok,
        built_page,
        **{**OFF, "lean_response": True},
    )
    for name, response in captured.items():
        assert response == recorded[name], name


async def test_the_subsection_headings_alone_are_byte_identical_to_their_recording(
    fake_redis, settings, wikimedia_client, ml_client_ok, built_page
) -> None:
    if RECORD:
        return
    captured, recorded = await _check(
        "subsection_headings.json",
        fake_redis,
        settings,
        wikimedia_client,
        ml_client_ok,
        built_page,
        **{**OFF, "subsection_headings": True},
    )
    for name, response in captured.items():
        expected = json.loads(json.dumps(recorded[name]))
        expected["headers"]["etag"] = expected["headers"]["etag"][:-1] + 'h"'
        assert response == expected, name


async def test_the_table_repack_alone_changes_nothing_but_the_etag_letter_here(
    fake_redis, settings, wikimedia_client, ml_client_ok, built_page
) -> None:
    # Nothing in the recorded dossier is better shown by a repack.
    if RECORD:
        return
    captured, recorded = await _check(
        "quote_split_only.json",
        fake_redis,
        settings,
        wikimedia_client,
        ml_client_ok,
        built_page,
        **{**OFF, "table_repack": True},
    )
    for name, response in captured.items():
        expected = json.loads(json.dumps(recorded[name]))
        expected["headers"]["etag"] = expected["headers"]["etag"][:-1] + 't"'
        assert response == expected, name
