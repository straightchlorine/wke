"""POST /v1/analyze: embed chunks, cluster, relevance, related edges.

Raw chunk vectors never leave the service: only relevance scores, cluster
ids, representative chunk ids and edge weights are returned.
"""

# since scikit-learn doesn't ship type information
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, Field
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

from wke_ml.backends import Embedder, FloatArray
from wke_ml.settings import Settings

LabelArray = npt.NDArray[np.intp]


class ChunkIn(BaseModel):
    id: str
    text: str


class RelatedLeadIn(BaseModel):
    page_id: int
    text: str


class AnalyzeRequest(BaseModel):
    page_id: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Seed node id for the analyzed article/topic, used as the "
            "source id of its edges. When absent, edges touching the "
            "seed node use placeholder id 0."
        ),
    )
    lead: str
    chunks: list[ChunkIn] = Field(max_length=400)
    related_leads: list[RelatedLeadIn] = Field(default_factory=list[RelatedLeadIn], max_length=40)
    max_clusters: int = Field(default=6, ge=2, le=6)
    max_edges: int = Field(default=20, ge=1, le=80)


class GraphEdgeOut(BaseModel):
    source: int
    target: int
    weight: float = Field(ge=0.0, le=1.0)


def _clamp(value: float, lo: float, hi: float) -> float:
    """Clamp a float32 dot product back into its theoretical range.

    Cosine similarity of normalized float32 vectors can drift a few ulps
    past +-1.0, which would otherwise fail Field(ge=..., le=...) validation.

    Args:
        value: the raw dot product.
        lo: lower bound.
        hi: upper bound.

    Returns:
        float: value clamped to [lo, hi].
    """
    return min(hi, max(lo, value))


class AnalyzeResponse(BaseModel):
    model: str
    model_revision: str
    relevance: dict[str, float]
    cluster_ids: dict[str, int]
    representatives: list[str]
    edges: list[GraphEdgeOut]
    infer_seconds: float | None = None


def _single_cluster(vectors: FloatArray) -> tuple[int, LabelArray, FloatArray]:
    """Put every vector in cluster 0.

    Args:
        vectors: chunk embeddings, shape (n, d) with n >= 1.

    Returns:
        tuple[int, LabelArray, FloatArray]: k=1, all-zero labels and the mean
        vector as the only centroid.
    """
    labels = np.zeros(vectors.shape[0], dtype=np.intp)
    return 1, labels, vectors.mean(axis=0, keepdims=True)


def _fit_kmeans(vectors: FloatArray, k: int, seed: int) -> tuple[LabelArray, FloatArray]:
    """Fit KMeans at one k.

    Args:
        vectors: normalized chunk embeddings, shape (n, d).
        k: number of clusters.
        seed: KMeans random_state.

    Returns:
        tuple[LabelArray, FloatArray]: label per chunk and centroid per cluster.
    """
    # n_init is annotated str because pyright infers it from the "auto" default.
    model = KMeans(n_clusters=k, random_state=seed, n_init=10)  # pyright: ignore[reportArgumentType]
    labels = np.asarray(model.fit_predict(vectors), dtype=np.intp)
    centroids = np.asarray(model.cluster_centers_, dtype=np.float32)
    return labels, centroids


