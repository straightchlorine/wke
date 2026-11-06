"""Redis writes that mirror what the build pipeline stores, for the offline tools."""

from __future__ import annotations

import base64
import zlib
from datetime import UTC, datetime

import fakeredis

from tests.support.constants import PIPELINE_VERSION
from wke.core import keys
from wke.core.citations import seed_pin
from wke.core.models import Dossier
from wke.jobs.build.payload import dossier_payload, ptr_json


def store_dossier(client: fakeredis.FakeRedis, dossier: Dossier) -> None:
    """Write a dossier and its latest-build pointer as the worker does.

    Args:
        client: the fake Redis client.
        dossier: the dossier to store, under PIPELINE_VERSION.
    """
    page_id, rev_id = dossier.topic.page_id, seed_pin(dossier).rev_id
    client.set(keys.dossier(page_id, rev_id, PIPELINE_VERSION), dossier_payload(dossier))
    client.set(keys.ptr(page_id), ptr_json(rev_id, PIPELINE_VERSION, datetime.now(UTC)))


def cache_html(client: fakeredis.FakeRedis, rev_id: int, html: str) -> None:
    """Write Parsoid HTML to the revision cache in the pipeline's encoding.

    Args:
        client: the fake Redis client.
        rev_id: revision id the HTML belongs to.
        html: the Parsoid HTML.
    """
    packed = base64.b64encode(zlib.compress(html.encode("utf-8"))).decode("ascii")
    client.set(keys.wm_html(rev_id), packed)
