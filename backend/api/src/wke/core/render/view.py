"""Build the DossierView a client receives for one budget."""

from __future__ import annotations

from typing import Any

from wke.core.models import Chunk, Dossier, DossierLinks, DossierView, Freshness, Section
from wke.core.models.budgets import BudgetTokens
from wke.core.pack import pack
from wke.core.render.defaults import DEFAULT_INCLUDE_SUMMARIES
from wke.core.render.markdown import content_text
from wke.core.text.tokens import est_tokens
from wke.core.text.wikilinks import usable_spans

MAX_FIT_ROUNDS = 6
# The only budget at which a view may be repacked to give tables and lists more room.
TABLE_REPACK_BUDGET = 2000
# The most extra passages a repack drops. Each try packs the dossier again, so a dossier of many
# short passages would otherwise make one read slow.
MAX_REPACK_EXTRAS = 12


def _content_tokens(
    view: DossierView,
    include_summaries: bool,
    subsection_headings: bool = True,
    notes: bool = True,
) -> int:
    """Return the estimated tokens of the view's dossier part, tags included."""
    text, _ = content_text(
        view, include_summaries, subsection_headings=subsection_headings, notes=notes
    )
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


def _trim_to_budget(
    view: DossierView,
    include_summaries: bool,
    subsection_headings: bool = True,
    notes: bool = True,
) -> DossierView:
    """Drop passages, last packed first, until the rendered content fits the budget.

    Args:
        view: the view after the repacking rounds of build_view.
        include_summaries: whether the view was packed with summaries.
        subsection_headings: whether the render writes subsection headings.
        notes: whether the per-section lines naming left-out tables and lists count.

    Returns:
        DossierView: a view whose dossier part is within the budget.

    Raises:
        ValueError: If the view has no passage, or the first passage alone
            does not fit the budget.
    """
    if not view.chunks:
        raise ValueError("content cannot fit the budget: no passage was kept")
    while (
        _content_tokens(view, include_summaries, subsection_headings, notes) > view.budget.requested
    ):
        if len(view.budget.included_chunk_ids) < 2:
            raise ValueError("content cannot fit the budget")
        view = _drop_last_passage(view)
    return view


def _fit_view(
    dossier: Dossier,
    budget: BudgetTokens,
    freshness: Freshness,
    links: DossierLinks,
    include_summaries: bool,
    subsection_headings: bool,
    lean: bool,
    allowed_prose: frozenset[str] | None = None,
    held_lists: dict[str, str] | None = None,
) -> tuple[DossierView, int]:
    """Pack a dossier until its dossier part fits the budget, and build its view.

    Args:
        dossier: The stored, immutable dossier.
        budget: One of 2000, 8000, 32000.
        freshness: Freshness computed at read time by the caller.
        links: self/pinned/markdown/wikipedia links for this response.
        include_summaries: Whether to pack section summaries.
        subsection_headings: Whether the render writes subsection headings.
        lean: Whether to leave the key facts and the left-out lines out of the counted part.
        allowed_prose: When given, the only passages the packer may place.
        held_lists: When given, lists the packer carries over as they are.

    Returns:
        tuple[DossierView, int]: the view, and the reserve held back for its last packing.

    Raises:
        ValueError: If not even the first passage fits the budget.
    """

    def pack_view(reserve: int) -> DossierView:
        if allowed_prose is None and held_lists is None:
            return assemble_view(
                dossier, budget, freshness, links, include_summaries, reserve, facts=not lean
            )
        return _assemble(
            dossier,
            budget,
            freshness,
            links,
            include_summaries,
            reserve,
            not lean,
            allowed_prose,
            held_lists,
        )

    reserve = 0
    notes = not lean
    view = pack_view(reserve)
    for attempt in range(MAX_FIT_ROUNDS):
        overshoot = _content_tokens(view, include_summaries, subsection_headings, notes) - budget
        if overshoot <= 0:
            break
        # Packing drops whole chunks, so a reserve smaller than one chunk may change
        # nothing. Doubling the added reserve each round makes sure a chunk drops soon.
        reserve += overshoot << attempt
        view = pack_view(reserve)
    view = _trim_to_budget(view, include_summaries, subsection_headings, notes)
    counted = view.budget.model_copy(
        update={
            "used_est_tokens": _content_tokens(view, include_summaries, subsection_headings, notes)
        }
    )
    return view.model_copy(update={"budget": counted}), reserve


