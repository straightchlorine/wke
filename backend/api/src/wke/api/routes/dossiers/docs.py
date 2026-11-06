"""OpenAPI fragments for the dossier routes."""

from __future__ import annotations

from wke.api.openapi_docs import error_response
from wke.api.routes.dossiers.params import DEFAULT_BUDGET
from wke.core.models.budgets import BUDGETS
from wke.core.titles import MAX_TITLE_LENGTH, MIN_TITLE_LENGTH, TITLE_PATTERN

BUDGET_OPENAPI_PARAM = {
    "name": "budget",
    "in": "query",
    "schema": {"type": "integer", "enum": list(BUDGETS), "default": DEFAULT_BUDGET},
}

# parts is parsed by parse_parts (a comma list), so its schema is republished here.
PARTS_OPENAPI_PARAM = {
    "name": "parts",
    "in": "query",
    "description": (
        "Comma list over dossier, metadata, sources; it must contain dossier. "
        "Default dossier: the sections and passages alone, with no [cN] "
        "markers, no revision pin and no truncation signal. metadata adds the "
        "title, pin line, budget line and notices (JSON: id, topic, build, "
        "freshness, budget, links); sources adds the [cN] markers and the "
        "Sources list (JSON: citations). The budget counts the dossier part "
        "only. The licence notice is always present."
    ),
    "schema": {"type": "string", "default": "dossier"},
}

TOKEN_HEADERS = {
    "WKE-Dossier-Tokens": {
        "schema": {"type": "integer"},
        "description": (
            "Budget.used_est_tokens: the counted dossier part, never above the requested budget"
        ),
    },
    "WKE-Total-Tokens": {
        "schema": {"type": "integer"},
        "description": "chars/4 of the whole body as delivered, whatever parts were selected",
    },
}

NOT_MODIFIED_RESPONSE = {
    "description": "Not modified",
    "headers": {"ETag": {"schema": {"type": "string"}}},
}
NOT_BUILT_RESPONSE = error_response("No dossier built (not_built)")
RATE_LIMITED_RESPONSE = error_response("Client rate limit hit; Retry-After set")
MARKDOWN_CONTENT = {"text/markdown": {"schema": {"type": "string"}}}

DOSSIER_200_RESPONSE = {
    "description": "Packed dossier",
    "headers": TOKEN_HEADERS,
    "content": MARKDOWN_CONTENT,
}

POST_REQUEST_BODY = {
    "required": True,
    "content": {
        "application/json": {
            "schema": {
                "type": "object",
                "required": ["title"],
                "additionalProperties": False,
                "properties": {
                    "title": {
                        "type": "string",
                        "minLength": MIN_TITLE_LENGTH,
                        "maxLength": MAX_TITLE_LENGTH,
                        "pattern": TITLE_PATTERN.pattern,
                    },
                    "refresh": {"type": "boolean", "default": False},
                },
            }
        }
    },
}
