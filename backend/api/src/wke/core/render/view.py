"""Build the DossierView a client receives for one budget."""

from __future__ import annotations

from wke.core.models import Dossier, DossierLinks, DossierView, Freshness, Section
from wke.core.models.budgets import BudgetTokens
from wke.core.pack import pack
from wke.core.render.defaults import DEFAULT_INCLUDE_SUMMARIES
from wke.core.render.markdown import content_text
from wke.core.text.tokens import est_tokens
from wke.core.text.wikilinks import usable_spans

MAX_FIT_ROUNDS = 6


def _content_tokens(view: DossierView, include_summaries: bool) -> int:
    """Return the estimated tokens of the view's dossier part, tags included."""
    text, _ = content_text(view, include_summaries)
    return est_tokens(text)


def _drop_last_passage(view: DossierView) -> DossierView:
    """Drop the last-packed passage, and the summary of its section if that is left without one.

    Args:
        view: a view holding at least two passages.

    Returns:
        DossierView: the view without the passage packed last.
    """
    dropped = view.budget.included_chunk_ids[-1]
    chunks = [chunk for chunk in view.chunks if chunk.id != dropped]
    kept = {chunk.id for chunk in chunks}
    sections = [
        section.model_copy(update={"summary": None})
        if section.summary is not None
        and dropped in section.chunk_ids
        and not any(cid in kept for cid in section.chunk_ids)
        else section
        for section in view.sections
    ]
    budget = view.budget.model_copy(
        update={
            "included_chunk_ids": view.budget.included_chunk_ids[:-1],
            "shortened_chunk_ids": [c for c in view.budget.shortened_chunk_ids if c != dropped],
            "omitted_chunks": view.budget.omitted_chunks + 1,
            "complete": False,
        }
    )
    return view.model_copy(update={"chunks": chunks, "sections": sections, "budget": budget})


def _trim_to_budget(view: DossierView, include_summaries: bool) -> DossierView:
    """Drop passages from the end of the pack order until the content fits the budget.

    Args:
        view: the view after the fit rounds.
        include_summaries: whether the view was packed with summaries.

    Returns:
        DossierView: a view whose dossier part is within the budget.

    Raises:
        ValueError: If the view has no passage, or the first passage alone
            does not fit the budget.
    """
    if not view.chunks:
        raise ValueError("content cannot fit the budget: no passage was kept")
    while _content_tokens(view, include_summaries) > view.budget.requested:
        if len(view.budget.included_chunk_ids) < 2:
            raise ValueError("content cannot fit the budget")
        view = _drop_last_passage(view)
    return view


def build_view(
    dossier: Dossier,
    budget: BudgetTokens,
    freshness: Freshness,
    links: DossierLinks,
    include_summaries: bool = DEFAULT_INCLUDE_SUMMARIES,
) -> DossierView:
    """Pack a dossier so its content fits a token budget and build its view.

    Packs, renders the dossier part and measures it; while that is over the
    budget the overshoot is held back from the packer and the dossier is
    packed again (at most MAX_FIT_ROUNDS times). Anything still over is
    trimmed from the end of the pack order. The header, the Sources list and
    the licence footer are not part of the measure.

    Args:
        dossier: The stored, immutable dossier.
        budget: One of 2000, 8000, 32000.
        freshness: Freshness computed at read time by the caller.
        links: self/pinned/markdown/wikipedia links for this response.
        include_summaries: Whether to pack section summaries.

    Returns:
        DossierView: A view whose chunks fit the budget and whose used_est_tokens
        is the measured size of the dossier part, never above the budget.

    Raises:
        ValueError: If not even the first passage fits the budget.
    """
    reserve = 0
    view = assemble_view(dossier, budget, freshness, links, include_summaries, reserve)
    for attempt in range(MAX_FIT_ROUNDS):
        overshoot = _content_tokens(view, include_summaries) - budget
        if overshoot <= 0:
            break
        # whole chunks drop out at once, so a small reserve changes nothing;
        # the step doubles each round until something does.
        reserve += overshoot << attempt
        view = assemble_view(dossier, budget, freshness, links, include_summaries, reserve)
    view = _trim_to_budget(view, include_summaries)
    counted = view.budget.model_copy(
        update={"used_est_tokens": _content_tokens(view, include_summaries)}
    )
    return view.model_copy(update={"budget": counted})


def assemble_view(
    dossier: Dossier,
    budget: BudgetTokens,
    freshness: Freshness,
    links: DossierLinks,
    include_summaries: bool,
    reserve: int,
) -> DossierView:
    """Pack a dossier holding back a reserve and build the view.

    Args:
        dossier: The stored, immutable dossier.
        budget: One of 2000, 8000, 32000.
        freshness: Freshness computed at read time by the caller.
        links: self/pinned/markdown/wikipedia links for this response.
        include_summaries: Whether to pack section summaries.
        reserve: Tokens the packer holds back for content Markdown it does not charge.

    Returns:
        DossierView: A view with chunks filtered to the packed budget.
    """
    packed = pack(dossier, budget, include_summaries=include_summaries, reserve=reserve)
    included = set(packed.budget.included_chunk_ids)
    chunks = [
        chunk.model_copy(
            update={
                "text": packed.chunk_texts[chunk.id],
                "links": usable_spans(chunk.links, len(packed.chunk_texts[chunk.id])),
                "formulas": usable_spans(chunk.formulas, len(packed.chunk_texts[chunk.id])),
            }
        )
        for chunk in dossier.chunks
        if chunk.id in included
    ]

    sections: list[Section] = []
    for section in dossier.sections:
        if section.summary is not None and section.id not in packed.included_summary_section_ids:
            sections.append(section.model_copy(update={"summary": None}))
        elif section.summary is not None:
            summary = section.summary.model_copy(update={"citation_id": section.citation_id})
            sections.append(section.model_copy(update={"summary": summary}))
        else:
            sections.append(section)

    return DossierView(
        schema_version=dossier.schema_version,
        id=dossier.id,
        topic=dossier.topic,
        build=dossier.build,
        citations=dossier.citations,
        sections=sections,
        chunks=chunks,
        graph=dossier.graph,
        license_notice=dossier.license_notice,
        freshness=freshness,
        budget=packed.budget,
        links=links,
    )
