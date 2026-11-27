"""The production config map sets an analyze deadline above the code default."""

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


def test_the_code_default_stays_at_8_seconds_and_no_retry() -> None:
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


def _refresh_cronjob() -> dict:
    return yaml.safe_load((K8S_BASE / "refresh.yaml").read_text())


def test_the_refresh_cronjob_runs_nightly_once_at_a_time_with_the_refresh_entrypoint() -> None:
    cronjob = _refresh_cronjob()
    spec = cronjob["spec"]
    container = spec["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]
    assert cronjob["kind"] == "CronJob"
    assert cronjob["metadata"]["name"] == "wke-refresh"
    assert spec["schedule"] == "0 1 * * *"
    assert spec["concurrencyPolicy"] == "Forbid"
    assert container["command"] == ["python", "-m", "wke.refresh"]
    assert container["image"].startswith("ghcr.io/straightchlorine/wke-api:")


def test_the_refresh_deadline_outlasts_the_thirty_minutes_it_asks_for_rebuilds() -> None:
    from wke.refresh.run import QUEUE_FULL_WAIT_SECONDS, REBUILD_PHASE_SECONDS

    deadline = _refresh_cronjob()["spec"]["jobTemplate"]["spec"]["activeDeadlineSeconds"]
    assert deadline > REBUILD_PHASE_SECONDS + QUEUE_FULL_WAIT_SECONDS


def test_the_refresh_cronjob_is_in_the_kustomization() -> None:
    resources = yaml.safe_load((K8S_BASE / "kustomization.yaml").read_text())["resources"]
    assert "refresh.yaml" in resources


def test_the_refresh_pod_may_reach_redis_and_dns_and_nothing_else() -> None:
    policies = {
        doc["metadata"]["name"]: doc
        for doc in yaml.safe_load_all((K8S_BASE / "networkpolicy.yaml").read_text())
    }
    refresh = policies["allow-egress-refresh"]["spec"]
    assert refresh["podSelector"] == {"matchLabels": {"app.kubernetes.io/name": "wke-refresh"}}
    ports = sorted(p["port"] for rule in refresh["egress"] for p in rule["ports"])
    assert ports == [53, 53, 6379]
    assert all("ipBlock" not in peer for rule in refresh["egress"] for peer in rule["to"])
    internet = policies["allow-egress-dns-https"]["spec"]["podSelector"]["matchExpressions"]
    assert "wke-refresh" not in internet[0]["values"]
    redis_in = policies["allow-ingress-redis"]["spec"]["ingress"][0]["from"]
    assert {"podSelector": {"matchLabels": {"app.kubernetes.io/name": "wke-refresh"}}} in redis_in
