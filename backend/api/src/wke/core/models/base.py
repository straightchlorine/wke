"""Base model shared by every WKE schema."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class WkeModel(BaseModel):
    """Base model: forbid unknown fields everywhere in the data model."""

    model_config = ConfigDict(extra="forbid")
