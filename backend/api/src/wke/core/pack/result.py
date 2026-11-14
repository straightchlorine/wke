"""The result of packing a dossier to a token budget."""

from __future__ import annotations

from dataclasses import dataclass, field

from wke.core.models import Budget


@dataclass(frozen=True)
class PackedDossier:
    """Result of packing a Dossier to a token budget.

    Attributes:
        budget: The API-facing Budget model.
        chunk_texts: Chunk id -> text to render, possibly shortened: the
            forced-first lead passage or a section's opening passage at a
            sentence end, a table or list at a row or item boundary.
        included_summary_section_ids: Ids of sections whose summary fit
            within the budget and should be rendered, with or without
            passages of the section beside it.
    """

    budget: Budget
    chunk_texts: dict[str, str] = field(default_factory=dict[str, str])
    included_summary_section_ids: frozenset[str] = field(default_factory=frozenset[str])
