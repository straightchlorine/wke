"""Mutable accumulator threaded through the recursive section walk."""

from __future__ import annotations

from wke.core.models import Chunk
from wke.core.parse.models import ParsedSection
from wke.core.parse.tables import TableInfo

MAX_CHUNKS = 400


class ParseState:
    """Mutable accumulator threaded through the recursive section walk."""

    def __init__(self, rev_id: int, citation_id: str) -> None:
        self.rev_id = rev_id
        self.citation_id = citation_id
        self.sections: list[ParsedSection] = []
        self.chunks: list[Chunk] = []
        self.section_order = 0
        self.chunk_order = 0
        self.truncated = False
        self.seen_texts: set[str] = set()
        self.tables: dict[int, TableInfo] = {}
        self.facts_done = False

    def chunk_cap_reached(self) -> bool:
        """Tell whether the article already holds MAX_CHUNKS chunks.

        Returns:
            bool: True when no further chunk may be added.
        """
        return len(self.chunks) >= MAX_CHUNKS
