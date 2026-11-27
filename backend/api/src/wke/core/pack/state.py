"""State of a pack run and the budget accounting shared by every placement phase."""

from __future__ import annotations

from dataclasses import dataclass, field

from wke.core.models import Chunk, Dossier, Section
from wke.core.pack.costs import SECTION_HEADING_OVERHEAD_TOKENS, TAG_TOKENS
from wke.core.pack.importance import ranked_sections
from wke.core.pack.owners import ancestors, section_of

# Room reported for a passage the pack may not show, so that nothing fits it.
NO_ROOM = -(10**9)


@dataclass
class PackState:
    """What a pack run has included so far; handed on to the next budget."""

    used: int
    included: list[str] = field(default_factory=list[str])
    texts: dict[str, str] = field(default_factory=dict[str, str])
    summaries: set[str] = field(default_factory=set[str])
    charged: set[str] = field(default_factory=set[str])
    shortened: list[str] = field(default_factory=list[str])
    openers: set[str] = field(default_factory=set[str])


class Packer:
    """One coverage-first pass over a dossier at one budget.

    The placement phases (place_lead, place_openers and the rest) are
    functions in their own modules; this class holds the lookups they share
    and charges the budget.

    A repack of a view sets two limits. allowed_prose, when not None, names the
    only passages that may be placed. held_lists maps a list's chunk id to the text
    it is placed with, and these lists are neither extended nor cut.
    """

    def __init__(
        self,
        dossier: Dossier,
        budget: int,
        state: PackState,
        include_summaries: bool,
        reserve: int = 0,
        allowed_prose: frozenset[str] | None = None,
        held_lists: dict[str, str] | None = None,
    ):
        self.dossier = dossier
        self.budget = budget
        self.reserve = reserve
        self.state = state
        self.include_summaries = include_summaries
        self.allowed_prose = allowed_prose
        self.held_lists = held_lists or {}
        self.chunk_by_id = {c.id: c for c in dossier.chunks}
        self.owner = section_of(dossier)
        self.section_by_id = {s.id: s for s in dossier.sections}
        self.ancestors = ancestors(dossier.sections)
        self.ranked = ranked_sections(dossier.sections, dossier.chunks)
        self.included = set(state.included)

    @property
    def remaining(self) -> int:
        """Tokens of the budget not yet charged."""
        return self.budget - self.state.used

    def heading_cost(self, section_id: str) -> int:
        """Return what the first item of a section adds beyond its own text.

        Args:
            section_id: the section the item belongs to.

        Returns:
            int: the headings of the section and its ancestors not yet paid for.
        """
        needed = [section_id, *self.ancestors.get(section_id, [])]
        return SECTION_HEADING_OVERHEAD_TOKENS * sum(
            1 for sid in needed if sid not in self.state.charged
        )

    def charge(self, section_id: str, tokens: int) -> None:
        """Pay for an item and mark its headings as paid.

        Args:
            section_id: the section the item belongs to.
            tokens: the cost of the item itself.
        """
        self.state.used += self.heading_cost(section_id) + tokens
        self.state.charged.update((section_id, *self.ancestors.get(section_id, [])))

    def add_chunk(self, chunk: Chunk, text: str | None = None, tokens: int | None = None) -> None:
        """Include a chunk, whole or as the given shortened text.

        Args:
            chunk: the chunk to include.
            text: the text to render; the chunk text when None.
            tokens: the cost of that text; the chunk's est_tokens when None.
        """
        section_id = self.owner.get(chunk.id, "")
        text = chunk.text if text is None else text
        tokens = chunk.est_tokens if tokens is None else tokens
        self.charge(section_id, tokens + TAG_TOKENS)
        self.state.included.append(chunk.id)
        self.state.texts[chunk.id] = text
        self.included.add(chunk.id)

    def chunk_room(self, chunk: Chunk) -> int:
        """Return the tokens left for the chunk's own text once its frame is paid.

        A passage outside allowed_prose has no room at all, whatever the budget holds.
        """
        if (
            self.allowed_prose is not None
            and chunk.kind == "prose"
            and chunk.id not in self.allowed_prose
        ):
            return NO_ROOM
        frame = TAG_TOKENS + self.heading_cost(self.owner.get(chunk.id, ""))
        return self.remaining - frame

    def fits_chunk(self, chunk: Chunk) -> bool:
        """Tell whether the whole chunk fits the room left."""
        return chunk.est_tokens <= self.chunk_room(chunk)

    def has_chunk(self, section: Section) -> bool:
        """Tell whether any chunk of the section is already included."""
        return any(cid in self.included for cid in section.chunk_ids)

    def prose_of(self, section: Section) -> list[Chunk]:
        """Return the prose chunks of a section in document order."""
        return [
            self.chunk_by_id[cid]
            for cid in section.chunk_ids
            if cid in self.chunk_by_id and self.chunk_by_id[cid].kind == "prose"
        ]
