"""Parse Parsoid revision HTML into sections and chunks."""

from __future__ import annotations

from wke.core.parse.article import parse_html
from wke.core.parse.models import ParsedArticle, ParsedSection

__all__ = ["ParsedArticle", "ParsedSection", "parse_html"]
