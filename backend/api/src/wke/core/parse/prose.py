"""Turn a paragraph element into clean prose."""

from __future__ import annotations

from selectolax.lexbor import LexborNode

from wke.core.parse.formulas import ends_with_display, mark_formulas
from wke.core.parse.links import mark_links
from wke.core.parse.marks import read_marked
from wke.core.parse.neighbours import (
    dropped_block_follows,
    formula_follows,
    quote_follows,
)
from wke.core.parse.passage import Passage, join_passages
from wke.core.parse.pronunciation import drop_pronunciation_spans, tidy_pronunciation
from wke.core.text.clean import clean_text
from wke.core.text.navigation import NAVIGATION_ANYWHERE, NAVIGATION_SENTENCE
from wke.core.text.sentences import SENTENCE_FINAL

CAPTION_MAX_WORDS = 12

EMPTY = Passage("")


def prose_of_paragraph(node: LexborNode, keep_open: bool = False) -> tuple[Passage, Passage]:
    """Clean one `<p>` and drop navigation sentences and list introductions.

    A last sentence ending in ":" is a list introduction when a dropped
    list or table follows; it goes, the rest of the paragraph stays.

    Args:
        node: the `<p>` element; modified in place (link and formula marks inserted).
        keep_open: True for the lead, whose text is kept without a sentence
            end and whose pronunciation is removed.

    Returns:
        tuple[Passage, Passage]: the cleaned passage (empty text when nothing
        prose is left), and the full-sentence passage when the whole
        paragraph was a list introduction (so a lead's only paragraph can be
        kept), else empty.
    """
    if keep_open:
        drop_pronunciation_spans(node)
    titles = mark_links(node)
    mark_formulas(node)
    marked = clean_text(node.text(separator="", strip=False))
    if keep_open:
        marked = clean_text(tidy_pronunciation(marked))
    sentences = [
        s
        for s in read_marked(marked, titles).sentences()
        if not NAVIGATION_SENTENCE.match(s.text) and not NAVIGATION_ANYWHERE.search(s.text)
    ]
    if not sentences:
        return EMPTY, EMPTY
    if sentences[-1].ends_intro() and dropped_block_follows(node):
        intro = join_passages(sentences)
        sentences.pop()
        if not sentences:
            return EMPTY, intro
    # A trailing piece without a sentence end is a fragment: leave it out,
    # unless a quote or a display equation follows to complete it (the chunk
    # guard drops it if the section ends before) or this is the lead.
    if not (keep_open or quote_follows(node) or formula_follows(node)):
        while sentences and not sentences[-1].ends_sentence():
            sentences.pop()
    return join_passages(sentences), EMPTY


def is_caption(text: str, node: LexborNode) -> bool:
    """Tell a caption or pseudo-heading from a paragraph of prose.

    Args:
        text: cleaned paragraph text.
        node: the `<p>` it came from.

    Returns:
        bool: True for fewer than CAPTION_MAX_WORDS words without a
        sentence-final mark, unless the paragraph introduces a quote that
        follows it (the rule of quote_follows) or a display equation that
        follows it or ends it.
    """
    if len(text.split()) >= CAPTION_MAX_WORDS or SENTENCE_FINAL.search(text):
        return False
    return not (ends_with_display(node) or formula_follows(node) or quote_follows(node))


def blockquote_text(node: LexborNode) -> Passage:
    """Read a blockquote without paragraphs as one line of text.

    Args:
        node: the `<blockquote>` element; modified in place (citation lines removed).

    Returns:
        Passage: the cleaned quote text; it carries no link spans.
    """
    for cite in node.css(".templatequotecite"):
        cite.decompose()
    for br in node.css("br"):
        br.replace_with(" ")
    return Passage(clean_text(node.text(separator="", strip=False)))
