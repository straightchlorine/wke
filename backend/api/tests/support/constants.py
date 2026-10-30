"""Page ids, titles, pins and required env shared by the recorded-fixture tests.

FIXTURE_* come from tests/fixtures/wm/resolve.json, so re-recording with
record.py (its TITLE) switches the recorded article for the whole suite.
"""

from __future__ import annotations

import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "wm"

_RESOLVE = json.loads((FIXTURES_DIR / "resolve.json").read_text(encoding="utf-8"))
_PAGE = _RESOLVE["query"]["pages"][0]
FIXTURE_TITLE: str = _PAGE["title"]

# The title as it appears in a Wikipedia URL path (spaces become underscores).
FIXTURE_WIKI_TITLE: str = FIXTURE_TITLE.replace(" ", "_")
FIXTURE_PAGE_ID: int = _PAGE["pageid"]
FIXTURE_REV_ID: int = _PAGE["lastrevid"]

# ISO 8601 with a trailing Z, as the Action API returns it.
FIXTURE_REV_TIMESTAMP: str = _PAGE["revisions"][0]["timestamp"]

PIPELINE_VERSION = "test-pv"
JOB_ID = "0123456789abcdef"
MISSING_TITLE = "Ghost Page Does Not Exist"
DISAMBIGUATION_TITLE = "Mercury (disambiguation)"
NEW_TITLE = "Grace Hopper"
NEW_TITLE_PAGE_ID = 555
NEW_TITLE_REV_ID = 42

# Settings with no default;
# tests/conftest.py sets them before importing wke.settings.
REQUIRED_ENV: dict[str, str] = {
    "WIKIPEDIA_API_URL": "https://en.wikipedia.org/w/api.php",
    "WIKIPEDIA_REST_URL": "https://en.wikipedia.org/w/rest.php/v1",
    "WIKIMEDIA_EVENTSTREAMS_URL": "https://stream.wikimedia.org/v2/stream/recentchange",
    "WIKIFEEDS_URL": "https://en.wikipedia.org/api/rest_v1/feed/featured",
    "ML_URL": "http://wke-ml:8000",
    "REDIS_URL": "redis://localhost:6379/0",
    "PUBLIC_HOST": "wke.piotrkrzysztof.dev",
    "WKE_CONTACT_EMAIL": "bot-traffic@wikimedia.org",
    "POD_CIDR": "10.42.0.0/16",
    "PIPELINE_VERSION": PIPELINE_VERSION,
}
