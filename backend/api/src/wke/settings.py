"""Typed application configuration for wke-api: required fields have no default."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AnyHttpUrl, EmailStr, Field, RedisDsn, TypeAdapter, field_validator
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
    log_level: str = Field(
        default="INFO",
        description="Python logging level name.",
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
        TypeAdapter(EmailStr).validate_python(value)
        return value

    @field_validator("log_level", mode="after")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        normalized = value.upper()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if normalized not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(allowed)}, got {value!r}")
        return normalized


settings = Settings()
