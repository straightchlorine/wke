"""Escape Wikipedia text so it cannot forge Markdown structure."""

from __future__ import annotations

import re

STRUCTURE_MARKER_RE = re.compile(
    r"^(?P<indent> {0,3})(?P<marker>"
    r"#{1,6}(?=\s|$)"  # ATX heading, e.g. "## Sources"
    r"|[-*_](?: *[-*_]){2,} *$"  # thematic break: ---, ***, ___, - - -
    r"|=+ *$"  # setext H1 underline
    r"|```"  # fenced code block
    r"|~~~"
    r"|>"  # blockquote marker
    r"|[-+*]\s"  # bullet list marker
    r"|\d{1,9}[.)]\s"  # ordered list marker
    r")"
)


INLINE_MARKUP_RE = re.compile(r"[\[\]<>`]")


def escape_inline_markup(text: str) -> str:
    """Backslash-escape characters that could forge inline Markdown structure.

    Args:
        text: raw text about to be embedded in a Markdown document.

    Returns:
        str: text with each '[', ']', '<', '>' and backtick preceded by a
        backslash, so quoted Wikipedia text cannot open a link, image,
        autolink, raw HTML tag or link-reference definition (e.g.
        "[c1]: https://evil"). Other ASCII punctuation is left alone:
        chunk text is always single-line (clean_text), so tables
        and emphasis are not an attack surface, and escaping them would
        only degrade the Markdown for LLM readers.
    """
    return INLINE_MARKUP_RE.sub(lambda m: "\\" + m.group(0), text)


def neutralise(text: str) -> str:
    """Defang lines that could be read as Markdown structure.

    Args:
        text: Raw chunk or summary text about to be quoted verbatim.

    Returns:
        str: text with a backslash inserted right before the first significant
        character of any line that opens a heading, thematic break,
        setext underline, blockquote, list item or fenced code block, so
        the quoted passage cannot forge document structure. ASCII only.
    """
    out_lines: list[str] = []
    for line in text.splitlines():
        match = STRUCTURE_MARKER_RE.match(line)
        if match:
            split = match.start("marker")
            out_lines.append(line[:split] + "\\" + line[split:])
        else:
            out_lines.append(line)
    return "\n".join(out_lines)
