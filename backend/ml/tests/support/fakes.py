"""Stand-ins for the embedder and the request that the inference gate tests need."""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np

from wke_ml.backends import Embedder, FloatArray
from wke_ml.rating import Rating


class BlockingEmbedder:
    """Wraps an embedder so its call blocks until released.

    Holds the inference slot without mocking internals, so the gate's
    waiting-queue bookkeeping runs for real.
    """

    def __init__(self, inner: Embedder, started: threading.Event, release: threading.Event) -> None:
        self._inner = inner
        self._started = started
        self._release = release

    def embed(self, texts: Sequence[str]) -> FloatArray:
        """Signal that the call started, wait for the release, then embed.

        Args:
            texts: input strings to embed.

        Returns:
            FloatArray: the wrapped embedder's vectors.
        """
        self._started.set()
        self._release.wait()
        return self._inner.embed(texts)


class OppositeEmbedder:
    """Embedder that gives the first text (the lead) +x and every other text -x."""

    def embed(self, texts: Sequence[str]) -> FloatArray:
        """Embed the first text as (1, 0) and the rest as (-1, 0).

        Args:
            texts: input strings; only their count matters.

        Returns:
            FloatArray: one 2-d unit vector per text.
        """
        vectors = np.zeros((len(texts), 2), dtype=np.float32)
        vectors[:, 0] = -1.0
        if len(texts):
            vectors[0, 0] = 1.0
        return vectors


class ScriptedEmbedder:
    """Embedder that returns a fixed vector per text, so cosines are set by the test."""

    def __init__(self, vectors: Mapping[str, Sequence[float]]) -> None:
        self._vectors = vectors

    def embed(self, texts: Sequence[str]) -> FloatArray:
        """Look up each text's vector.

        Args:
            texts: input strings; each must be a key given at construction.

        Returns:
            FloatArray: one row per text.
        """
        return np.array([self._vectors[text] for text in texts], dtype=np.float32)


class FakeRequest:
    """Minimal stand-in for a Request: only the disconnect poll the gate uses."""

    def __init__(self, disconnected: bool = False) -> None:
        self._disconnected = disconnected

    async def is_disconnected(self) -> bool:
        """Report whether the client is gone.

        Returns:
            bool: the value given at construction.
        """
        return self._disconnected


class ProcessorList(list[Any]):
    """Stand-in for llama_cpp.LogitsProcessorList: a list that is callable."""

    def __call__(self, input_ids: Any, scores: Any) -> Any:
        """Pass the scores through every processor, as llama.cpp does."""
        for processor in self:
            scores = processor(input_ids, scores)
        return scores


class FakeLlama:
    """A model with digit tokens 10..13 (bare) and 20..23 (spaced); a test sets the logits."""

    VOCAB = 40

    def __init__(
        self,
        logits: Sequence[float] | None = None,
        generated: str = "2",
        spaced: bool = True,
    ) -> None:
        self._logits = list(logits) if logits is not None else self.row(favoured=3, boost=12.0)
        self._generated = generated
        self._spaced = spaced
        self.calls: list[dict[str, Any]] = []

    @classmethod
    def row(cls, favoured: int | None, boost: float) -> list[float]:
        """Build a logit row where one digit's two tokens stand out from a flat vocabulary."""
        row = [0.0] * cls.VOCAB
        if favoured is not None:
            row[10 + favoured] = boost
            row[20 + favoured] = boost
        return row

    def tokenize(self, text: bytes, add_bos: bool = True, special: bool = False) -> list[int]:
        """Tokenize a digit as one token; a spaced digit is two tokens when spaced is False."""
        spelling = text.decode()
        if spelling.strip() in {"0", "1", "2", "3"}:
            digit = int(spelling.strip())
            if not spelling.startswith(" "):
                return [10 + digit]
            return [20 + digit] if self._spaced else [30, 31]
        return [30, 31]

    def create_chat_completion(self, **kwargs: Any) -> dict[str, Any]:
        """Record the call; feed the logits row to a processor, else return generated text."""
        self.calls.append(kwargs)
        processor = kwargs.get("logits_processor")
        if processor is not None:
            processor([1, 2], list(self._logits))
            content = "3"
        else:
            content = self._generated
        return {"choices": [{"message": {"content": content}}]}


def fake_loader(llama: FakeLlama) -> Callable[[str, int, int], tuple[Any, type[list[Any]]]]:
    """Build a loader that hands out one fake model and counts its loads."""

    def loader(_path: str, _threads: int, _n_ctx: int) -> tuple[Any, type[list[Any]]]:
        loader.loads += 1  # type: ignore[attr-defined]
        return llama, ProcessorList

    loader.loads = 0  # type: ignore[attr-defined]
    return loader


class FakeRater:
    """A rater whose scores are set by a test, keyed by passage text.

    Passages listed in `fallback` come back flagged as rated by the generated digit.
    """

    def __init__(
        self,
        scores: dict[str, float | None] | None = None,
        fallback: frozenset[str] = frozenset(),
        error: Exception | None = None,
    ) -> None:
        self.model_file = "fake-model.gguf"
        self._scores = scores or {}
        self._fallback = fallback
        self._error = error
        self.calls: list[tuple[str, str, str]] = []

    def rate(
        self, title: str, lead: str, passage: str, should_stop: Callable[[], bool] | None = None
    ) -> Rating:
        """Return the score keyed by the passage text (1.0 if absent), or raise the given error."""
        self.calls.append((title, lead, passage))
        if self._error is not None:
            raise self._error
        return Rating(self._scores.get(passage, 1.0), passage in self._fallback)
