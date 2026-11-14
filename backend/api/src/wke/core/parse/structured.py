"""Turn the infobox, wikitables and lists of a section into chunks."""

from __future__ import annotations

from wke.core.formats.facts import facts_text
from wke.core.formats.list import list_text
from wke.core.formats.table import table_text
from wke.core.models import Chunk, ChunkKind
from wke.core.parse.lists import read_list
from wke.core.parse.models import ParsedSection
from wke.core.parse.paragraphs import OwnContent
from wke.core.parse.state import ParseState
from wke.core.text.tokens import est_tokens

TABLE_PROSE_FLOOR_TOKENS = 40
FACTS_SUFFIX = "facts"


def add_structured_chunk(
    state: ParseState,
    parsed_section: ParsedSection,
    heading_path: list[str],
    kind: ChunkKind,
    chunk_id: str,
    text: str,
    listed_in: ParsedSection | None = None,
) -> bool:
    """Append a facts, table or list chunk unless the chunk cap is reached.

    Args:
        state: parse accumulator, extended with the new chunk.
        parsed_section: the section that owns the chunk.
        heading_path: heading path the chunk carries.
        kind: "facts", "table" or "list".
        chunk_id: id of the new chunk.
        text: the chunk text.
        listed_in: the section that lists the chunk when it is not the owner
            (the lead, for the infobox facts).

    Returns:
        bool: False when the chunk cap was reached and nothing was added;
        the article is then marked truncated.
    """
    if state.chunk_cap_reached():
        state.truncated = True
        return False
    chunk = Chunk(
        id=chunk_id,
        kind=kind,
        citation_id=state.citation_id,
        heading_path=heading_path,
        order=state.chunk_order,
        text=text,
        est_tokens=est_tokens(text),
        relevance=0.0,
    )
    home = listed_in or parsed_section
    if home is parsed_section:
        state.chunks.append(chunk)
    else:
        # The lead's chunks open the article, so the key facts go right after them.
        state.chunks.insert(len(home.chunk_ids), chunk)
        for position, placed in enumerate(state.chunks):
            placed.order = position
    home.chunk_ids.append(chunk.id)
    state.chunk_order += 1
    return True


def emit_tables(
    own: OwnContent,
    heading: str,
    section_id: str,
    heading_path: list[str],
    state: ParseState,
    parsed_section: ParsedSection,
) -> int:
    """Turn a section's infobox and wikitables into facts and table chunks.

    Args:
        own: lists and tables found directly in the section.
        heading: the section's own heading, "" for the lead.
        section_id: the section's id, for the chunk ids.
        heading_path: heading path every chunk of the section carries.
        state: parse accumulator, extended with the new chunks.
        parsed_section: the section that gets the chunk ids.

    Returns:
        int: how many content tables were left out.
    """
    dropped = 0
    table_index = 0
    for node in own.tables:
        info = state.tables.get(node.mem_id)
        if info is None:
            continue
        if info.infobox is not None:
            if not info.infobox:
                continue
            if not state.facts_done:
                state.facts_done = True
                facts_id = f"{state.rev_id}:{section_id}:{FACTS_SUFFIX}"
                lead = state.sections[0]
                listed_in = lead if not lead.heading else None
                if add_structured_chunk(
                    state,
                    parsed_section,
                    heading_path,
                    "facts",
                    facts_id,
                    facts_text(info.infobox),
                    listed_in,
                ):
                    continue
            dropped += 1
            continue
        table = info.wikitable
        if table is not None:
            text = table_text(table.caption or heading or "Table", table.header, table.rows)
            chunk_id = f"{state.rev_id}:{section_id}:table{table_index}"
            if add_structured_chunk(state, parsed_section, heading_path, "table", chunk_id, text):
                table_index += 1
                continue
        dropped += 1
    return dropped


def emit_lists(
    own: OwnContent,
    prose_tokens: int,
    section_id: str,
    heading_path: list[str],
    state: ParseState,
    parsed_section: ParsedSection,
) -> int:
    """Turn a section's outermost lists into list chunks when it has little prose.

    Args:
        own: lists and tables found directly in the section.
        prose_tokens: est-tokens of the section's prose paragraphs.
        section_id: the section's id, for the chunk ids.
        heading_path: heading path every chunk of the section carries.
        state: parse accumulator, extended with the new chunks.
        parsed_section: the section that gets the chunk ids.

    Returns:
        int: how many lists were left out.
    """
    dropped = 0
    list_index = 0
    for node in own.lists:
        if prose_tokens < TABLE_PROSE_FLOOR_TOKENS:
            lines = read_list(node)
            chunk_id = f"{state.rev_id}:{section_id}:list{list_index}"
            if lines and add_structured_chunk(
                state, parsed_section, heading_path, "list", chunk_id, list_text(lines)
            ):
                list_index += 1
                continue
        dropped += 1
    return dropped


def emit_structured(
    own: OwnContent,
    heading: str,
    prose_tokens: int,
    section_id: str,
    heading_path: list[str],
    state: ParseState,
    parsed_section: ParsedSection,
) -> None:
    """Turn a section's infobox, wikitables and lists into chunks and count what is left out.

    The article's first infobox, wherever it sits, becomes one "facts" chunk.
    The chunk is listed in the lead section (so it renders right after the
    lead) but keeps the heading path of the section that holds the infobox,
    and the citation of that section. A wikitable with a header row becomes
    a "table" chunk. The outermost lists of a section with little prose
    become "list" chunks, one "- item" line per item. Counted as left out: a
    second infobox, any other content table (a wikitable that is not read, a
    table without the wikitable class), a table or list past the chunk cap,
    every list of a section with prose and every `pre` code block. Navigation
    boxes and metadata tables are not counted.

    Args:
        own: lists and tables found directly in the section.
        heading: the section's own heading, "" for the lead.
        prose_tokens: est-tokens of the section's prose paragraphs.
        section_id: the section's id, for the chunk ids.
        heading_path: heading path every chunk of the section carries.
        state: parse accumulator, extended with the new chunks.
        parsed_section: the section; gets the chunk ids and the drop counts.
    """
    dropped_tables = emit_tables(own, heading, section_id, heading_path, state, parsed_section)
    # A code block is never emitted, so it is counted with the lists left out.
    dropped_lists = (
        emit_lists(own, prose_tokens, section_id, heading_path, state, parsed_section)
        + own.pre_blocks
    )
    parsed_section.dropped_lists = dropped_lists
    parsed_section.dropped_tables = dropped_tables
    parsed_section.dropped_non_prose = bool(dropped_lists or dropped_tables)
