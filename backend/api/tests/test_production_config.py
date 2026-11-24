"""The production ConfigMap sets the analyze deadline that the code default leaves at 8 s."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from wke.api.constants import ML_HTTP_TIMEOUT_SECONDS
from wke.api.mcp_server import GET_DOSSIER_WAIT_SECONDS
from wke.settings import Settings

K8S_BASE = Path(__file__).parents[3] / "k8s" / "base"

pytestmark = pytest.mark.skipif(
    not K8S_BASE.is_dir(), reason="the k8s manifests are not in the image"
)


def _config() -> dict[str, str]:
    return yaml.safe_load((K8S_BASE / "configmap.yaml").read_text())["data"]


def test_production_gives_one_analyze_attempt_15_seconds_and_no_retry() -> None:
    data = _config()
    assert data["ANALYZE_DEADLINE_MS"] == "15000"
    assert data.get("ANALYZE_RETRIES", "0") == "0"


def test_one_analyze_attempt_stays_under_the_mcp_wait_and_the_http_timeout() -> None:
    attempt = int(_config()["ANALYZE_DEADLINE_MS"]) / 1000
    assert attempt < GET_DOSSIER_WAIT_SECONDS
    assert attempt <= ML_HTTP_TIMEOUT_SECONDS


def test_the_code_default_stays_at_8_seconds_so_that_all_switches_off_equals_base() -> None:
    assert Settings.model_fields["analyze_deadline_ms"].default == 8000
    assert Settings.model_fields["analyze_retries"].default == 0


def test_the_api_deployment_reads_the_config_map_the_deadline_is_in() -> None:
    api = next(
        doc
        for doc in yaml.safe_load_all((K8S_BASE / "api.yaml").read_text())
        if doc["kind"] == "Deployment"
    )
    env_from = api["spec"]["template"]["spec"]["containers"][0]["envFrom"]
    assert {"configMapRef": {"name": "wke-config"}} in env_from
