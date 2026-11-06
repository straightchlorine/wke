"""Configuration for the wke-ml inference service.

Read from environment via pydantic-settings with prefix WKE_ML_. Model
revisions are pinned so the running container's behaviour matches the
image it was built from; the defaults match the revisions the image
build downloads (the Dockerfile build args).
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from wke_ml.logging_setup import LogFormat, LogLevel


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="WKE_ML_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    backend: Literal["torch", "stub"] = Field(
        default="torch",
        description=(
            "Inference backend: torch (real models) or stub (deterministic, no torch import)."
        ),
    )

    embed_model: str = Field(default="sentence-transformers/all-MiniLM-L6-v2")
    embed_model_revision: str = Field(default="1110a243")

    summarize_model: str = Field(default="sshleifer/distilbart-cnn-6-6")
    summarize_model_revision: str = Field(default="d2fde4ca")

    max_input_tokens: int = Field(default=512, ge=1)

    omp_num_threads: int = Field(default=2, ge=1)

    queue_max_wait: int = Field(default=4, ge=0)
    stuck_after_seconds: float = Field(
        default=300.0,
        gt=0,
        description="/healthz fails once one inference job has held the slot this long.",
    )

    kmeans_seed: int = Field(default=42)
    kmeans_max_k: int = Field(default=6, ge=2)
    kmeans_chunks_per_cluster: int = Field(default=6, ge=1)
    edge_similarity_threshold: float = Field(default=0.35, ge=-1.0, le=1.0)
    edge_top_n: int = Field(default=2, ge=0)

    log_level: LogLevel = Field(default="INFO")
    # json: one object per line for a log collector; console: colored lines for a terminal.
    log_format: LogFormat = Field(default="json")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Build and cache the process-wide Settings instance.

    Returns:
        Settings: the cached instance, constructed once per process.
    """
    return Settings()
