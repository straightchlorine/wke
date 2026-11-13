"""Embedding and summarization backends for wke-ml.

The torch backend loads sentence-transformers/all-MiniLM-L6-v2 and
sshleifer/distilbart-cnn-6-6 at pinned revisions. The stub backend
returns deterministic output and never imports torch, transformers or
sentence-transformers, so the FastAPI app can be constructed (and the
unit test suite can run) without paying the torch import and weight
download cost.
"""

# transformers and sentence-transformers leave from_pretrained, generate and
# encode partly untyped; the torch classes are the only code touching them.
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false

from __future__ import annotations

import hashlib
import logging
from collections.abc import Sequence
from typing import Protocol

import numpy as np
import numpy.typing as npt

from wke_ml.settings import Settings

logger = logging.getLogger(__name__)

EMBED_DIM = 384

FloatArray = npt.NDArray[np.float32]

LENGTH_PENALTY = 1.0
NO_REPEAT_NGRAM_SIZE = 3


class Embedder(Protocol):
    """Turns texts into normalized embedding vectors."""

    def embed(self, texts: Sequence[str]) -> FloatArray:
        """Embed texts.

        Args:
            texts: input strings to embed.

        Returns:
            FloatArray: float32 array of shape (len(texts), dim), one L2-normalized row per text.
        """


class Summarizer(Protocol):
    """Turns one text into an abstractive summary."""

    def summarize(
        self, text: str, num_beams: int, min_length: int, max_length: int
    ) -> tuple[str, int, bool]:
        """Summarize text.

        Args:
            text: the source text.
            num_beams: beam search width.
            min_length: minimum output length in tokens.
            max_length: maximum output length in tokens.

        Returns:
            tuple[str, int, bool]: summary text, input token count after
            truncation, and whether generation stopped on max_length.
        """


class HashEmbedder:
    """Deterministic feature-hash embedder used by the stub backend.

    Hashes each lowercased token into one of EMBED_DIM buckets with a
    sign derived from the same digest, then L2-normalizes the result.
    Two calls with the same text always produce the same vector, which
    is all the analyze pipeline needs from an embedder in tests.
    """

    def embed(self, texts: Sequence[str]) -> FloatArray:
        """Hash-embed and L2-normalize each text.

        Args:
            texts: input strings to embed.

        Returns:
            FloatArray: shape (len(texts), EMBED_DIM), one normalized row per text.
        """
        vectors = np.zeros((len(texts), EMBED_DIM), dtype=np.float32)
        for i, text in enumerate(texts):
            for token in text.lower().split():
                digest = hashlib.sha256(token.encode("utf-8")).digest()
                bucket = int.from_bytes(digest[:4], "big") % EMBED_DIM
                sign = 1.0 if digest[4] % 2 == 0 else -1.0
                vectors[i, bucket] += sign
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return vectors / norms


class StubSummarizer:
    """Deterministic summarizer used by the stub backend and unit tests."""

    def summarize(
        self, text: str, num_beams: int, min_length: int, max_length: int
    ) -> tuple[str, int, bool]:
        """Build a deterministic stand-in summary.

        Args:
            text: the source text.
            num_beams: unused; kept for interface parity with TorchSummarizer.
            min_length: unused; kept for interface parity with TorchSummarizer.
            max_length: truncates the echoed body to this many characters.

        Returns:
            tuple[str, int, bool]: stub summary text, whitespace-split token
            count of text, and whether the echoed body was cut at max_length
            characters.
        """
        input_tokens = len(text.split())
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
        stripped = text.strip()
        limit = max(max_length, 1)
        return f"stub-summary-{digest}: {stripped[:limit]}", input_tokens, len(stripped) > limit


class TorchEmbedder:
    """sentence-transformers all-MiniLM-L6-v2 embedder, pinned by revision."""

    def __init__(self, model_name: str, revision: str) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name, revision=revision)

    def embed(self, texts: Sequence[str]) -> FloatArray:
        """Encode texts with the pinned SentenceTransformer.

        Args:
            texts: input strings to embed.

        Returns:
            FloatArray: shape (len(texts), EMBED_DIM), L2-normalized rows.
        """
        vectors = self._model.encode(list(texts), normalize_embeddings=True, convert_to_numpy=True)
        return np.asarray(vectors, dtype=np.float32)


class TorchSummarizer:
    """distilbart-cnn-6-6 summarizer, fp32, safetensors, pinned by revision."""

    def __init__(self, model_name: str, revision: str, max_input_tokens: int) -> None:
        import torch
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        self._tokenizer = AutoTokenizer.from_pretrained(model_name, revision=revision)
        try:
            self._model = AutoModelForSeq2SeqLM.from_pretrained(
                model_name, revision=revision, use_safetensors=True, dtype=torch.float32
            )
        except OSError:
            # The pinned revision predates this repo's safetensors conversion
            # (no model.safetensors at that commit); fall back to the
            # pytorch_model.bin present at the same pinned revision.
            logger.warning(
                "no safetensors weights at %s@%s; loading pytorch_model.bin (pickle) instead",
                model_name,
                revision,
            )
            self._model = AutoModelForSeq2SeqLM.from_pretrained(
                model_name, revision=revision, use_safetensors=False, dtype=torch.float32
            )
        self._model.eval()
        self._max_input_tokens = max_input_tokens

    def summarize(
        self, text: str, num_beams: int, min_length: int, max_length: int
    ) -> tuple[str, int, bool]:
        """Abstractive summarization with distilbart-cnn-6-6.

        Decoding is beam search with length_penalty, no_repeat_ngram_size and
        early_stopping fixed; the text is never trimmed after generation. A
        generation that used all max_length tokens did not finish on its own
        end-of-sequence token (the model config forces one at the limit), so
        it is reported as truncated.

        Args:
            text: the source text.
            num_beams: beam search width.
            min_length: minimum output length in tokens.
            max_length: maximum output length in tokens.

        Returns:
            tuple[str, int, bool]: summary text, input token count after
            truncation, and whether generation stopped on max_length.
        """
        import torch

        inputs = self._tokenizer(
            text,
            return_tensors="pt",
            max_length=self._max_input_tokens,
            truncation=True,
        )
        input_tokens = int(inputs["input_ids"].shape[1])
        with torch.inference_mode():
            outputs = self._model.generate(
                **inputs,
                num_beams=num_beams,
                min_length=min_length,
                max_length=max_length,
                length_penalty=LENGTH_PENALTY,
                no_repeat_ngram_size=NO_REPEAT_NGRAM_SIZE,
                early_stopping=True,
            )
        generated = outputs[0]
        used = int((generated != self._tokenizer.pad_token_id).sum())
        summary = self._tokenizer.decode(generated, skip_special_tokens=True).strip()
        return summary, input_tokens, used >= max_length


def build_embedder(settings: Settings) -> Embedder:
    """Construct the embedder selected by settings.backend.

    Args:
        settings: service settings.

    Returns:
        Embedder: a HashEmbedder for the stub backend, else a TorchEmbedder.
    """
    if settings.backend == "stub":
        return HashEmbedder()
    return TorchEmbedder(settings.embed_model, settings.embed_model_revision)


def build_summarizer(settings: Settings) -> Summarizer:
    """Construct the summarizer selected by settings.backend.

    Args:
        settings: service settings.

    Returns:
        Summarizer: a StubSummarizer for the stub backend, else a TorchSummarizer.
    """
    if settings.backend == "stub":
        return StubSummarizer()
    return TorchSummarizer(
        settings.summarize_model,
        settings.summarize_model_revision,
        settings.max_input_tokens,
    )
