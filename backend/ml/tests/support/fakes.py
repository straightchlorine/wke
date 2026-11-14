"""Stand-ins for the embedder and the request that the inference gate tests need."""

from __future__ import annotations

import threading
from collections.abc import Mapping, Sequence

import numpy as np

from wke_ml.backends import Embedder, FloatArray


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
