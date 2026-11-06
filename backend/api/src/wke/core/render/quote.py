"""Quote a chunk as Markdown blockquote lines."""

from __future__ import annotations

from wke.core.models import Chunk
from wke.core.render.escape import escape_inline_markup, neutralise
from wke.core.render.inline import inline_markup
from wke.core.render.labels import FACTS_LABEL


def quote_list_line(line: str) -> str:
    """Quote one line of a list chunk, keeping its bullet and nesting.

    Args:
        line: "- item", an indented "  - item" or the "(N items; M shown)" note.

    Returns:
        str: the line as a quoted bullet, its text neutralised like any
        other quoted text; the note is quoted as plain text.
    """
    body = line.lstrip(" ")
    if not body.startswith("- "):
        return f"> {neutralise(escape_inline_markup(line))}"
    indent = line[: len(line) - len(body)]
    return f"> {indent}- {neutralise(escape_inline_markup(body[2:]))}"


def quote(chunk: Chunk, text: str, origin: str = "") -> list[str]:
    """Quote one chunk's text, line by line, so it cannot forge structure.

    Args:
        chunk: the chunk being rendered.
        text: its (possibly shortened) text.
        origin: scheme and host of the wiki; the passage's links are
            written as Markdown links when given. Formulas are code spans.

    Returns:
        list[str]: Markdown lines. Prose is a blockquote; key facts are a
        quoted bullet list under a label; a table is a quoted caption line
        and a pipe table; a list is its "- item" lines, quoted.
    """
    if chunk.kind == "prose":
        safe = neutralise(inline_markup(text, chunk.links, chunk.formulas, origin))
    else:
        safe = neutralise(escape_inline_markup(text))
    lines = safe.splitlines() or [""]
    if chunk.kind == "facts":
        return [f"**{FACTS_LABEL}**", "", *[f"> - {line}" for line in lines]]
    if chunk.kind == "table":
        return [f"> {lines[0]}", ">", *[f"> {line}" for line in lines[1:]]]
    if chunk.kind == "list":
        return [quote_list_line(line) for line in text.splitlines()]
    return [f"> {line}" for line in lines]
