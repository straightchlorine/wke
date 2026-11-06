"""Hypothesis property tests of the packer: budget, monotone packs, lead, determinism."""

from __future__ import annotations

from hypothesis import given, settings

from tests.factories.dossier import dossiers
from wke.core import pack
from wke.core.models import Dossier


@given(dossier=dossiers())
@settings(max_examples=60)
def test_used_never_exceeds_requested(dossier: Dossier) -> None:
    for budget in (2000, 8000, 32000):
        packed = pack.pack(dossier, budget)
        assert packed.budget.used_est_tokens <= budget


@given(dossier=dossiers())
@settings(max_examples=60)
def test_budgets_are_monotone_subsets(dossier: Dossier) -> None:
    small = set(pack.pack(dossier, 2000).budget.included_chunk_ids)
    medium = set(pack.pack(dossier, 8000).budget.included_chunk_ids)
    large = set(pack.pack(dossier, 32000).budget.included_chunk_ids)
    assert small <= medium <= large


@given(dossier=dossiers())
@settings(max_examples=60)
def test_lead_chunk_always_included(dossier: Dossier) -> None:
    lead_ids = {c.id for c in dossier.chunks if not c.heading_path}
    if not lead_ids:
        return
    for budget in (2000, 8000, 32000):
        packed = pack.pack(dossier, budget)
        assert lead_ids & set(packed.budget.included_chunk_ids)


@given(dossier=dossiers())
@settings(max_examples=60)
def test_deterministic(dossier: Dossier) -> None:
    first = pack.pack(dossier, 8000)
    second = pack.pack(dossier, 8000)
    assert first.budget.included_chunk_ids == second.budget.included_chunk_ids
    assert first.budget.used_est_tokens == second.budget.used_est_tokens


@given(dossier=dossiers())
@settings(max_examples=60)
def test_omitted_chunks_are_the_ones_not_included_and_complete_means_none(
    dossier: Dossier,
) -> None:
    for budget in (2000, 8000, 32000):
        packed = pack.pack(dossier, budget)
        assert packed.budget.omitted_chunks == len(dossier.chunks) - len(
            packed.budget.included_chunk_ids
        )
        assert packed.budget.complete == (packed.budget.omitted_chunks == 0)