def _structured_units(chunks: list[Chunk], held_lists: dict[str, str]) -> int:
    """Count the table rows and the list items of some chunks, apart from the held lists.

    Args:
        chunks: the chunks of a packed view, or of the whole dossier.
        held_lists: the lists to leave out of the count, by chunk id.

    Returns:
        int: the data rows of every table plus the top-level items of every other list.
    """
    total = 0
    for chunk in chunks:
        lines = chunk.text.split("\n")
        if chunk.kind == "table":
            total += max(0, sum(1 for line in lines if line.startswith("|")) - 2)
        elif chunk.kind == "list" and chunk.id not in held_lists:
            total += sum(1 for line in lines if line.startswith("- "))
    return total


def _repack_for_tables(
    dossier: Dossier,
    baseline: DossierView,
    reserve: int,
    freshness: Freshness,
    links: DossierLinks,
    include_summaries: bool,
    subsection_headings: bool,
    lean: bool,
) -> DossierView:
    """Give tables and lists room by dropping the weakest extra passages, as far as it pays.

    The extra passages are the shown ones that are neither lead passages nor a section's
    opening paragraph. They leave one at a time, lowest score first, the later passage of the
    document first on a tie, and at most MAX_REPACK_EXTRAS of them. After each departure the
    dossier is packed again with only the baseline's other passages allowed and every list the
    baseline shows carried over as shown. The result is the pack with the most table rows plus
    items of lists the baseline does not show, the one with fewest departures on a tie; the
    baseline itself when none gains. The tries stop at the first pack that shows every row and
    item the dossier holds, and none is made when the baseline already shows them all.

    Args:
        dossier: The stored dossier the baseline was packed from.
        baseline: the view packed without the repack.
        reserve: the reserve the baseline's last packing was made with.
        freshness: Freshness computed at read time by the caller.
        links: self/pinned/markdown/wikipedia links for this response.
        include_summaries: Whether to pack section summaries.
        subsection_headings: Whether the render writes subsection headings.
        lean: Whether to leave the key facts and the left-out lines out of the counted part.

    Returns:
        DossierView: the chosen view, with its own counts.
    """
    by_id = {chunk.id: chunk for chunk in dossier.chunks}
    text_of = {c.id: c.text for c in baseline.chunks}
    held = {
        cid: text_of[cid] for cid in baseline.budget.included_chunk_ids if by_id[cid].kind == "list"
    }
    best, best_gain = baseline, _structured_units(baseline.chunks, held)
    most = _structured_units(dossier.chunks, held)
    if best_gain >= most:
        return baseline
    # The pack that built the view does not report its openers, so it is run once more.
    openers = pack(
        dossier,
        baseline.budget.requested,
        include_summaries=include_summaries,
        reserve=reserve,
        facts=not lean,
    ).opener_ids
    shown = [c.id for c in baseline.chunks if c.kind == "prose"]
    extras = sorted(
        (by_id[cid] for cid in shown if by_id[cid].heading_path and cid not in openers),
        key=lambda c: (c.relevance, -c.order),
    )
    for count in range(1, min(len(extras), MAX_REPACK_EXTRAS) + 1):
        allowed = frozenset(shown) - {c.id for c in extras[:count]}
        view, _ = _fit_view(
            dossier,
            baseline.budget.requested,
            freshness,
            links,
            include_summaries,
            subsection_headings,
            lean,
            allowed,
            held,
        )
        gain = _structured_units(view.chunks, held)
        if gain > best_gain:
            best, best_gain = view, gain
        if best_gain >= most:
            break
    return best


