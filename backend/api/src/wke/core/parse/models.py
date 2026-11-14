"""Result types of parse_html."""

from __future__ import annotations

from wke.core.models import Chunk, WkeModel


class ParsedSection(WkeModel):
    """A kept section of the article and the chunks it owns."""

    id: str
    anchor: str
    heading: str
    heading_path: list[str]
    order: int
    chunk_ids: list[str]
    dropped_non_prose: bool = False
    dropped_lists: int = 0
    dropped_tables: int = 0


class ParsedArticle(WkeModel):
    """The sections and chunks parse_html extracted from one revision."""

    sections: list[ParsedSection]
    chunks: list[Chunk]
    truncated: bool
