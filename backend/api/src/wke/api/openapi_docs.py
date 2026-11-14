"""Runtime OpenAPI document: shared `responses=` entries and the component schema set."""

from __future__ import annotations

import json
from typing import Any, TypeGuard

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel

from wke.api.constants import API_TITLE, PACKAGE_VERSION
from wke.core.errors import PROBLEM_MEDIA_TYPE
from wke.core.models import Dossier, DossierListItem


def error_response(description: str) -> dict[str, Any]:
    """Build an OpenAPI response entry whose body is the shared ApiError schema.

    Args:
        description: the response description.

    Returns:
        dict[str, Any]: a `responses=` value for an application/problem+json body.
    """
    return {
        "description": description,
        "content": {PROBLEM_MEDIA_TYPE: {"schema": {"$ref": "#/components/schemas/ApiError"}}},
    }


# FastAPI auto-generates these for the default validation-error response.
# Every error body of this API is an ApiError, so custom_openapi() rewrites
# references to them onto ApiError and drops them from components.schemas.
_DEFAULT_VALIDATION_SCHEMAS = ("HTTPValidationError", "ValidationError")

# Nested wrapper models (Dossier.topic, Dossier.graph, DossierMetadata.links,
# Job.progress, LiveResponse.counters, MachineSummary.params) that the
# published contract inlines into their parent's properties instead of
# naming as their own component; pydantic always names them. Folded away
# by inline_wrapper_schemas below so the component name set matches.
_INLINE_WRAPPER_SCHEMAS = (
    "DossierTopic",
    "DossierGraph",
    "DossierLinks",
    "JobProgress",
    "LiveCounters",
    "MachineSummaryParams",
)


def _is_json_object(node: Any) -> TypeGuard[dict[str, Any]]:
    return isinstance(node, dict)


def _is_json_array(node: Any) -> TypeGuard[list[Any]]:
    return isinstance(node, list)


def inline_wrapper_schemas(node: Any, schemas: dict[str, Any]) -> Any:
    """Recursively replace $ref to an inline-wrapper schema with its body.

    Args:
        node: a JSON-schema fragment (dict, list, or scalar).
        schemas: components.schemas, to resolve $ref targets against.

    Returns:
        Any: the same shape as node, with any $ref to one of
        _INLINE_WRAPPER_SCHEMAS replaced by a copy of the target schema.
    """
    if _is_json_object(node):
        ref: str = node.get("$ref", "")
        ref_name = ref.rsplit("/", 1)[-1]
        if ref and ref_name in _INLINE_WRAPPER_SCHEMAS:
            return inline_wrapper_schemas(dict(schemas[ref_name]), schemas)
        return {key: inline_wrapper_schemas(value, schemas) for key, value in node.items()}
    if _is_json_array(node):
        return [inline_wrapper_schemas(item, schemas) for item in node]
    return node


def add_standalone_schema(schema: dict[str, Any], model: type[BaseModel]) -> None:
    """Register a pydantic model's schema even if no route returns it bare.

    Dossier and DossierListItem are contract components but pydantic
    emits them only when used directly in a response_model; the dossier
    routes return DossierResponse, which does not reference Dossier, so they
    must be added explicitly to keep the component set complete.

    Args:
        schema: the full openapi schema dict, mutated in place.
        model: a pydantic model class to add as `components.schemas[name]`.
    """
    model_schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
    defs: dict[str, Any] = model_schema.pop("$defs", {})
    schemas: dict[str, Any] = schema.setdefault("components", {}).setdefault("schemas", {})
    for name, definition in defs.items():
        schemas.setdefault(name, definition)
    schemas[model.__name__] = model_schema


_MCP_PATH_ITEM: dict[str, Any] = {
    "post": {
        "tags": ["machine"],
        "summary": "MCP streamable-http transport",
        "operationId": "mcp",
        "description": (
            "Model Context Protocol (streamable HTTP, stateless). Tools: "
            "search_topics, get_dossier, get_trending. Not a plain REST "
            "endpoint."
        ),
        "responses": {"200": {"description": "MCP JSON-RPC response"}},
    }
}


def custom_openapi(app: FastAPI) -> dict[str, Any]:
    """Build the OpenAPI schema: ApiError for every error body, no wrapper components.

    Args:
        app: the FastAPI application.

    Returns:
        dict[str, Any]: the OpenAPI document, cached on the app.
    """
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=API_TITLE,
        version=PACKAGE_VERSION,
        description=app.description,
        routes=app.routes,
        tags=[
            {"name": "search"},
            {"name": "dossiers"},
            {"name": "jobs"},
            {"name": "trending"},
            {"name": "live"},
            {"name": "status"},
            {"name": "machine", "description": "llms.txt and MCP endpoints"},
            {
                "name": "internal",
                "description": ("Internal: only the API may call the model service."),
            },
        ],
    )
    # Every error body is an ApiError: fold references to FastAPI's own
    # validation-error schemas onto it and drop them from components.schemas.
    raw = json.dumps(schema)
    for name in _DEFAULT_VALIDATION_SCHEMAS:
        raw = raw.replace(f"#/components/schemas/{name}", "#/components/schemas/ApiError")
    schema = json.loads(raw)
    for name in _DEFAULT_VALIDATION_SCHEMAS:
        schema.get("components", {}).get("schemas", {}).pop(name, None)

    add_standalone_schema(schema, Dossier)
    add_standalone_schema(schema, DossierListItem)

    schemas: dict[str, Any] = schema.setdefault("components", {}).setdefault("schemas", {})
    schema["paths"] = inline_wrapper_schemas(schema["paths"], schemas)
    schema["components"]["schemas"] = inline_wrapper_schemas(schemas, schemas)
    for name in _INLINE_WRAPPER_SCHEMAS:
        schema["components"]["schemas"].pop(name, None)

    schema["paths"]["/mcp"] = _MCP_PATH_ITEM

    app.openapi_schema = schema
    return schema
