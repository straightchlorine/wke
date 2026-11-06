"""Unit tests for the stub backends and the build_* dispatch."""

from __future__ import annotations

import numpy as np
import pytest

from wke_ml.backends import (
    EMBED_DIM,
    HashEmbedder,
    StubSummarizer,
    build_embedder,
    build_summarizer,
)
from wke_ml.settings import Settings


def test_stub_summarizer_is_deterministic_and_reports_truncation() -> None:
    text = "The quick brown fox jumps over the lazy dog."
    summarizer = StubSummarizer()

    first = summarizer.summarize(text, 1, 30, 96)
    second = summarizer.summarize(text, 1, 30, 96)
    short = summarizer.summarize(text, 1, 30, 10)

    assert first == second
    assert first[1] == len(text.split())
    assert first[2] is False
    assert short[0].endswith(": The quick ")
    assert short[2] is True


def test_hash_embedder_returns_unit_rows_of_embed_dim() -> None:
    vectors = HashEmbedder().embed(["alpha beta", "gamma"])

    assert vectors.shape == (2, EMBED_DIM)
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-5)


def test_hash_embedder_ignores_case_and_is_deterministic() -> None:
    vectors = HashEmbedder().embed(["Alpha BETA", "alpha beta", "alpha beta"])

    assert np.array_equal(vectors[0], vectors[1])
    assert np.array_equal(vectors[1], vectors[2])


@pytest.mark.parametrize("text", ["", "   "])
def test_hash_embedder_handles_text_without_tokens(text: str) -> None:
    vectors = HashEmbedder().embed([text])

    assert vectors.shape == (1, EMBED_DIM)
    assert np.all(np.isfinite(vectors))


def test_build_functions_return_stub_classes_for_stub_backend(settings_stub: Settings) -> None:
    assert isinstance(build_embedder(settings_stub), HashEmbedder)
    assert isinstance(build_summarizer(settings_stub), StubSummarizer)
