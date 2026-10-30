"""Canned wke-ml response bodies."""

from __future__ import annotations

from datetime import UTC, datetime


def analyze_response_json() -> dict:
    return {
        "model": "all-MiniLM-L6-v2",
        "model_revision": "abc123",
        "relevance": {},
        "cluster_ids": {},
        "representatives": [],
        "edges": [],
        "infer_seconds": 0.1,
    }


def summarize_response_json() -> dict:
    return {
        "kind": "machine_summary",
        "text": "A short machine summary.",
        "model": "sshleifer/distilbart-cnn-6-6",
        "model_revision": "def456",
        "params": {"num_beams": 1, "min_length": 30, "max_length": 96, "input_tokens": 120},
        "input_chunk_ids": ["ml-reported-1"],
        "generated_at": datetime.now(UTC).isoformat(),
        "infer_seconds": 1.2,
    }
