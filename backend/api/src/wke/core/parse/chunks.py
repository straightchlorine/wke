"""Merge and split a section's paragraphs into prose chunks."""

from __future__ import annotations

from wke.core.models import Chunk
from wke.core.parse.models import ParsedSection
from wke.core.parse.passage import Passage, join_passages
from wke.core.parse.state import ParseState
from wke.core.text.tokens import est_tokens

# Largest chunk an introduction and its quote, or a sentence and its
# continuation, may make together; past it they are split as usual.
INTRO_MERGE_MAX_TOKENS = 400

MERGE_THRESHOLD_TOKENS = 40

SPLIT_THRESHOLD_TOKENS = 250


def split_long_paragraph(paragraph: Passage) -> list[Passage]:
    """Split a paragraph over SPLIT_THRESHOLD_TOKENS est-tokens at sentence boundaries.

    A single sentence longer than the cap is kept whole: splitting inside
    a sentence would invent a word boundary that is not there.

    Args:
        paragraph: one cleaned paragraph.

    Returns:
        list[Passage]: the paragraph itself, or pieces of at most
        SPLIT_THRESHOLD_TOKENS.
    """
    if est_tokens(paragraph.text) <= SPLIT_THRESHOLD_TOKENS:
        return [paragraph]

    pieces: list[Passage] = []
    buffer: list[Passage] = []
    for sentence in paragraph.sentences():
        candidate = join_passages([*buffer, sentence])
        if buffer and est_tokens(candidate.text) > SPLIT_THRESHOLD_TOKENS:
            pieces.append(join_passages(buffer))
            buffer = [sentence]
        else:
            buffer.append(sentence)
    if buffer:
        pieces.append(join_passages(buffer))
    return pieces


def trim_fragment_tail(passage: Passage) -> Passage:
    """Cut a passage back to its last sentence end.

    Args:
        passage: a chunk's text; may end with an introduction such as "wrote:".

    Returns:
        Passage: the text without trailing sentences that do not end at a
        sentence end; empty when none does.
    """
    sentences = passage.sentences()
    while sentences and not sentences[-1].ends_sentence():
        sentences.pop()
    return join_passages(sentences)


def section_pieces(paragraphs: list[Passage], has_heading: bool) -> list[Passage]:
    """Split long paragraphs and drop a fragment left at the end of a run.

    Args:
        paragraphs: the cleaned paragraphs of one run.
        has_heading: False for the lead, whose last piece is kept as it is.

    Returns:
        list[Passage]: pieces of at most SPLIT_THRESHOLD_TOKENS (a single
        longer sentence stays whole); for a headed section the trailing
        pieces without a sentence end are removed.
    """
    pieces: list[Passage] = []
    for paragraph in paragraphs:
        pieces.extend(split_long_paragraph(paragraph))
    if has_heading:
        # A passage ends at a sentence end: an unpunctuated quote or caption
        # left at the end of the section is not kept.
        while pieces and not pieces[-1].ends_sentence():
            pieces.pop()
    return pieces


class ChunkWriter:
    """Merge the pieces of one section into chunks, honouring the chunk cap."""

    def __init__(
        self,
        section_id: str,
        heading_path: list[str],
        state: ParseState,
        parsed_section: ParsedSection,
    ) -> None:
        """Start a writer for one section.

        Args:
            section_id: the section's id, for the chunk ids.
            heading_path: heading path every chunk carries; empty for the lead.
            state: parse accumulator, extended with the new chunks.
            parsed_section: the section that gets the chunk ids.
        """
        self.section_id = section_id
        self.heading_path = heading_path
        self.state = state
        self.parsed_section = parsed_section
        self.index = 0

    def write_run(self, pieces: list[Passage]) -> None:
        """Merge the pieces of one run into chunks; a chunk never crosses a run.

        Args:
            pieces: the pieces of the run in order.
        """
        buffer: Passage | None = None
        last: Chunk | None = None
        for piece in pieces:
            if self.state.truncated:
                return

            if buffer is None:
                buffer = piece
                continue

            merged = join_passages([buffer, piece])

            # An introduction stays with what it introduces, and a sentence
            # with its continuation ("where c is ..." after an equation).
            joined = buffer.ends_intro() or piece.starts_mid_sentence()
            if joined and est_tokens(merged.text) <= INTRO_MERGE_MAX_TOKENS:
                buffer = merged
            elif (
                est_tokens(buffer.text) < MERGE_THRESHOLD_TOKENS
                and est_tokens(merged.text) <= SPLIT_THRESHOLD_TOKENS
            ):
                buffer = merged
            else:
                last = self._flush(buffer) or last
                buffer = piece

        if buffer is None:
            return
        if last is not None and est_tokens(buffer.text) < MERGE_THRESHOLD_TOKENS:
            if self._append_to(last, buffer):
                return
        self._flush(buffer)

    def _append_to(self, last: Chunk, tail: Passage) -> bool:
        """Join a short tail onto the chunk before it when the result stays small.

        Args:
            last: the chunk written just before the tail.
            tail: the short remainder of the run.

        Returns:
            bool: True when the tail was absorbed.
        """
        joined = join_passages([Passage(last.text, tuple(last.links), tuple(last.formulas)), tail])
        if est_tokens(joined.text) > SPLIT_THRESHOLD_TOKENS or joined.text in self.state.seen_texts:
            return False

        self.state.seen_texts.discard(last.text)
        self.state.seen_texts.add(joined.text)

        last.text = joined.text
        last.links = list(joined.links)
        last.formulas = list(joined.formulas)
        last.est_tokens = est_tokens(joined.text)

        return True

    def _flush(self, buffer: Passage) -> Chunk | None:
        """Turn the buffered passage into a chunk unless it is empty, seen or over the cap.

        Args:
            buffer: the merged passage.

        Returns:
            Chunk | None: the new chunk, None when nothing was added.
        """
        passage = trim_fragment_tail(buffer) if self.heading_path else buffer
        state = self.state

        if not passage.text or passage.text in state.seen_texts:
            return None
        if state.chunk_cap_reached():
            state.truncated = True
            return None

        state.seen_texts.add(passage.text)
        chunk = Chunk(
            id=f"{state.rev_id}:{self.section_id}:{self.index}",
            citation_id=state.citation_id,
            heading_path=self.heading_path,
            order=state.chunk_order,
            text=passage.text,
            est_tokens=est_tokens(passage.text),
            relevance=0.0,
            links=list(passage.links),
            formulas=list(passage.formulas),
        )
        state.chunks.append(chunk)

        self.parsed_section.chunk_ids.append(chunk.id)
        state.chunk_order += 1
        self.index += 1

        return chunk


def emit_chunks(
    runs: list[list[Passage]],
    section_id: str,
    heading_path: list[str],
    state: ParseState,
    parsed_section: ParsedSection,
) -> None:
    """Merge and split a section's paragraphs into Chunks, honouring the chunk cap.

    Args:
        runs: the cleaned paragraphs of the section, grouped between dropped blocks.
        section_id: the section's id, for the chunk ids.
        heading_path: heading path every chunk carries; empty for the lead.
        state: parse accumulator, extended with the new chunks.
        parsed_section: the section that gets the chunk ids.
    """
    if state.truncated:
        return
    writer = ChunkWriter(section_id, heading_path, state, parsed_section)
    for run in runs:
        writer.write_run(section_pieces(run, bool(heading_path)))
