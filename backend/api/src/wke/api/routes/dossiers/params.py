"""Query and body parsing and ETag helpers shared by the dossier routes."""

from __future__ import annotations

from typing import Any, Literal

from wke.api.etag import compute_etag
from wke.core.errors import ApiException
from wke.core.models import DossierView
from wke.core.models.budgets import BUDGETS, BudgetTokens
from wke.core.render.parts import DEFAULT_PARTS, Part, parts_code
from wke.core.titles import MAX_TITLE_LENGTH, MIN_TITLE_LENGTH, TITLE_PATTERN

DEFAULT_BUDGET: BudgetTokens = 8000

# A string Literal coerces from the query string and yields openapi.yaml's enum.
FormatParam = Literal["json", "md"]

# pydantic 2.13 does not coerce "8000" into Literal[2000, 8000, 32000], so
# budget is parsed by parse_budget and its schema republished via openapi_extra.
_BUDGET_ALIASES: dict[str, BudgetTokens] = {"2k": 2000, "8k": 8000, "32k": 32000}


def parse_budget(raw: str | None) -> BudgetTokens:
    """Parse and validate the raw `budget` query string.

    Args:
        raw: the raw query string value, or None if the parameter was
            omitted.

    Returns:
        BudgetTokens: one of 2000, 8000 or 32000.

    Raises:
        ApiException: 422 validation_error if raw is not one of 2000,
            8000, 32000 or their 2k/8k/32k aliases.
    """
    if raw is None:
        return DEFAULT_BUDGET
    normalized = raw.strip().lower()
    if normalized in _BUDGET_ALIASES:
        return _BUDGET_ALIASES[normalized]
    try:
        value = int(raw)
    except ValueError:
        value = None
    for budget in BUDGETS:
        if budget == value:
            return budget
    raise ApiException(
        422,
        "validation_error",
        detail=f"budget must be 2k, 8k or 32k (or 2000, 8000, 32000); got {raw!r}.",
    )


def parse_dossier_request(payload: dict[str, Any]) -> tuple[str, bool]:
    """Validate the POST /api/v1/dossiers body against the openapi.yaml schema.

    Args:
        payload: the decoded JSON object (FastAPI rejects any other JSON type).

    Returns:
        tuple[str, bool]: (title, refresh).

    Raises:
        ApiException: 422 validation_error on any schema violation.
    """
    extra_keys = set(payload) - {"title", "refresh"}
    if extra_keys:
        raise ApiException(
            422, "validation_error", detail=f"unexpected field(s): {sorted(extra_keys)}."
        )
    title = payload.get("title")
    # fullmatch: "$" alone would let a title end in a newline.
    if (
        not isinstance(title, str)
        or not (MIN_TITLE_LENGTH <= len(title) <= MAX_TITLE_LENGTH)
        or not TITLE_PATTERN.fullmatch(title)
    ):
        raise ApiException(
            422,
            "validation_error",
            detail="title is required and must be a Wikipedia article title.",
        )
    refresh = payload.get("refresh", False)
    if not isinstance(refresh, bool):
        raise ApiException(422, "validation_error", detail="refresh must be a boolean.")
    return title, refresh


def parse_format(raw: FormatParam) -> Literal["json", "markdown"]:
    """Map the public `format` value to the service's internal fmt literal.

    Args:
        raw: "json" or "md" (already validated by the FormatParam type).

    Returns:
        Literal["json", "markdown"]: "json" or "markdown".
    """
    return "markdown" if raw == "md" else "json"


def view_etag(
    view: DossierView,
    budget: BudgetTokens,
    fmt: Literal["json", "markdown"],
    include_summaries: bool,
    links: bool = False,
    parts: frozenset[Part] = DEFAULT_PARTS,
) -> str:
    """Compute the ETag for a packed view, shared by the JSON and Markdown routes.

    Args:
        view: the packed dossier view being served.
        budget: the parsed token budget.
        fmt: "json" or "markdown".
        include_summaries: whether the view was packed with summaries.
        links: whether the Markdown carries inline links.
        parts: the selected response parts.

    Returns:
        str: the quoted ETag value.
    """
    return compute_etag(
        view.freshness.pinned_rev_id,
        view.build.pipeline_version,
        budget,
        fmt,
        view.build.state,
        view.build.summaries_done,
        include_summaries,
        links,
        parts_code(parts),
    )
