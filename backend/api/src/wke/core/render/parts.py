"""The selectable parts of a dossier response and the parser of the `parts` value."""

from __future__ import annotations

from typing import Final, Literal, get_args

from wke.core.errors import ApiException
from wke.core.models import DossierContent, DossierMetadata, DossierResponse, DossierView

Part = Literal["dossier", "metadata", "sources"]

ALL_PARTS: Final[frozenset[Part]] = frozenset(get_args(Part))
DEFAULT_PARTS: Final[frozenset[Part]] = frozenset({"dossier"})

_CODES: Final[dict[Part, str]] = {"dossier": "d", "metadata": "m", "sources": "s"}
_BY_NAME: Final[dict[str, Part]] = {part: part for part in ALL_PARTS}
ALL_PARTS_ORDER: Final[tuple[Part, ...]] = ("dossier", "metadata", "sources")


def parse_parts(raw: str | None) -> frozenset[Part]:
    """Parse the raw `parts` value: a comma list over dossier, metadata, sources.

    Args:
        raw: the raw value, or None when the parameter was omitted.

    Returns:
        frozenset[Part]: the selected parts; DEFAULT_PARTS when raw is None.
        Order and duplicates in raw do not matter.

    Raises:
        ApiException: 422 validation_error when a token is unknown, the value
            is empty, or the selection does not contain dossier.
    """
    if raw is None:
        return DEFAULT_PARTS
    selected: set[Part] = set()
    for token in raw.split(","):
        part = _BY_NAME.get(token.strip().lower())
        if part is None:
            raise ApiException(
                422,
                "validation_error",
                detail=f"unknown part {token.strip()!r}; use dossier, metadata, sources",
            )
        selected.add(part)
    if "dossier" not in selected:
        raise ApiException(422, "validation_error", detail="parts must include dossier")
    return frozenset(selected)


def parts_code(parts: frozenset[Part]) -> str:
    """Return the short code of a selection, used in cache keys.

    Args:
        parts: the selected parts.

    Returns:
        str: "p" followed by one letter per part in fixed order, such as "pdm".
    """
    return "p" + "".join(_CODES[part] for part in ALL_PARTS_ORDER if part in parts)


def to_response(view: DossierView, parts: frozenset[Part]) -> DossierResponse:
    """Map a packed view to the JSON response carrying the selected parts.

    Args:
        view: a DossierView produced by build_view.
        parts: the selected parts; "dossier" is always written.

    Returns:
        DossierResponse: the dossier part and the licence notice, plus the
        metadata and sources parts when selected (None otherwise).
    """
    return DossierResponse(
        license_notice=view.license_notice,
        dossier=DossierContent(sections=view.sections, chunks=view.chunks, graph=view.graph),
        metadata=(
            DossierMetadata(
                id=view.id,
                topic=view.topic,
                build=view.build,
                freshness=view.freshness,
                budget=view.budget,
                links=view.links,
            )
            if "metadata" in parts
            else None
        ),
        sources=view.citations if "sources" in parts else None,
    )


def response_json(response: DossierResponse) -> str:
    """Serialise a response for every route: aliases on, unselected parts left out.

    Args:
        response: the mapped response.

    Returns:
        str: the JSON body, with `self` (not `self_`) in the links and no
        metadata or sources key when that part was not selected.
    """
    left_out = {name for name in ("metadata", "sources") if getattr(response, name) is None}
    return response.model_dump_json(by_alias=True, exclude=left_out)
