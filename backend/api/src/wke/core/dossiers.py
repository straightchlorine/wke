"""Reads of the build state a stored dossier is in.

Both the dossier service and the trending job need the state out of JSON they
do not want to validate in full, so the parse lives here once.
"""

from __future__ import annotations

from pydantic import BaseModel, ValidationError

from wke.core.models import DossierState


class _StoredPointer(BaseModel):
    """The part of `ptr:{page_id}` a reader needs."""

    rev_id: int


class _StoredBuild(BaseModel):
    """The part of a stored dossier's `build` a reader needs."""

    state: str | None = None


class _StoredDossier(BaseModel):
    """The part of a stored dossier the state reads need, without the rest."""

    build: _StoredBuild = _StoredBuild()


def pointer_rev_id(ptr_raw: str) -> int | None:
    """Read the revision id out of a stored `ptr:{page_id}` value.

    Args:
        ptr_raw: the stored pointer JSON.

    Returns:
        int | None: the latest built revision, or None if the pointer is
        unreadable.
    """
    try:
        return _StoredPointer.model_validate_json(ptr_raw).rev_id
    except ValidationError:
        return None


def state_from_dossier_json(dossier_raw: str | None) -> DossierState:
    """Read build.state out of a stored dossier's JSON without validating it.

    Args:
        dossier_raw: the stored dossier JSON, or None if it is missing.

    Returns:
        DossierState: "none" if missing or unreadable, "ready" if the build
        is complete, "partial" otherwise.
    """
    if dossier_raw is None:
        return "none"
    try:
        stored = _StoredDossier.model_validate_json(dossier_raw)
    except ValidationError:
        return "none"
    return "ready" if stored.build.state == "complete" else "partial"
