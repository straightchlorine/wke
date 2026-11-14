"""Placement of the lead passages."""

from __future__ import annotations

from wke.core.models import Chunk
from wke.core.pack.state import Packer
from wke.core.pack.truncate import truncate_lead
from wke.core.text.tokens import est_tokens

# Share of a step's budget the lead may take.
# At 2000 on the 30 reading topics, 0.40 beats 0.35:
# - one more topic answers every key question (27 to 28 of 30),
# - one more important section is represented (102 to 103 of 120),
# - it reads better: continuity 0.402 to 0.417, longest run of consecutive
#   paragraphs 3.50 to 3.70,
# - detail recall is unchanged.
# 0.50 costs coverage (100 of 120). The lead is contiguous prose, so this is
# the one setting that buys coverage and readability together.
LEAD_SHARE = 0.40


def cut_to_room(chunk: Chunk, room: int) -> str:
    """Cut a passage to whole sentences whose text fits the room.

    Args:
        chunk: the passage to cut.
        room: tokens available for it.

    Returns:
        str: the first sentences of the passage, at least the first one.
    """
    return truncate_lead(chunk.text, room)


def place_lead(packer: Packer) -> None:
    """Include the lead passages, the first one always.

    Restores lead text cut at a lower budget when the room now allows it.
    Further lead passages are added up to LEAD_SHARE of the budget.

    Args:
        packer: the pass to place into.
    """
    state = packer.state
    leads = sorted(
        (c for c in packer.dossier.chunks if not c.heading_path and c.kind == "prose"),
        key=lambda c: c.order,
    )
    cap = LEAD_SHARE * packer.budget
    for chunk_id in list(state.shortened):
        chunk = packer.chunk_by_id[chunk_id]
        if chunk.kind != "prose":
            continue
        extra = chunk.est_tokens - est_tokens(state.texts[chunk_id])
        if extra <= packer.remaining:
            state.texts[chunk_id] = chunk.text
            state.used += extra
            state.shortened.remove(chunk_id)

    lead_tokens = sum(c.est_tokens for c in leads if c.id in packer.included)
    for index, chunk in enumerate(leads):
        if chunk.id in packer.included:
            continue
        if index == 0:
            room = packer.chunk_room(chunk) + packer.reserve
            if chunk.est_tokens <= room:
                packer.add_chunk(chunk)
            else:
                text = cut_to_room(chunk, room)
                packer.add_chunk(chunk, text, est_tokens(text))
                state.shortened.append(chunk.id)
            lead_tokens += chunk.est_tokens
            continue
        if lead_tokens + chunk.est_tokens > cap or not packer.fits_chunk(chunk):
            break
        packer.add_chunk(chunk)
        lead_tokens += chunk.est_tokens
