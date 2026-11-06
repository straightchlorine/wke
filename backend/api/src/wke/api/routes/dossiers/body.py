"""Response bodies and token headers shared by every route that returns a dossier."""

from __future__ import annotations

from typing import Literal

from wke.core.models import DossierView
from wke.core.render import render_markdown
from wke.core.render.parts import Part, response_json, to_response
from wke.core.text.tokens import est_tokens


def dossier_body(
    view: DossierView,
    fmt: Literal["json", "markdown"],
    summaries: bool,
    links: bool,
    parts: frozenset[Part],
) -> tuple[str, str]:
    """Write the body of a dossier read in the requested format and parts.

    Args:
        view: the packed dossier view.
        fmt: "json" or "markdown".
        summaries: whether the view was packed with summaries.
        links: whether the Markdown carries inline links.
        parts: the selected response parts.

    Returns:
        tuple[str, str]: the body text and its media type.
    """
    if fmt == "markdown":
        return render_markdown(view, summaries, links, parts), "text/markdown"
    return response_json(to_response(view, parts)), "application/json"


def token_headers(view: DossierView, body: str) -> dict[str, str]:
    """Build the two token-count headers of a dossier body.

    Args:
        view: the packed dossier view.
        body: the body as delivered.

    Returns:
        dict[str, str]: WKE-Dossier-Tokens (the counted dossier part) and
        WKE-Total-Tokens (the whole body).
    """
    return {
        "WKE-Dossier-Tokens": str(view.budget.used_est_tokens),
        "WKE-Total-Tokens": str(est_tokens(body)),
    }
