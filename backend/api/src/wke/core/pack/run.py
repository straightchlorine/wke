"""Pack a dossier to a token budget, coverage first."""

from __future__ import annotations

from wke.core.models import Budget, Dossier
from wke.core.models.budgets import BUDGETS, BudgetTokens
from wke.core.pack.costs import (
    SECTION_HEADING_OVERHEAD_TOKENS,
    TAG_TOKENS,
    summary_cost,
)
from wke.core.pack.facts import place_facts
from wke.core.pack.layout import section_layout
from wke.core.pack.lead import place_lead
from wke.core.pack.openers import place_openers
from wke.core.pack.rest import place_rest
from wke.core.pack.result import PackedDossier
from wke.core.pack.state import Packer, PackState
from wke.core.pack.structured import extend_structured, place_structured
from wke.core.pack.summaries import place_summaries
from wke.core.text.tokens import est_tokens

SUMMARY_SHARE = 0.10


def _used_tokens(dossier: Dossier, state: PackState) -> int:
    """Total the estimated tokens of the content a finished run included.

    Args:
        dossier: the packed dossier.
        state: the state after the last budget step.

    Returns:
        int: the section headings, passages with their tags and summaries.
    """
    included = state.included
    layout = section_layout(dossier.sections, included, state.summaries)
    chunk_by_id = {c.id: c for c in dossier.chunks}
    chunk_tokens = sum(
        (est_tokens(state.texts[cid]) if cid in state.shortened else chunk_by_id[cid].est_tokens)
        + TAG_TOKENS
        for cid in included
    )
    summary_tokens = sum(
        summary_cost(section.summary.text)
        for section in dossier.sections
        if section.id in state.summaries and section.summary is not None
    )
    return SECTION_HEADING_OVERHEAD_TOKENS * len(layout.kept_ids) + chunk_tokens + summary_tokens


def pack(
    dossier: Dossier,
    requested: BudgetTokens,
    include_summaries: bool = True,
    reserve: int = 0,
) -> PackedDossier:
    """Pack a dossier's chunks and summaries to a token budget, coverage first.

    Order of inclusion: the lead's passages (up to 40 percent of the budget,
    the first one always), the key facts, one opening passage per section by
    importance (a section whose opening passage does not fit is represented
    by its summary when that fits, else by the passage cut at a sentence end),
    tables and lists of the top-ranked sections (one takes at most 15
    percent of a step's budget; a longer one is cut at a row or item
    boundary), the remaining passages by their own relevance plus the
    importance of the section they belong to, and last any summary that
    still fits beside its section's passages. Only whole chunks and whole
    summaries are ever included, apart from the lead and openers cut at a
    sentence end and a table or list cut at a row or item boundary. A larger
    budget extends the packs of the smaller ones, so a budget never holds
    less than the one below it.

    Args:
        dossier: The stored, immutable dossier to pack.
        requested: One of 2000, 8000, 32000.
        include_summaries: Whether to spend budget on section summaries.
        reserve: Tokens held back at the requested budget for Markdown the
            packer does not charge (quote prefixes, blank lines).
            The first lead passage and the key facts ignore it, so they are
            never lost to it.

    Returns:
        A PackedDossier carrying the Budget, the text for every included
        chunk, and which section summaries fit.
    """
    state = PackState(used=0)
    for step in (b for b in BUDGETS if b <= requested):
        held = reserve if step == requested else 0
        state.used += held
        packer = Packer(dossier, step, state, include_summaries, held)
        place_lead(packer)
        place_facts(packer)
        place_openers(packer)
        place_structured(packer)
        place_summaries(packer, SUMMARY_SHARE * step)
        place_rest(packer)
        extend_structured(packer, leftover=True)
        place_summaries(packer, None)
        state = packer.state

    included = state.included
    omitted = len(dossier.chunks) - len(included)
    budget = Budget(
        requested=requested,
        used_est_tokens=_used_tokens(dossier, state),
        estimator="chars/4",
        included_chunk_ids=included,
        omitted_chunks=omitted,
        complete=omitted == 0,
        shortened_chunk_ids=state.shortened,
    )
    return PackedDossier(
        budget=budget,
        chunk_texts=state.texts,
        included_summary_section_ids=frozenset(state.summaries),
    )