def build_view(
    dossier: Dossier,
    budget: BudgetTokens,
    freshness: Freshness,
    links: DossierLinks,
    include_summaries: bool = DEFAULT_INCLUDE_SUMMARIES,
    subsection_headings: bool = True,
    lean: bool = False,
    table_repack: bool = False,
) -> DossierView:
    """Pack a dossier so its content fits a token budget and build its view.

    Packs the dossier, renders its dossier part and measures it. While the
    measure is over the budget, a growing reserve is held back from the packer
    and the dossier is packed again (at most MAX_FIT_ROUNDS times). Anything
    still over is trimmed passage by passage, last packed first. The header,
    the Sources list and the licence footer are not measured. When lean, the key
    facts and the per-section lines naming left-out tables and lists are neither
    packed nor measured. At TABLE_REPACK_BUDGET with table_repack, the view may be
    replaced by a repack that trades some passages for table rows and list items.

    Args:
        dossier: The stored, immutable dossier.
        budget: One of 2000, 8000, 32000.
        freshness: Freshness computed at read time by the caller.
        links: self/pinned/markdown/wikipedia links for this response.
        include_summaries: Whether to pack section summaries.
        subsection_headings: Whether the render writes subsection headings, which are
            counted in the measure.
        lean: Whether to leave the key facts and the left-out lines out of the
            counted dossier part; the view then holds no key facts chunk.
        table_repack: Whether to repack at TABLE_REPACK_BUDGET for tables and lists.

    Returns:
        DossierView: A view whose chunks fit the budget and whose used_est_tokens
        is the measured size of the dossier part, never above the budget.

    Raises:
        ValueError: If not even the first passage fits the budget.
    """
    view, reserve = _fit_view(
        dossier, budget, freshness, links, include_summaries, subsection_headings, lean
    )
    if table_repack and budget == TABLE_REPACK_BUDGET:
        view = _repack_for_tables(
            dossier, view, reserve, freshness, links, include_summaries, subsection_headings, lean
        )
    return view


def assemble_view(
    dossier: Dossier,
    budget: BudgetTokens,
    freshness: Freshness,
    links: DossierLinks,
    include_summaries: bool,
    reserve: int,
    facts: bool = True,
) -> DossierView:
    """Pack a dossier with a token reserve held back, and build the view.

    Args:
        dossier: The stored, immutable dossier.
        budget: One of 2000, 8000, 32000.
        freshness: Freshness computed at read time by the caller.
        links: self/pinned/markdown/wikipedia links for this response.
        include_summaries: Whether to pack section summaries.
        reserve: Tokens held back for Markdown the packer does not count.
        facts: Whether the key facts are packed; if False the view holds no key facts.

    Returns:
        DossierView: A view with chunks filtered to the packed budget.
    """
    return _assemble(dossier, budget, freshness, links, include_summaries, reserve, facts)


def _assemble(
    dossier: Dossier,
    budget: BudgetTokens,
    freshness: Freshness,
    links: DossierLinks,
    include_summaries: bool,
    reserve: int,
    facts: bool,
    allowed_prose: frozenset[str] | None = None,
    held_lists: dict[str, str] | None = None,
) -> DossierView:
    """Pack a dossier with a token reserve held back, and build the view.

    Args:
        dossier: The stored, immutable dossier.
        budget: One of 2000, 8000, 32000.
        freshness: Freshness computed at read time by the caller.
        links: self/pinned/markdown/wikipedia links for this response.
        include_summaries: Whether to pack section summaries.
        reserve: Tokens held back for Markdown the packer does not count.
        facts: Whether the key facts are packed; if False the view holds no key facts.
        allowed_prose: When given, the only passages the packer may place.
        held_lists: When given, lists the packer carries over as they are.

    Returns:
        DossierView: A view with chunks filtered to the packed budget.
    """
    # The limits go to the packer only when a repack sets them.
    limits: dict[str, Any] = {}
    if allowed_prose is not None:
        limits["allowed_prose"] = allowed_prose
    if held_lists:
        limits["held_lists"] = held_lists
    packed = pack(
        dossier, budget, include_summaries=include_summaries, reserve=reserve, facts=facts, **limits
    )
    facts_ids = set() if facts else {c.id for c in dossier.chunks if c.kind == "facts"}
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
        if facts_ids.intersection(section.chunk_ids):
            ids = [cid for cid in section.chunk_ids if cid not in facts_ids]
            section = section.model_copy(update={"chunk_ids": ids})
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
