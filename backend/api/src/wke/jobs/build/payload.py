"""Serialised forms a build writes to Redis and into Job.result_url."""

from __future__ import annotations

import json
from datetime import datetime

from pydantic import HttpUrl, TypeAdapter

from wke.core.models import Dossier
from wke.jobs.build.constants import RESULT_URL_BUDGET

_HTTP_URL = TypeAdapter(HttpUrl)


def dossier_payload(dossier: Dossier) -> str:
    """Serialize a dossier for Redis, validated so it can always be read back.

    `model_dump_json` alone never re-validates: a field mutated in place
    after construction (e.g. wke-ml's relevance clamped past [0, 1]) would
    otherwise persist happily and only fail the next time something reads
    it back with `Dossier.model_validate_json`, as an unrelated 500 on a
    completely different request. Validating the exact string about to be
    written catches that here, before anything is stored.

    Args:
        dossier: the dossier about to be written to Redis.

    Returns:
        str: dossier.model_dump_json(exclude_none=True).

    Raises:
        pydantic.ValidationError: if that JSON fails Dossier's own schema.
    """
    payload = dossier.model_dump_json(exclude_none=True)
    Dossier.model_validate_json(payload)
    return payload


def result_url(public_host: str, public_scheme: str, page_id: int) -> HttpUrl | None:
    """Build Job.result_url: the public dossier URL for a just-persisted build.

    Args:
        public_host: PUBLIC_HOST setting; empty means no public URL is
            known (e.g. some tests), so no result_url is set.
        public_scheme: PUBLIC_SCHEME setting ("http" or "https").
        page_id: the built page's id.

    Returns:
        HttpUrl | None: the public URL of
        GET /api/v1/dossiers/{page_id}?budget=8000, or None if
        public_host is empty.
    """
    if not public_host:
        return None
    return _HTTP_URL.validate_python(
        f"{public_scheme}://{public_host}/api/v1/dossiers/{page_id}?budget={RESULT_URL_BUDGET}"
    )


def ptr_json(rev_id: int, pipeline_version: str, built_at: datetime) -> str:
    """Serialise the latest-build pointer of a page.

    Args:
        rev_id: the revision of the latest build.
        pipeline_version: PIPELINE_VERSION setting.
        built_at: when the build finished.

    Returns:
        str: the JSON text stored under ptr:{page_id}.
    """
    return json.dumps(
        {"rev_id": rev_id, "pipeline_version": pipeline_version, "built_at": built_at.isoformat()}
    )
