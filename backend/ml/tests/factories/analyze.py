"""Builders for /v1/analyze request bodies."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from wke_ml.analyze import AnalyzeRequest, ChunkIn


def make_analyze_request(
    texts: Sequence[str], lead: str = "An article about several unrelated topics.", **fields: Any
) -> AnalyzeRequest:
    """Build an AnalyzeRequest with chunk ids c0, c1, ...

    Args:
        texts: chunk texts, in order.
        lead: lead paragraph text.
        **fields: extra AnalyzeRequest fields (related_leads, page_id, ...).

    Returns:
        AnalyzeRequest: the request.
    """
    chunks = [ChunkIn(id=f"c{i}", text=text) for i, text in enumerate(texts)]
    return AnalyzeRequest(lead=lead, chunks=chunks, **fields)
