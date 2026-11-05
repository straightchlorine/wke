"""Collect the prose paragraphs, lists and tables a section owns."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import NamedTuple

from selectolax.lexbor import LexborNode

from wke.core.parse.formulas import display_equation, display_tex
from wke.core.parse.lists import LIST_TAGS, is_content_list
from wke.core.parse.passage import Passage, join_passages
from wke.core.parse.prose import EMPTY, blockquote_text, is_caption, prose_of_paragraph
from wke.core.text.clean import clean_text


class Paragraph(NamedTuple):
    """A paragraph or blockquote the walk found."""

    passage: Passage
    is_caption: bool
    list_intro: Passage


@dataclass(frozen=True)
class DisplayFormula:
    """A display equation the walk passed, as TeX."""

    tex: str


# What the walk found in document order; None marks a dropped block (list,
# table or pre) that separates the text around it.
Entry = Paragraph | DisplayFormula | None


@dataclass
class OwnContent:
    """Lists, tables and code blocks found directly in one section, outside subsections."""

    is_lead: bool = False
    lists: list[LexborNode] = field(default_factory=list[LexborNode])
    tables: list[LexborNode] = field(default_factory=list[LexborNode])
    pre_blocks: int = 0


def collect_own_paragraphs(
    section: LexborNode, is_lead: bool = False
) -> tuple[list[list[Passage]], OwnContent]:
    """Collect prose paragraphs belonging to this section, not its subsections.

    Args:
        section: the `<section>` element.
        is_lead: True for the lead, whose only paragraph is never dropped
            as a caption.

    Returns:
        tuple[list[list[Passage]], OwnContent]: the cleaned paragraphs in
        order, grouped in runs that a
        list, table, code block or display formula separates, and the
        blocks the section's own subtree holds.
    """
    found: list[Entry] = []
    own = OwnContent(is_lead=is_lead)
    collect_paragraphs_recursive(section, found, own, in_list=False)
    keep_single = is_lead and sum(isinstance(entry, Paragraph) for entry in found) == 1
    runs: list[list[Passage]] = [[]]
    for entry in found:
        if entry is None:
            if runs[-1]:
                runs.append([])
        elif isinstance(entry, DisplayFormula):
            # The equation closes the sentence before it; text after it goes on.
            if runs[-1]:
                runs[-1][-1] = join_passages([runs[-1][-1], display_equation(entry.tex)])
        else:
            text = entry.list_intro if keep_single and not entry.passage.text else entry.passage
            if text.text and (keep_single or not entry.is_caption):
                runs[-1].append(text)
    return [run for run in runs if run], own


def collect_paragraphs_recursive(
    node: LexborNode, out: list[Entry], own: OwnContent, in_list: bool
) -> None:
    """Walk the subtree of a section and gather its paragraphs, lists and tables.

    Args:
        node: the element to walk; nested sections are skipped.
        out: receives an entry per paragraph, blockquote and display equation,
            and a None where a dropped block lay.
        own: receives the lists, tables and code blocks found.
        in_list: True below a list, whose nested lists are not recorded.
    """
    for child in node.iter():
        if child.tag == "section" and child.attributes.get("data-mw-section-id") is not None:
            continue
        if child.tag == "table":
            own.tables.append(child)
            out.append(None)
            continue
        if child.tag == "pre":
            own.pre_blocks += 1
            out.append(None)
            continue
        tex = display_tex(child)
        if tex:
            out.append(DisplayFormula(tex))
            continue
        entering_list = child.tag in LIST_TAGS
        if entering_list and not in_list and clean_text(child.text(separator="", strip=False)):
            out.append(None)
            if is_content_list(child):
                own.lists.append(child)
        if child.tag == "p":
            text, intro = prose_of_paragraph(child, keep_open=own.is_lead)
            if text.text or intro.text:
                out.append(Paragraph(text, bool(text.text) and is_caption(text.text, child), intro))
            continue
        if child.tag == "blockquote" and child.css_first("p") is None:
            text = blockquote_text(child)
            if text.text:
                out.append(Paragraph(text, False, EMPTY))
            continue
        collect_paragraphs_recursive(child, out, own, in_list or entering_list)
