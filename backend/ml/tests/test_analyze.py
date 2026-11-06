"""Unit tests for the /v1/analyze pipeline (wke_ml.analyze)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from tests.factories.analyze import make_analyze_request
from tests.support.fakes import OppositeEmbedder, ScriptedEmbedder
from wke_ml.analyze import (
    AnalyzeRequest,
    AnalyzeResponse,
    RelatedLeadIn,
    analyze,
    pick_representatives,
    select_clusters,
)
from wke_ml.backends import HashEmbedder
from wke_ml.settings import Settings

GROUP_A = [
    "alpha alpha alpha rocket propulsion engineering",
    "alpha alpha rocket fuel engineering systems",
    "alpha rocket propulsion fuel systems design",
    "alpha alpha alpha propulsion rocket design",
    "alpha rocket engineering fuel design systems",
    "alpha alpha propulsion engineering rocket fuel",
]
GROUP_B = [
    "beta beta beta ocean marine biology",
    "beta beta ocean coral marine biology",
    "beta ocean marine coral biology reef",
    "beta beta beta marine coral ocean",
    "beta ocean biology reef marine coral",
    "beta beta marine ocean reef biology",
]
GROUP_C = [
    "gamma gamma gamma medieval castle history",
    "gamma gamma medieval history castle siege",
    "gamma medieval castle siege history stone",
    "gamma gamma gamma castle medieval stone",
    "gamma medieval history stone castle siege",
    "gamma gamma castle history medieval siege",
]


def _node_ids(result: AnalyzeResponse) -> set[int]:
    return {edge.source for edge in result.edges} | {edge.target for edge in result.edges}


def test_analyze_recovers_planted_topic_clusters(
    settings_stub: Settings, embedder: HashEmbedder
) -> None:
    request = make_analyze_request(GROUP_A + GROUP_B + GROUP_C)
    n_chunks = len(request.chunks)

    result = analyze(request, embedder, settings_stub)
    again = analyze(request, embedder, settings_stub)
    assert result.cluster_ids == again.cluster_ids
    assert result.representatives == again.representatives
    k = len(set(result.cluster_ids.values()))

    assert 2 <= k <= n_chunks // settings_stub.kmeans_chunks_per_cluster
    assert len(result.representatives) == k

    group_a_clusters = {result.cluster_ids[f"c{i}"] for i in range(0, 6)}
    group_b_clusters = {result.cluster_ids[f"c{i}"] for i in range(6, 12)}
    group_c_clusters = {result.cluster_ids[f"c{i}"] for i in range(12, 18)}
    assert len(group_a_clusters) == 1
    assert len(group_b_clusters) == 1
    assert len(group_c_clusters) == 1
    assert group_a_clusters != group_b_clusters != group_c_clusters != group_a_clusters
    for cluster_id, chunk_id in enumerate(result.representatives):
        assert result.cluster_ids[chunk_id] == cluster_id


@pytest.mark.parametrize(
    ("request_cap", "settings_cap"),
    [(2, 6), (6, 2)],
    ids=["request_max_clusters", "settings_kmeans_max_k"],
)
def test_analyze_caps_k(
    settings_stub: Settings, embedder: HashEmbedder, request_cap: int, settings_cap: int
) -> None:
    request = make_analyze_request(GROUP_A + GROUP_B + GROUP_C, max_clusters=request_cap)
    settings = settings_stub.model_copy(update={"kmeans_max_k": settings_cap})

    result = analyze(request, embedder, settings)

    assert len(set(result.cluster_ids.values())) == 2
    assert len(result.representatives) == 2


def test_analyze_relevance_ranks_on_topic_chunks_higher_and_stays_in_bounds(
    settings_stub: Settings, embedder: HashEmbedder
) -> None:
    request = make_analyze_request(GROUP_A + GROUP_B, lead="alpha rocket propulsion fuel design")

    result = analyze(request, embedder, settings_stub)

    assert set(result.relevance) == {chunk.id for chunk in request.chunks}
    assert all(0.0 <= score <= 1.0 for score in result.relevance.values())
    mean_a = sum(result.relevance[f"c{i}"] for i in range(6)) / 6
    mean_b = sum(result.relevance[f"c{i}"] for i in range(6, 12)) / 6
    assert mean_a > mean_b


def test_analyze_relevance_clamps_negative_cosine_to_zero(settings_stub: Settings) -> None:
    request = make_analyze_request(["one chunk pointing the opposite way"], lead="a lead vector")

    result = analyze(request, OppositeEmbedder(), settings_stub)

    assert result.relevance["c0"] == 0.0


def test_analyze_falls_back_to_single_cluster_for_few_chunks(
    settings_stub: Settings, embedder: HashEmbedder
) -> None:
    request = make_analyze_request(["only one chunk here", "a second short chunk"])

    result = analyze(request, embedder, settings_stub)

    assert set(result.cluster_ids.values()) == {0}
    assert len(result.representatives) == 1


@pytest.mark.filterwarnings("error::sklearn.exceptions.ConvergenceWarning")
def test_analyze_identical_chunks_form_one_cluster(
    settings_stub: Settings, embedder: HashEmbedder
) -> None:
    request = make_analyze_request(["the very same words"] * 12)

    result = analyze(request, embedder, settings_stub)

    assert set(result.cluster_ids.values()) == {0}
    assert result.representatives == ["c0"]


@pytest.mark.filterwarnings("ignore::sklearn.exceptions.ConvergenceWarning")
def test_select_clusters_picks_fewest_clusters_that_separate_the_data(
    embedder: HashEmbedder,
) -> None:
    vectors = embedder.embed(["alpha alpha alpha"] * 9 + ["omega omega omega"] * 9)

    k, labels, centroids = select_clusters(vectors, max_clusters=6, chunks_per_cluster=6, seed=42)

    assert k == 2
    assert len(set(labels[:9].tolist())) == len(set(labels[9:].tolist())) == 1
    assert labels[0] != labels[-1]
    assert centroids.shape == (2, vectors.shape[1])


@pytest.mark.filterwarnings("error::sklearn.exceptions.ConvergenceWarning")
def test_select_clusters_returns_one_cluster_for_identical_vectors(
    embedder: HashEmbedder,
) -> None:
    vectors = embedder.embed(["the very same words"] * 12)

    k, labels, centroids = select_clusters(vectors, max_clusters=6, chunks_per_cluster=6, seed=42)

    assert (k, labels.tolist()) == (1, [0] * 12)
    assert centroids.shape == (1, vectors.shape[1])


@pytest.mark.parametrize(
    ("silhouettes", "expected_k"),
    [
        pytest.param([0.5, 0.51], 2, id="penalty-beats-small-silhouette-gain"),
        pytest.param([0.5, 0.52], 2, id="tie-keeps-the-smaller-k"),
        pytest.param([0.5, 0.6], 3, id="large-gain-wins"),
    ],
)
def test_select_clusters_scores_silhouette_minus_k_penalty(
    monkeypatch: pytest.MonkeyPatch, silhouettes: list[float], expected_k: int
) -> None:
    scores = iter(silhouettes)

    def fake_silhouette(*_args: object) -> float:
        return next(scores)

    monkeypatch.setattr("wke_ml.analyze.silhouette_score", fake_silhouette)
    vectors = np.eye(12, dtype=np.float32)

    k, _labels, _centroids = select_clusters(vectors, max_clusters=3, chunks_per_cluster=4, seed=42)

    assert k == expected_k


def test_pick_representatives_skips_an_empty_cluster() -> None:
    vectors = np.array([[1.0, 0.0], [0.9, 0.1], [0.0, 1.0]], dtype=np.float32)
    labels = np.array([0, 0, 2], dtype=np.intp)
    centroids = np.array([[1.0, 0.0], [0.5, 0.5], [0.0, 1.0]], dtype=np.float32)

    reps = pick_representatives(["a", "b", "c"], vectors, 3, labels, centroids)

    assert reps == ["a", "c"]


def _filler_and_match_request(related_page_id: int = 999) -> AnalyzeRequest:
    related = [
        RelatedLeadIn(page_id=100 + i, text=f"unrelated filler text number {i}") for i in range(7)
    ]
    related.append(
        RelatedLeadIn(
            page_id=related_page_id, text="alpha alpha alpha rocket propulsion engineering"
        )
    )
    return make_analyze_request(GROUP_A, lead="alpha rocket propulsion", related_leads=related)


def test_analyze_edges_respect_threshold_dedup_and_sort(
    settings_stub: Settings, embedder: HashEmbedder
) -> None:
    result = analyze(_filler_and_match_request(), embedder, settings_stub)

    assert result.edges
    assert all(edge.weight >= settings_stub.edge_similarity_threshold for edge in result.edges)
    weights = [edge.weight for edge in result.edges]
    assert weights == sorted(weights, reverse=True)
    pairs = [frozenset((edge.source, edge.target)) for edge in result.edges]
    assert len(pairs) == len(set(pairs))
    # 999 is the only related lead whose text overlaps the article's
    # vocabulary, so it is the article node's sole edge.
    article_edges = [edge for edge in result.edges if 0 in (edge.source, edge.target)]
    assert [(edge.source, edge.target) for edge in article_edges] == [(0, 999)]
    # The seven filler leads share most of their vocabulary with each
    # other, so related-to-related edges exist too.
    assert any(0 not in (edge.source, edge.target) for edge in result.edges)


@pytest.mark.parametrize("top_n", [0, 1])
def test_analyze_edge_top_n_limits_edges_per_node(
    settings_stub: Settings, embedder: HashEmbedder, top_n: int
) -> None:
    related = [
        RelatedLeadIn(page_id=i + 1, text="alpha alpha alpha rocket propulsion engineering")
        for i in range(5)
    ]
    request = make_analyze_request(GROUP_A, lead="alpha rocket propulsion", related_leads=related)
    settings = settings_stub.model_copy(update={"edge_top_n": top_n})

    result = analyze(request, embedder, settings)

    # Six identical-ish nodes, each keeping its top_n neighbours: at most
    # top_n * nodes edges, and at least one per node when top_n > 0.
    assert len(result.edges) <= top_n * 6
    if top_n == 0:
        assert result.edges == []
    else:
        assert _node_ids(result) == {0, 1, 2, 3, 4, 5}


def test_analyze_edges_honour_max_edges_when_top_n_widened(
    settings_stub: Settings, embedder: HashEmbedder
) -> None:
    related = [
        RelatedLeadIn(page_id=i, text="alpha alpha alpha rocket propulsion engineering fuel")
        for i in range(40)
    ]
    request = make_analyze_request(
        GROUP_A, lead="alpha rocket propulsion", related_leads=related, max_edges=80
    )
    settings = settings_stub.model_copy(update={"edge_top_n": 100})

    result = analyze(request, embedder, settings)

    # With edge_top_n widened, 40 densely-similar related leads produce far
    # more than 20 candidate edges; max_edges is the cap.
    assert len(result.edges) > 20
    assert len(result.edges) <= 80
    capped = analyze(request.model_copy(update={"max_edges": 20}), embedder, settings)
    assert len(capped.edges) == 20


def test_analyze_empty_chunks_without_related_leads_is_empty(
    settings_stub: Settings, embedder: HashEmbedder
) -> None:
    request = make_analyze_request([], lead="rockets and propulsion topic")

    result = analyze(request, embedder, settings_stub)

    assert (result.relevance, result.cluster_ids, result.representatives, result.edges) == (
        {},
        {},
        [],
        [],
    )


def test_analyze_empty_chunks_still_link_related_leads_to_the_lead(
    settings_stub: Settings, embedder: HashEmbedder
) -> None:
    related = [
        RelatedLeadIn(page_id=501, text="rockets and propulsion topic"),
        RelatedLeadIn(page_id=502, text="rockets and propulsion topic"),
    ]
    request = make_analyze_request([], lead="rockets and propulsion topic", related_leads=related)

    result = analyze(request, embedder, settings_stub)

    assert (result.relevance, result.cluster_ids, result.representatives) == ({}, {}, [])
    # page_id absent -> the seed falls back to placeholder id 0, embedded from the lead.
    assert _node_ids(result) == {0, 501, 502}


def test_analyze_chunks_that_cancel_out_give_the_seed_no_edges(settings_stub: Settings) -> None:
    # Chunk vectors +y and -y average to the zero vector: no direction to link by.
    embedder = ScriptedEmbedder(
        {"lead": (1, 0), "up": (0, 1), "down": (0, -1), "related": (0.6, 0.8)}
    )
    request = make_analyze_request(
        ["up", "down"], lead="lead", related_leads=[RelatedLeadIn(page_id=7, text="related")]
    )

    result = analyze(request, embedder, settings_stub)

    assert result.edges == []


@pytest.mark.parametrize(
    ("cosine", "linked"), [(0.2, False), (0.6, True)], ids=["below_threshold", "above_threshold"]
)
def test_analyze_links_a_related_lead_only_at_or_above_the_threshold(
    settings_stub: Settings, cosine: float, linked: bool
) -> None:
    assert settings_stub.edge_similarity_threshold == 0.35
    embedder = ScriptedEmbedder({"lead": (1, 0), "related": (cosine, (1 - cosine**2) ** 0.5)})
    request = make_analyze_request(
        [], lead="lead", related_leads=[RelatedLeadIn(page_id=7, text="related")]
    )

    result = analyze(request, embedder, settings_stub)

    if linked:
        assert [(e.source, e.target) for e in result.edges] == [(0, 7)]
        assert result.edges[0].weight == pytest.approx(cosine, abs=1e-6)
    else:
        assert result.edges == []


@pytest.mark.parametrize(("page_id", "seed_id"), [(None, 0), (12345, 12345)])
def test_analyze_uses_page_id_as_seed_edge_node_id(
    settings_stub: Settings, embedder: HashEmbedder, page_id: int | None, seed_id: int
) -> None:
    related = [RelatedLeadIn(page_id=999, text="alpha alpha alpha rocket propulsion engineering")]
    request = make_analyze_request(
        GROUP_A, lead="alpha rocket propulsion", related_leads=related, page_id=page_id
    )

    result = analyze(request, embedder, settings_stub)

    assert _node_ids(result) == {seed_id, 999}


@pytest.mark.parametrize(
    "fields",
    [
        {"chunks": [{"id": f"c{i}", "text": "t"} for i in range(401)]},
        {"related_leads": [{"page_id": i, "text": "t"} for i in range(41)]},
        {"max_clusters": 1},
        {"max_clusters": 7},
        {"max_edges": 0},
        {"max_edges": 81},
        {"page_id": 0},
    ],
    ids=[
        "chunks_401",
        "related_leads_41",
        "max_clusters_1",
        "max_clusters_7",
        "max_edges_0",
        "max_edges_81",
        "page_id_0",
    ],
)
def test_analyze_request_rejects_out_of_range_fields(fields: dict[str, Any]) -> None:
    payload: dict[str, Any] = {"lead": "a lead", "chunks": [], **fields}

    with pytest.raises(ValidationError):
        AnalyzeRequest(**payload)
