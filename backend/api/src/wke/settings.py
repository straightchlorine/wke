"""Typed application configuration for wke-api: required fields have no default."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AnyHttpUrl, Field, RedisDsn, TypeAdapter, field_validator, validate_email
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Environment settings; a missing or invalid value stops the process at start."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    wikipedia_api_url: AnyHttpUrl = Field(
        description="Action API endpoint, e.g. https://en.wikipedia.org/w/api.php.",
    )
    wikipedia_rest_url: AnyHttpUrl = Field(
        description="Wikipedia REST endpoint, e.g. https://en.wikipedia.org/w/rest.php/v1.",
    )
    wikimedia_eventstreams_url: AnyHttpUrl = Field(
        description="EventStreams recentchange endpoint for wke-watcher.",
    )
    wikifeeds_url: AnyHttpUrl = Field(
        description="Wikifeeds featured-feed base URL for wke-trending.",
    )
    ml_url: AnyHttpUrl = Field(
        description="wke-ml base URL (ClusterIP, not routed by the Ingress).",
    )
    redis_url: RedisDsn = Field(
        description="Redis connection URL shared by cache, queue and counters.",
    )

    public_host: str = Field(
        description="Public hostname (and MCP allowed host), e.g. wke.piotrkrzysztof.dev.",
    )
    public_scheme: Literal["http", "https"] = Field(
        default="https",
        description=(
            "Scheme used to build every public-facing absolute URL (dossier "
            "links, the Link header, Job.result_url): 'https' in production; "
            "local dev sets PUBLIC_SCHEME=http."
        ),
    )
    wke_contact_email: str = Field(
        description=(
            "Contact address embedded in the Wikimedia User-Agent: an email "
            "address or an https URL, per the WMF User-Agent policy."
        ),
    )
    wke_port: int = Field(
        default=8000,
        ge=1,
        le=65535,
        description="TCP port wke-api listens on.",
    )

    watcher_metrics_port: int = Field(
        default=8000,
        ge=1,
        le=65535,
        description="TCP port the watcher serves /metrics on (python -m wke.watcher).",
    )

    lean_response: bool = Field(
        default=True,
        description=(
            "Leave the Key facts block out of every response and the per-section 'left out at "
            "this budget' lines out of the dossier part and the budget. 'false' serves "
            "both in every response and counts them against the budget, as before."
        ),
    )
    summary_sections: int = Field(
        default=8,
        ge=1,
        description=(
            "Most sections summarized per dossier build; the rule picks "
            "round(prose tokens / 2000), at least 3."
        ),
    )
    num_beams: int = Field(
        default=1,
        ge=1,
        le=4,
        description="Beam count passed to wke-ml /v1/summarize.",
    )
    subsection_headings: bool = Field(
        default=True,
        description=(
            "Show a subsection's heading where passages of a structural build jump "
            "between subsections; false renders as before."
        ),
    )
    analyze_deadline_ms: int = Field(
        default=8000,
        ge=1,
        description="Deadline in ms of each wke-ml /v1/analyze call made by a dossier build.",
    )
    analyze_retries: int = Field(
        default=0,
        ge=0,
        description=(
            "Retries of a failed build analyze call; http_4xx is never retried, "
            "a timeout only with ANALYZE_RETRY_ON_TIMEOUT."
        ),
    )
    analyze_retry_pause_ms: int = Field(
        default=1000,
        ge=0,
        description="Pause in ms before each analyze retry.",
    )
    analyze_retry_on_timeout: bool = Field(
        default=False,
        description="Retry an analyze call that timed out (it burns the deadline again).",
    )
    dossier_structural_ttl_seconds: int = Field(
        default=600,
        ge=1,
        description="Lifetime in seconds of a structural (wke-ml unavailable) dossier.",
    )
    log_level: str = Field(
        default="INFO",
        description="Python logging level name.",
    )
    log_format: Literal["json", "console"] = Field(
        default="json",
        description=(
            "Log line format: 'json', one object per line for a log collector; "
            "'console', colored lines for a terminal."
        ),
    )
    pod_cidr: str = Field(
        description="Traefik pod CIDR for uvicorn --forwarded-allow-ips.",
    )

    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        description="Allowed CORS origins, comma-separated in the env var.",
    )

    queue_cap: int = Field(
        default=20,
        ge=1,
        description="Max depth of q:interactive before an admission gets 503 queue_full.",
    )
    background_queue_cap: int = Field(
        default=50,
        ge=1,
        description=(
            "Max depth of q:background before an admission gets 503 queue_full. "
            "Kept above wke-trending's MAX_TOPICS (40) so a nightly prebuild run "
            "never rejects its own topics."
        ),
    )
    wm_budget_per_minute: int = Field(
        default=150,
        ge=1,
        description="Shared Wikimedia call budget per epoch minute (wm:budget:{minute}).",
    )
    pipeline_version: str = Field(
        description="Pipeline version string embedded in dossier and job keys.",
    )
    selection_rating: bool = Field(
        default=False,
        description=(
            "Pack dossiers by a local model's 0 to 3 rating of each passage once a stored "
            "rating is complete: a background stage rates every built dossier through wke-ml "
            "POST /v1/rate. Off: nothing is rated, queued or read."
        ),
    )
    rating_deadline_seconds: int = Field(
        default=1800,
        ge=1,
        description="Longest one rating attempt of an article; the next attempt resumes it.",
    )
    rating_call_timeout_seconds: int = Field(
        default=120,
        ge=1,
        description="Timeout and X-Deadline-Ms of one wke-ml rating call (one passage).",
    )
    rating_min_coverage: float = Field(
        default=0.9,
        ge=0.0,
        le=1.0,
        description=(
            "Share of an article's prose passages that must hold a real score (not null) for "
            "its rating to be applied; below it the dossier is packed by its stored relevance."
        ),
    )
    rating_max_attempts: int = Field(
        default=3,
        ge=1,
        description=(
            "Attempts of one rating stage that end unavailable or over the deadline without "
            "storing a new score before it is given up until the next build."
        ),
    )
    rating_retry_backoff_seconds: int = Field(
        default=60,
        ge=0,
        description="Wait before a failed rating stage is tried again; doubles per attempt.",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: object) -> object:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("wke_contact_email", mode="after")
    @classmethod
    def _validate_contact(cls, value: str) -> str:
        if value.startswith("https://"):
            TypeAdapter(AnyHttpUrl).validate_python(value)
            return value
        validate_email(value)
        return value

    @field_validator("log_level", mode="after")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        normalized = value.upper()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if normalized not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(allowed)}, got {value!r}")
        return normalized


# model_validate({}) reads the environment as Settings() does and type-checks
settings = Settings.model_validate({})
