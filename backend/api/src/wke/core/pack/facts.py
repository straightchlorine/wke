"""Placement of the key facts chunk."""

from __future__ import annotations

from wke.core.pack.state import Packer


def place_facts(packer: Packer) -> None:
    """Include the facts chunks that fit, ignoring the reserve.

    Args:
        packer: the pass to place into.
    """
    for chunk in packer.dossier.chunks:
        if (
            chunk.kind == "facts"
            and chunk.id not in packer.included
            and chunk.est_tokens <= packer.chunk_room(chunk) + packer.reserve
        ):
            packer.add_chunk(chunk)
