"""Pack and render a stored dossier, optionally re-parsing its cached HTML."""

from __future__ import annotations

from pydantic import HttpUrl, TypeAdapter

from wke.core import render
from wke.core.citations import seed_pin
from wke.core.models import Citation, Dossier, DossierLinks, DossierView, Freshness
from wke.core.models.budgets import BudgetTokens
from wke.core.parse import parse_html
from wke.core.render.defaults import DEFAULT_INCLUDE_SUMMARIES
from wke.core.summaries.check import check_summary
from wke.jobs.build.cite import cite_sections
from wke.jobs.build.sections import assemble_sections, set_importance
from wke.jobs.build.summarize import summary_input
from wke.jobs.build.summary_gate import withhold

_URL = TypeAdapter(HttpUrl)
# Offline links point nowhere: the invalid TLD is reserved and never resolves.
_PLACEHOLDER_BASE = "https://wke.invalid"


def view_and_markdown(
    dossier: Dossier, budget: BudgetTokens, summaries: bool = DEFAULT_INCLUDE_SUMMARIES
) -> tuple[DossierView, str]:
    """Pack a dossier and render it, as the API does.

    A dossier stored before Section.importance existed gets the score set
    in place, so the view shows what a rebuild would store.

    Args:
        dossier: the stored dossier.
        budget: 2000, 8000 or 32000.
        summaries: whether summaries take part in the packing.

    Returns:
        tuple[DossierView, str]: the packed view and its Markdown.
    """
    if not any(section.importance for section in dossier.sections):
        set_importance(dossier.sections, dossier.chunks)
    pin = seed_pin(dossier)
    freshness = Freshness(
        state="unknown", pinned_rev_id=pin.rev_id, edits_since=None, source="none"
    )
    links = DossierLinks(
        self=_URL.validate_python(f"{_PLACEHOLDER_BASE}/self"),
        pinned=_URL.validate_python(f"{_PLACEHOLDER_BASE}/pinned"),
        markdown=_URL.validate_python(f"{_PLACEHOLDER_BASE}/md"),
        wikipedia=pin.url,
    )
    view = render.build_view(dossier, budget, freshness, links, include_summaries=summaries)
    return view, render.render_markdown(view, summaries)


def reparse(dossier: Dossier, html: str) -> Dossier:
    """Rebuild a stored dossier with the current parser, packer inputs and source check.

    Prose relevance comes from the stored chunk with the same text (or the
    same first 60 characters), else the stored mean; a key-facts or table
    chunk gets the relevance rule of the pipeline. A stored summary stays on
    its section when the section has one that passes the source check against
    the section's new input, else the section is marked withheld.

    Args:
        dossier: the stored dossier of the same revision.
        html: Parsoid HTML of that revision.

    Returns:
        A Dossier shaped like a fresh build of the current pipeline, without
        any model call.
    """
    pin = seed_pin(dossier)
    seed = Citation(id="c1", pin=pin, role="seed", url=pin.permalink)
    related = [c for c in dossier.citations if c.role == "related"]
    parsed = parse_html(html, pin.rev_id, seed.id)

    old_by_text = {c.text: c.relevance for c in dossier.chunks}
    old_by_head = {c.text[:60]: c.relevance for c in dossier.chunks}
    mean = sum(old_by_text.values()) / len(old_by_text) if old_by_text else 0.0

    for chunk in parsed.chunks:
        if chunk.kind == "prose":
            chunk.relevance = old_by_text.get(chunk.text, old_by_head.get(chunk.text[:60], mean))

    section_citations, citation_of = cite_sections(parsed, seed, related)
    old_sections = {s.id: s for s in dossier.sections}
    sections, _ = assemble_sections(
        parsed, parsed.chunks, dossier.topic.title, citation_of, len(parsed.sections)
    )
    for section in sections:
        old = old_sections.get(section.id)
        if old is None or old.summary is None or old.summary_state != "done":
            continue

        input_text, input_ids = summary_input(section, parsed.chunks)
        titles = [c.pin.title for c in related]
        heading = section.heading_path[-1] if section.heading_path else section.label
        reason = check_summary(old.summary.text, input_text, heading, foreign_titles=titles)

        if reason is not None:
            withhold(section, reason)
        else:
            section.summary = old.summary.model_copy(
                update={"input_chunk_ids": input_ids, "citation_id": section.citation_id}
            )
            section.summary_state = "done"
    return dossier.model_copy(
        update={
            "citations": [seed, *related, *section_citations],
            "sections": sections,
            "chunks": parsed.chunks,
        }
    )
