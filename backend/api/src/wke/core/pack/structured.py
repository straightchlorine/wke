"""Placement of tables and lists, whole or cut at a row or item boundary."""

from __future__ import annotations

import math

from wke.core.formats.shorten import shorten_list, shorten_table
from wke.core.models import Chunk
from wke.core.pack.importance import section_importance
from wke.core.pack.state import Packer
from wke.core.text.tokens import est_tokens

# Most of a ladder step's budget one table or list may take.
STRUCTURED_SHARE = 0.15
TABLE_SECTION_SHARE = 0.5


def shorten_chunk(chunk: Chunk, allowed: int) -> str | None:
    """Shorten a table or list chunk to a token ceiling.

    Args:
        chunk: a chunk of kind "table" or "list".
        allowed: the most tokens its text may take.

    Returns:
        str | None: the text, or None when too few rows or items fit.
    """
    shorten = shorten_table if chunk.kind == "table" else shorten_list
    return shorten(chunk.text, allowed, est_tokens)


def add_structured(packer: Packer, chunk: Chunk) -> bool:
    """Add a table or list whole, or shortened at a row boundary to what fits.

    Args:
        packer: the pass to place into.
        chunk: the table or list chunk, not yet included.

    Returns:
        bool: True when it was added, whole or shortened.
    """
    allowed = min(packer.chunk_room(chunk), int(STRUCTURED_SHARE * packer.budget))
    text = shorten_chunk(chunk, allowed)
    if text is None:
        return False
    packer.add_chunk(chunk, text, est_tokens(text))
    if text != chunk.text:
        packer.state.shortened.append(chunk.id)
    return True


def extend_structured(packer: Packer, leftover: bool = False) -> None:
    """Give cut tables and lists more rows from the room still free at this step.

    Args:
        packer: the pass to place into.
        leftover: False caps each table at its per-step share (a lower step
            cut it shorter); True lets the most important ones take whatever
            budget the other passes left unused.
    """
    state = packer.state
    cap = int(STRUCTURED_SHARE * packer.budget)
    score = section_importance(packer.dossier.sections, packer.dossier.chunks)
    order = sorted(
        (cid for cid in state.shortened if packer.chunk_by_id[cid].kind != "prose"),
        key=lambda cid: (-score.get(packer.owner.get(cid, ""), 0.0), packer.chunk_by_id[cid].order),
    )
    for chunk_id in order:
        chunk = packer.chunk_by_id[chunk_id]
        held = est_tokens(state.texts[chunk_id])
        room = held + packer.remaining
        text = shorten_chunk(chunk, room if leftover else min(cap, room))
        if text is None or est_tokens(text) <= held:
            continue
        state.texts[chunk_id] = text
        state.used += est_tokens(text) - held
        if text == chunk.text:
            state.shortened.remove(chunk_id)


def place_structured(packer: Packer) -> None:
    """Extend cut tables, then add the tables and lists of the top-ranked sections.

    Args:
        packer: the pass to place into.
    """
    extend_structured(packer)
    top = packer.ranked[: math.ceil(len(packer.ranked) * TABLE_SECTION_SHARE)]
    for section in top:
        for cid in section.chunk_ids:
            chunk = packer.chunk_by_id.get(cid)
            if chunk is not None and chunk.kind in ("table", "list") and cid not in packer.included:
                add_structured(packer, chunk)
