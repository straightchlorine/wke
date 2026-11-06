"""Which section owns a chunk, and which sections enclose another."""

from __future__ import annotations

from wke.core.models import Dossier, Section


def section_of(dossier: Dossier) -> dict[str, str]:
    """Map chunk id -> owning section id.

    Args:
        dossier: The dossier to inspect.

    Returns:
        A dict from chunk id to the id of the section listing it.
    """
    owner: dict[str, str] = {}
    for section in dossier.sections:
        for chunk_id in section.chunk_ids:
            owner.setdefault(chunk_id, section.id)
    return owner


def chunk_kind(chunk_id: str) -> str:
    """Tell the kind of a chunk from its id alone.

    Args:
        chunk_id: "{rev}:{section}:{n}" for prose, ":facts" for the key
            facts, ":table{n}" for a table, ":list{n}" for a list.

    Returns:
        str: "facts", "table", "list" or "prose".
    """
    tail = chunk_id.rsplit(":", 1)[-1]
    if tail == "facts":
        return "facts"
    for kind in ("table", "list"):
        if tail.startswith(kind):
            return kind
    return "prose"


def ancestors(sections: list[Section]) -> dict[str, list[str]]:
    """Map each section id to the ids of the sections whose heading encloses it."""
    found: dict[str, list[str]] = {section.id: [] for section in sections}
    for index, section in enumerate(sections):
        path = section.heading_path
        depth = len(path)
        if not depth:
            continue
        for later in sections[index + 1 :]:
            if later.heading_path[:depth] != path or len(later.heading_path) <= depth:
                break
            found[later.id].append(section.id)
    return found
