"""With the switches off the dossier responses are those of the code without the changes.

Four recordings over the same built article, each the status, headers and body hash of the JSON
and Markdown routes at 2000, 8000 and 32000 (the build and retrieval times and the stage seconds
are blanked, they are the clock's):

- fixtures/switch_off/base.json: base's code (f5f16ae). With every switch off (SELECTION_RATING,
  LEAN_RESPONSE, SUBSECTION_HEADINGS) the status and headers, the ETag among them, equal it. The
  body does not: change C (quote-aware sentence split) has no switch and moves one passage of
  this article at 2000 and the importance of a section.
- fixtures/switch_off/c_only.json: base's code with change C only. With every switch off, the
  whole response (headers and body) equals it.
- fixtures/switch_off/g_c.json: change G (lean response) and change C, at their defaults. With
  only LEAN_RESPONSE on, the whole response equals it.
- fixtures/switch_off/b_c.json: change B (subsection headings) and change C, at their defaults.
  With only SUBSECTION_HEADINGS on, the whole response equals it, but for the ETag: the recording
  predates the letter "h" that the headings switch adds to the parts code, so the test expects the
  recorded tag with "h" at its end. The recorded article is not a
  structural build, so this file equals c_only.json and shows no heading; the headings on a
  structural build are tested in test_dossiers_rating_lean.py (the matrix on the Markdown route).

To record again, run this test in a copy of the api tree of that code (its tests and pyproject.toml,
this file added) with PYTHONPATH on its src and WKE_RECORD_SWITCH_OFF set to the file to write
(the recording is made with the settings at their defaults).
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

FIXTURES = Path(__file__).parent.parent / "fixtures" / "switch_off"
# A path to write the recording to instead of checking it.
RECORD = os.environ.get("WKE_RECORD_SWITCH_OFF")
HEADERS = ("etag", "cache-control", "content-type", "vary")
BUDGETS = (2000, 8000, 32000)
CLOCK = re.compile(r'"(built_at|retrieved_at)":"[^"]*"|"stage_seconds":\{[^}]*\}')
OFF = {"selection_rating": False, "lean_response": False, "subsection_headings": False}


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


async def _app_of(fake_redis, settings, wikimedia_client, ml_client_ok, **switches: bool):
    return make_app(
        fake_redis,
        settings.model_copy(update=switches),
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
        pytest.skip("only records, when WKE_RECORD_SWITCH_OFF names the file to write")
    app = await _app_of(fake_redis, settings, wikimedia_client, ml_client_ok)
    captured = await _capture(app, built_page)
    Path(RECORD).write_text(json.dumps(captured, indent=1, sort_keys=True) + "\n")


async def test_every_switch_off_keeps_the_headers_of_base(
    fake_redis, settings, wikimedia_client, ml_client_ok, built_page
) -> None:
    if RECORD:
        return
    captured, recorded = await _check(
        "base.json", fake_redis, settings, wikimedia_client, ml_client_ok, built_page, **OFF
    )
    for name, response in captured.items():
        assert response["status"] == recorded[name]["status"], name
        assert response["headers"] == recorded[name]["headers"], name


async def test_every_switch_off_is_byte_identical_to_base_with_change_c(
    fake_redis, settings, wikimedia_client, ml_client_ok, built_page
) -> None:
    if RECORD:
        return
    captured, recorded = await _check(
        "c_only.json", fake_redis, settings, wikimedia_client, ml_client_ok, built_page, **OFF
    )
    for name, response in captured.items():
        assert response == recorded[name], name


async def test_the_lean_response_alone_is_byte_identical_to_change_g_with_change_c(
    fake_redis, settings, wikimedia_client, ml_client_ok, built_page
) -> None:
    if RECORD:
        return
    captured, recorded = await _check(
        "g_c.json",
        fake_redis,
        settings,
        wikimedia_client,
        ml_client_ok,
        built_page,
        **{**OFF, "lean_response": True},
    )
    for name, response in captured.items():
        assert response == recorded[name], name


async def test_the_subsection_headings_alone_are_byte_identical_to_change_b_with_change_c(
    fake_redis, settings, wikimedia_client, ml_client_ok, built_page
) -> None:
    if RECORD:
        return
    captured, recorded = await _check(
        "b_c.json",
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
