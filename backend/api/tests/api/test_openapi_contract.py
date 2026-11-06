"""The runtime OpenAPI document matches the contract file and the package metadata.

`app.openapi()` must expose the same (path, method) pairs and the same
component schema names as the OpenAPI contract file (skipped when that
file is not in the checkout), outside its `internal` tag (that tag is the
wke-api -> wke-ml wire protocol, served by wke-ml, not this app).
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

from wke.api.app import create_app

OPENAPI_YAML = Path(__file__).parents[4] / "docs" / "internal" / "architecture" / "openapi.yaml"
PYPROJECT = Path(__file__).parents[2] / "pyproject.toml"
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


@pytest.fixture(scope="module")
def spec() -> dict[str, Any]:
    if not OPENAPI_YAML.is_file():
        pytest.skip("OpenAPI contract file is not in this checkout")
    return yaml.safe_load(OPENAPI_YAML.read_text())


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    return create_app().openapi()


def _non_internal_path_methods(document: dict[str, Any]) -> set[tuple[str, str]]:
    return {
        (path, method)
        for path, operations in document["paths"].items()
        for method, operation in operations.items()
        if method in HTTP_METHODS and "internal" not in operation.get("tags", [])
    }


def _parameter_schema(operation: dict[str, Any], name: str) -> dict[str, Any]:
    for param in operation.get("parameters", []):
        if param["name"] == name:
            return param["schema"]
    raise AssertionError(f"no {name!r} parameter in operation {operation.get('operationId')}")


def test_paths_and_methods_match_openapi_yaml(spec: dict[str, Any], schema: dict[str, Any]) -> None:
    expected = _non_internal_path_methods(spec)
    actual = _non_internal_path_methods(schema)

    only_in_yaml = expected - actual
    only_in_app = actual - expected
    assert not only_in_yaml and not only_in_app, (
        f"paths/methods only in openapi.yaml: {sorted(only_in_yaml)}\n"
        f"paths/methods only in app.openapi(): {sorted(only_in_app)}"
    )


def test_schema_names_match_openapi_yaml(spec: dict[str, Any], schema: dict[str, Any]) -> None:
    expected = set(spec["components"]["schemas"])
    actual = set(schema["components"]["schemas"])

    only_in_yaml = expected - actual
    only_in_app = actual - expected
    assert not only_in_yaml and not only_in_app, (
        f"schemas only in openapi.yaml: {sorted(only_in_yaml)}\n"
        f"schemas only in app.openapi(): {sorted(only_in_app)}"
    )


def test_budget_and_format_params_match_openapi_yaml(
    spec: dict[str, Any], schema: dict[str, Any]
) -> None:
    """The budget and format params carry the Budget and Format component schemas.

    A Literal-typed FastAPI param and a `type: string` component would both
    pass the path and method check, so type, enum and default are compared.
    FastAPI's own cosmetic `title` is not part of the contract.
    """
    operation = schema["paths"]["/api/v1/dossiers/{page_id}"]["get"]

    for param, component in (("budget", "Budget"), ("format", "Format")):
        expected = spec["components"]["parameters"][component]["schema"]
        actual = _parameter_schema(operation, param)
        for key in ("type", "enum", "default"):
            assert actual.get(key) == expected.get(key), (param, key, actual, expected)


def test_declared_responses_and_post_body_match_openapi_yaml(
    spec: dict[str, Any], schema: dict[str, Any]
) -> None:
    """Every status code the contract declares for a dossier or job route is declared at runtime.

    The POST body schema must not be open-ended, and error bodies are ApiError.
    """
    routes = [
        ("/api/v1/dossiers", "post"),
        ("/api/v1/dossiers/{page_id}", "get"),
        ("/api/v1/dossiers/{page_id}.md", "get"),
        ("/api/v1/dossiers/{page_id}/rev/{rev_id}", "get"),
        ("/api/v1/jobs/{job_id}", "get"),
    ]
    for path, method in routes:
        expected = set(spec["paths"][path][method]["responses"])
        actual = set(schema["paths"][path][method]["responses"])
        assert expected <= actual, (path, method, sorted(expected - actual))

    body = schema["paths"]["/api/v1/dossiers"]["post"]["requestBody"]
    body_schema = body["content"]["application/json"]["schema"]
    yaml_body = spec["paths"]["/api/v1/dossiers"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    for key in ("required", "additionalProperties"):
        assert body_schema[key] == yaml_body[key]
    assert body_schema["properties"]["title"] == yaml_body["properties"]["title"]

    not_built = schema["paths"]["/api/v1/dossiers/{page_id}"]["get"]["responses"]["404"]
    ref = not_built["content"]["application/problem+json"]["schema"]["$ref"]
    assert ref == "#/components/schemas/ApiError"


def _refs(document: dict[str, Any]) -> set[str]:
    return set(re.findall(r'"\$ref": "([^"]+)"', json.dumps(document)))


def test_every_ref_points_at_a_declared_component(schema: dict[str, Any]) -> None:
    declared = {f"#/components/schemas/{name}" for name in schema["components"]["schemas"]}

    assert _refs(schema) - declared == set()


def test_runtime_version_is_the_package_version(schema: dict[str, Any]) -> None:
    project = tomllib.loads(PYPROJECT.read_text())["project"]

    assert schema["info"]["version"] == project["version"]


def test_internal_tag_text_names_no_workload(schema: dict[str, Any]) -> None:
    tags = {tag["name"]: tag.get("description", "") for tag in schema["tags"]}

    assert "wke" not in tags["internal"].lower()
