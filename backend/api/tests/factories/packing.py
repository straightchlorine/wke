"""Chunks and sections of an exact token size, for tests of the packer."""

from __future__ import annotations

from wke.core.models import Chunk, ChunkKind, MachineSummary, Section


def make_chunk(
    cid: str,
    path: list[str],
    order: int,
    tokens: int,
    relevance: float,
    kind: ChunkKind = "prose",
) -> Chunk:
    """Build a chunk of one sentence whose est_tokens is exactly the given tokens.

    Args:
        cid: chunk id.
        path: heading path of the owning section; empty for the lead.
        order: document order.
        tokens: the est_tokens of the chunk (its text is 4 chars per token).
        relevance: similarity to the lead.
        kind: the chunk kind.

    Returns:
        Chunk: the chunk, cited as "c1".
    """
    return Chunk(
        id=cid,
        kind=kind,
        citation_id="c1",
        heading_path=path,
        order=order,
        text="w" * (tokens * 4 - 1) + ".",
        est_tokens=tokens,
        relevance=relevance,
    )


def make_section(
    sid: str, path: list[str], ids: list[str], summary: MachineSummary | None = None
) -> Section:
    """Build a section over the given chunk ids, summarised when a summary is given.

    Args:
        sid: section id, also its label.
        path: heading path; empty for the lead.
        ids: ids of the chunks it lists.
        summary: the model summary, or None.

    Returns:
        Section: with summary_state "done" when a summary is given, else "skipped".
    """
    return Section(
        id=sid,
        label=sid,
        label_source="heading",
        chunk_ids=ids,
        heading_path=path,
        summary=summary,
        summary_state="done" if summary else "skipped",
    )
