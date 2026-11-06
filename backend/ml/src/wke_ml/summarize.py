"""POST /v1/summarize: abstractive summary with distilbart-cnn-6-6."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from wke_ml.backends import Summarizer
from wke_ml.settings import Settings

# distilbart-cnn-6-6 (BART) has 1024 learned position embeddings; a
# max_length above that makes generate() raise IndexError, which would
# surface as a 500. 256 is a tighter ceiling that still covers every
# summary length the packing pipeline asks for.
MAX_SUMMARY_LENGTH = 256

# 128 new tokens let a summary of a 512-token input finish its last
# sentence; beam search with 4 beams is the model card setting.
DEFAULT_NUM_BEAMS = 4
DEFAULT_MIN_LENGTH = 30
DEFAULT_MAX_LENGTH = 128


class SummarizeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)
    num_beams: int = Field(default=DEFAULT_NUM_BEAMS, ge=1, le=4)
    min_length: int = Field(default=DEFAULT_MIN_LENGTH, ge=1, le=MAX_SUMMARY_LENGTH)
    max_length: int = Field(default=DEFAULT_MAX_LENGTH, ge=1, le=MAX_SUMMARY_LENGTH)
    input_chunk_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_length_order(self) -> SummarizeRequest:
        """Reject a min_length that exceeds max_length.

        Returns:
            SummarizeRequest: self, unchanged, once the ordering is confirmed valid.

        Raises:
            ValueError: min_length is greater than max_length.
        """
        if self.min_length > self.max_length:
            raise ValueError("min_length must not exceed max_length")
        return self


class MachineSummaryParams(BaseModel):
    num_beams: int
    min_length: int
    max_length: int
    input_tokens: int


class SummarizeResponse(BaseModel):
    kind: Literal["machine_summary"] = "machine_summary"
    text: str
    model: str
    model_revision: str
    params: MachineSummaryParams
    input_chunk_ids: list[str] = Field(default_factory=list)
    generated_at: datetime
    truncated: bool = Field(
        description="True when generation stopped on max_length instead of finishing its sentence."
    )
    infer_seconds: float | None = None


def summarize(
    payload: SummarizeRequest, backend: Summarizer, settings: Settings
) -> SummarizeResponse:
    """Run one summarization inference and build the response body.

    Args:
        payload: validated /v1/summarize request body.
        backend: summarization backend (stub or torch).
        settings: service settings, source of the pinned model identity.

    Returns:
        SummarizeResponse: the /v1/summarize response body.
    """
    text, input_tokens, truncated = backend.summarize(
        payload.text,
        num_beams=payload.num_beams,
        min_length=payload.min_length,
        max_length=payload.max_length,
    )
    return SummarizeResponse(
        text=text,
        model=settings.summarize_model,
        model_revision=settings.summarize_model_revision,
        params=MachineSummaryParams(
            num_beams=payload.num_beams,
            min_length=payload.min_length,
            max_length=payload.max_length,
            input_tokens=input_tokens,
        ),
        input_chunk_ids=payload.input_chunk_ids,
        generated_at=datetime.now(UTC),
        truncated=truncated,
    )
