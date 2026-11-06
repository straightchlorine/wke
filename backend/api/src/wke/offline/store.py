"""Load stored dossiers and their cached HTML from Redis or a pulled folder."""

from __future__ import annotations

import base64
import json
import zlib
from pathlib import Path

import redis

from wke.core import keys
from wke.core.models import Dossier

DEFAULT_REDIS = "redis://localhost:6379/0"


def connect(url: str = DEFAULT_REDIS) -> redis.Redis:
    """Open a synchronous Redis client.

    Args:
        url: Redis URL.

    Returns:
        A client that decodes responses to str.
    """
    # redis-py types from_url's **kwargs loosely, so strict mode calls the result partly unknown.
    return redis.Redis.from_url(url, decode_responses=True)  # pyright: ignore[reportUnknownMemberType]


def load_dossier(
    client: redis.Redis, page_id: int, rev_id: int | None = None, pipeline_version: str = ""
) -> Dossier | None:
    """Read one stored dossier.

    Args:
        client: Redis client.
        page_id: Wikipedia page id.
        rev_id: revision to read; the latest build pointer when None.
        pipeline_version: pipeline version of the key; taken from the
            pointer when empty.

    Returns:
        The Dossier, or None when it is not stored.
    """
    if rev_id is None or not pipeline_version:
        raw_ptr = client.get(keys.ptr(page_id))
        if raw_ptr is None:
            return None
        pointer = json.loads(raw_ptr)
        if rev_id is None:
            rev_id = int(pointer["rev_id"])
        if not pipeline_version:
            pipeline_version = str(pointer["pipeline_version"])
    raw = client.get(keys.dossier(page_id, rev_id, pipeline_version))
    return Dossier.model_validate_json(raw) if raw else None


def load_pulled(pulled_dir: str, page_id: int) -> Dossier | None:
    """Rebuild a dossier from the rest-32000.json of an earlier pull.

    The 32000-token view of a dossier that fits whole carries every section
    and chunk, so it validates as a Dossier. Used for topics whose Redis
    entry has expired. A view packed without summaries carries none, so a
    section the original had summarised comes back with state "done" and no
    summary.

    Args:
        pulled_dir: folder holding pull.py output (<page_id>-<slug>/).
        page_id: Wikipedia page id.

    Returns:
        The Dossier, or None when there is no pull of that page or its
        32000-token view left chunks out.
    """
    folder = next(Path(pulled_dir).glob(f"{page_id}-*"), None)
    path = folder / "rest-32000.json" if folder else None
    if path is None or not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("budget", {}).get("omitted_chunks"):
        return None
    for view_only in ("freshness", "budget", "links"):
        data.pop(view_only, None)
    return Dossier.model_validate(data)


def load_pulled_html(folder: Path | None, rev_id: int) -> str | None:
    """Read the source HTML a pull stored next to its dossier.

    Args:
        folder: the pulled dossier folder, or None when the page was not pulled.
        rev_id: revision id the dossier is pinned to.

    Returns:
        The HTML, or None when the folder holds no file for that revision.
    """
    path = folder / f"source-{rev_id}.html" if folder is not None else None
    return path.read_text(encoding="utf-8") if path is not None and path.exists() else None


def load_html(client: redis.Redis, rev_id: int) -> str | None:
    """Read the cached Parsoid HTML of a revision.

    Args:
        client: Redis client.
        rev_id: revision id.

    Returns:
        The HTML, or None when the 24 h cache is cold.
    """
    raw = client.get(keys.wm_html(rev_id))
    return zlib.decompress(base64.b64decode(raw)).decode("utf-8") if raw else None


def stored_page_ids(client: redis.Redis) -> list[int]:
    """List the page ids that have a latest-build pointer.

    Args:
        client: Redis client.

    Returns:
        Page ids in ascending order.
    """
    # scan_iter is annotated as a bare Iterator; with decode_responses it yields str.
    found: list[str] = list(client.scan_iter("ptr:*", count=1000))  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    return sorted(int(key.split(":", 1)[1]) for key in found)
