"""Fail-fast tests for wke.settings.Settings."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from tests.support.constants import REQUIRED_ENV
from wke.settings import Settings


def _set_all(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)


def test_all_required_vars_present_constructs(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_all(monkeypatch)
    monkeypatch.delenv("WKE_PORT", raising=False)
    monkeypatch.delenv("WATCHER_METRICS_PORT", raising=False)
    monkeypatch.delenv("LOG_FORMAT", raising=False)

    s = Settings.model_validate({})

    assert str(s.wikipedia_api_url) == REQUIRED_ENV["WIKIPEDIA_API_URL"]
    assert s.pipeline_version == REQUIRED_ENV["PIPELINE_VERSION"]
    assert s.public_scheme == "https"
    assert s.wke_port == 8000
    assert s.watcher_metrics_port == 8000
    assert s.log_format == "json"
    assert s.summary_sections == 8
    assert s.num_beams == 1
    assert s.queue_cap == 20
    assert s.wm_budget_per_minute == 150


@pytest.mark.parametrize("missing_key", sorted(REQUIRED_ENV))
def test_missing_required_var_raises(monkeypatch: pytest.MonkeyPatch, missing_key: str) -> None:
    _set_all(monkeypatch)
    monkeypatch.delenv(missing_key, raising=False)

    with pytest.raises(ValidationError):
        Settings.model_validate({})


def test_cors_origins_parses_comma_separated(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_all(monkeypatch)
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:8080, https://wke.piotrkrzysztof.dev ")

    s = Settings.model_validate({})

    assert s.cors_origins == ["http://localhost:8080", "https://wke.piotrkrzysztof.dev"]


def test_cors_origins_defaults_to_empty_list(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_all(monkeypatch)
    monkeypatch.delenv("CORS_ORIGINS", raising=False)

    s = Settings.model_validate({})

    assert s.cors_origins == []


def test_cors_origins_empty_string_is_an_empty_list(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_all(monkeypatch)
    monkeypatch.setenv("CORS_ORIGINS", "")

    s = Settings.model_validate({})

    assert s.cors_origins == []


def test_invalid_public_scheme_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_all(monkeypatch)
    monkeypatch.setenv("PUBLIC_SCHEME", "ftp")

    with pytest.raises(ValidationError):
        Settings.model_validate({})


def test_invalid_log_level_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_all(monkeypatch)
    monkeypatch.setenv("LOG_LEVEL", "NOT_A_LEVEL")

    with pytest.raises(ValidationError):
        Settings.model_validate({})


def test_invalid_log_format_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_all(monkeypatch)
    monkeypatch.setenv("LOG_FORMAT", "pretty")

    with pytest.raises(ValidationError):
        Settings.model_validate({})


def test_log_level_is_case_insensitive_and_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_all(monkeypatch)
    monkeypatch.setenv("LOG_LEVEL", "debug")

    s = Settings.model_validate({})

    assert s.log_level == "DEBUG"


def test_invalid_contact_email_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_all(monkeypatch)
    monkeypatch.setenv("WKE_CONTACT_EMAIL", "not-an-email")

    with pytest.raises(ValidationError):
        Settings.model_validate({})


def test_contact_https_url_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_all(monkeypatch)
    monkeypatch.setenv("WKE_CONTACT_EMAIL", "https://github.com/straightchlorine/wke")

    s = Settings.model_validate({})

    assert s.wke_contact_email == "https://github.com/straightchlorine/wke"


def test_watcher_metrics_port_reads_the_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """WATCHER_METRICS_PORT is the name the justfile and k8s set."""
    _set_all(monkeypatch)
    monkeypatch.setenv("WATCHER_METRICS_PORT", "8012")

    assert Settings.model_validate({}).watcher_metrics_port == 8012
