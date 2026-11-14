"""Small synthetic dossiers whose passage texts the test writes out."""

from __future__ import annotations

import math

from tests.factories.dossier import make_fixture_dossier
from wke.core.models import Chunk, Dossier, FormulaSpan, LinkSpan, Section


def prose(
    cid: str,
    path: list[str],
    order: int,
    text: str,
    relevance: float = 0.5,
    links: list[LinkSpan] | None = None,
    formulas: list[FormulaSpan] | None = None,
) -> Chunk:
    """Build a prose chunk whose token estimate follows its text."""
    return Chunk(
        id=cid,
        citation_id="c1",
        heading_path=path,
        order=order,
        text=text,
        est_tokens=math.ceil(len(text) / 4),
        relevance=relevance,
        links=links or [],
        formulas=formulas or [],
    )


def section(sid: str, path: list[str], ids: list[str], label: str | None = None) -> Section:
    """Build a section without a summary over the given chunk ids."""
    return Section(
        id=sid,
        label=label or sid,
        label_source="heading",
        chunk_ids=ids,
        heading_path=path,
        summary=None,
        summary_state="skipped",
    )


def dossier_of(sections: list[Section], chunks: list[Chunk]) -> Dossier:
    """Put sections and chunks into the fixture dossier, keeping its seed citation only."""
    base = make_fixture_dossier()
    return base.model_copy(
        update={
            "sections": sections,
            "chunks": chunks,
            "citations": [c for c in base.citations if c.id == "c1"],
        }
    )


def sized(first: str, tokens: int) -> str:
    """Pad a sentence with filler words until it is about the given tokens."""
    filler = " ".join(f"item{n}" for n in range(tokens * 4 // 7 + 1))
    return f"{first} {filler}."[: tokens * 4]


def table_chunk_text(rows: int, total: bool = False) -> str:
    """Build the text of a table chunk: caption, header, separator and numbered rows.

    Args:
        rows: how many data rows.
        total: True to end the table with a "Total" row.

    Returns:
        str: the chunk text, without a count note.
    """
    lines = ["Medal table", "| Rank | Nation | Gold |", "| --- | --- | --- |"]
    lines += [f"| {n} | Nation number {n} | {n * 3} |" for n in range(1, rows + 1)]
    if total:
        lines.append("| Total |  | 999 |")
    return "\n".join(lines)


def list_chunk_text(items: int) -> str:
    """Build the text of a list chunk: numbered items, each with one nested line.

    Args:
        items: how many top-level items.

    Returns:
        str: the chunk text, without a count note.
    """
    out: list[str] = []
    for n in range(1, items + 1):
        out.append(f"- Item number {n}")
        out.append(f"  - Detail of item {n}")
    return "\n".join(out)
