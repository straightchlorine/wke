"""Coverage-first packing of a Dossier's chunks and summaries to a token budget."""

from wke.core.pack.importance import ranked_sections, section_importance
from wke.core.pack.layout import SectionLayout, section_layout
from wke.core.pack.owners import chunk_kind
from wke.core.pack.result import PackedDossier
from wke.core.pack.run import pack

__all__ = [
    "PackedDossier",
    "SectionLayout",
    "chunk_kind",
    "pack",
    "ranked_sections",
    "section_importance",
    "section_layout",
]