def select_clusters(
    vectors: FloatArray, max_clusters: int, chunks_per_cluster: int, seed: int
) -> tuple[int, LabelArray, FloatArray]:
    """Choose k by silhouette score minus 0.02*k and fit KMeans at that k.

    Falls back to one cluster when there are too few chunks for two clusters
    or when KMeans cannot separate the vectors. Identical vectors return
    before any fit, so KMeans never warns about fewer distinct points than
    clusters.

    Args:
        vectors: normalized chunk embeddings, shape (n, d).
        max_clusters: caller-supplied upper bound on k (already <= 6).
        chunks_per_cluster: divisor used to size k to n (n // this value).
        seed: KMeans random_state, fixed so labels are stable across runs.

    Returns:
        tuple[int, LabelArray, FloatArray]: chosen k, label per chunk and
        centroid per cluster.
    """
    n = vectors.shape[0]
    upper = min(max_clusters, n // chunks_per_cluster)
    if upper < 2 or bool(np.all(vectors == vectors[0])):
        return _single_cluster(vectors)

    best: tuple[int, LabelArray, FloatArray] | None = None
    best_score = -np.inf
    for k in range(2, upper + 1):
        labels, centroids = _fit_kmeans(vectors, k, seed)
        if np.unique(labels).size < 2:
            continue
        score = float(silhouette_score(vectors, labels)) - 0.02 * k
        if score > best_score:
            best_score = score
            best = (k, labels, centroids)
    return best if best is not None else _single_cluster(vectors)


def pick_representatives(
    chunk_ids: Sequence[str],
    vectors: FloatArray,
    k: int,
    labels: LabelArray,
    centroids: FloatArray,
) -> list[str]:
    """Pick the chunk nearest each cluster centroid.

    Args:
        chunk_ids: chunk ids in the same order as vectors.
        vectors: chunk embeddings, shape (n, d).
        k: number of clusters.
        labels: cluster label per chunk.
        centroids: one centroid per cluster, shape (k, d).

    Returns:
        list[str]: representative chunk ids, one per non-empty cluster, in cluster order.
    """
    reps: list[str] = []
    for cluster_idx in range(k):
        members = [i for i in range(len(chunk_ids)) if labels[i] == cluster_idx]
        if not members:
            continue
        centroid = centroids[cluster_idx]
        best = min(members, key=lambda i: float(np.linalg.norm(vectors[i] - centroid)))
        reps.append(chunk_ids[best])
    return reps


# Seed node id for edges when the request carries no page_id.
_ARTICLE_NODE_ID = 0


def _seed_vector(lead: str, chunk_vectors: FloatArray, embedder: Embedder) -> FloatArray:
    """Compute the seed node's embedding for the related-leads edge graph.

    Uses the mean of the article's chunk embeddings when chunks are
    present, matching the content the reader actually sees. When chunks
    is empty (the trending job analyzes a bare topic title with no
    chunks), embeds the lead text directly instead.

    Args:
        lead: the lead/topic text from the request.
        chunk_vectors: normalized chunk embeddings; may be empty.
        embedder: embedding backend (stub or torch).

    Returns:
        FloatArray: a single normalized embedding vector.
    """
    if chunk_vectors.shape[0] == 0:
        return embedder.embed([lead])[0]

    vector = chunk_vectors.mean(axis=0)
    norm = np.linalg.norm(vector)
    if norm > 0:
        vector = vector / norm
    return vector


def _edges(
    seed_vector: FloatArray,
    seed_id: int,
    related_leads: Sequence[RelatedLeadIn],
    embedder: Embedder,
    settings: Settings,
    max_edges: int,
) -> list[GraphEdgeOut]:
    """Build the similarity graph over the seed and related leads.

    Each node (the analyzed article/topic and every related lead) keeps
    its own top edge_top_n neighbours with cosine similarity >= the
    configured threshold. Edges are undirected and deduped, so a
    related-to-related pair can appear even though neither side is the seed.

    Args:
        seed_vector: normalized embedding for the analyzed article/topic.
        seed_id: node id for the seed (payload.page_id, or the placeholder).
        related_leads: related-lead ids and texts from the request.
        embedder: embedding backend (stub or torch).
        settings: service settings (edge threshold, top_n).
        max_edges: cap on the number of edges returned (payload.max_edges).

    Returns:
        list[GraphEdgeOut]: edges sorted by weight descending, capped at max_edges.
    """
    related_vectors = embedder.embed([lead.text for lead in related_leads])
    node_ids = [seed_id] + [lead.page_id for lead in related_leads]
    node_vectors = np.vstack([seed_vector[np.newaxis, :], related_vectors])

    similarity = node_vectors @ node_vectors.T
    np.fill_diagonal(similarity, -np.inf)

    pair_weights: dict[tuple[int, int], float] = {}
    for i in range(len(node_ids)):
        order = np.argsort(similarity[i])[::-1]
        kept = 0
        for j in order:
            if kept >= settings.edge_top_n:
                break
            weight = float(similarity[i, j])
            if weight < settings.edge_similarity_threshold:
                break
            key = (min(i, int(j)), max(i, int(j)))
            pair_weights[key] = weight
            kept += 1

    edges = [
        GraphEdgeOut(source=node_ids[i], target=node_ids[j], weight=_clamp(weight, 0.0, 1.0))
        for (i, j), weight in pair_weights.items()
    ]
    edges.sort(key=lambda edge: edge.weight, reverse=True)
    return edges[:max_edges]


def analyze(payload: AnalyzeRequest, embedder: Embedder, settings: Settings) -> AnalyzeResponse:
    """Embed chunks and the lead, cluster, and score related-lead edges.

    With no chunks, clustering and relevance are skipped (empty relevance,
    cluster_ids and representatives) but edges among the seed and related
    leads are still computed, since the trending job analyzes bare topic
    titles with no chunks.

    Args:
        payload: validated /v1/analyze request body.
        embedder: embedding backend (stub or torch).
        settings: service settings (kmeans/edge tuning, model identity).

    Returns:
        AnalyzeResponse: the /v1/analyze response body.
    """
    chunk_ids = [c.id for c in payload.chunks]
    n = len(chunk_ids)
    seed_id = payload.page_id if payload.page_id is not None else _ARTICLE_NODE_ID

    relevance: dict[str, float] = {}
    cluster_ids: dict[str, int] = {}
    representatives: list[str] = []
    chunk_vectors: FloatArray = np.empty((0, 0), dtype=np.float32)

    if n > 0:
        all_texts = [payload.lead] + [c.text for c in payload.chunks]
        all_vectors = embedder.embed(all_texts)
        lead_vector = all_vectors[0]
        chunk_vectors = all_vectors[1:]

        relevance = {
            chunk_ids[i]: _clamp(float(np.dot(chunk_vectors[i], lead_vector)), 0.0, 1.0)
            for i in range(n)
        }

        max_clusters = min(payload.max_clusters, settings.kmeans_max_k)
        k, labels, centroids = select_clusters(
            chunk_vectors, max_clusters, settings.kmeans_chunks_per_cluster, settings.kmeans_seed
        )
        cluster_ids = {chunk_ids[i]: int(labels[i]) for i in range(n)}
        representatives = pick_representatives(chunk_ids, chunk_vectors, k, labels, centroids)

    edges: list[GraphEdgeOut] = []
    if payload.related_leads:
        seed_vector = _seed_vector(payload.lead, chunk_vectors, embedder)
        edges = _edges(
            seed_vector, seed_id, payload.related_leads, embedder, settings, payload.max_edges
        )

    return AnalyzeResponse(
        model=settings.embed_model,
        model_revision=settings.embed_model_revision,
        relevance=relevance,
        cluster_ids=cluster_ids,
        representatives=representatives,
        edges=edges,
    )
