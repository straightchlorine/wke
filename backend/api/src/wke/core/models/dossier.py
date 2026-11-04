"""The dossier schema: pins, citations, chunks, sections, budget and views."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import ConfigDict, Field, HttpUrl, model_validator

from wke.core.models.base import WkeModel
from wke.core.models.budgets import BudgetTokens
from wke.core.models.catalog import FreshnessState

SummaryState = Literal["pending", "done", "skipped", "unavailable", "no_prose", "withheld"]


class RevisionPin(WkeModel):
    """One Wikipedia revision a citation points at, with its permalink."""

    page_id: int
    title: str
    rev_id: int
    rev_timestamp: datetime
    url: HttpUrl
    permalink: HttpUrl
    license: Literal["CC BY-SA 4.0"] = "CC BY-SA 4.0"
    retrieved_at: datetime


class Citation(WkeModel):
    """A citation to an exact revision, optionally anchored to a section."""

    id: str = Field(pattern=r"^c[0-9]+$")
    pin: RevisionPin
    role: Literal["seed", "related"]
    anchor: str | None = None
    url: HttpUrl | None = None


class TextSpan(WkeModel):
    """A stretch of a chunk's text.

    Offsets are code points into the text of the chunk, the end exclusive.
    """

    start: int = Field(ge=0)
    end: int

    @model_validator(mode="after")
    def _non_empty_span(self) -> TextSpan:
        """Reject a span that ends at or before its start."""
        if self.end <= self.start:
            raise ValueError("a span must end after it starts")
        return self


class LinkSpan(TextSpan):
    """A link from a passage to another Wikipedia article."""

    title: str


class FormulaSpan(TextSpan):
    """A formula whose TeX source the chunk text holds."""


class Chunk(WkeModel):
    """One passage of the article, kept as source text."""

    id: str
    # "prose" is a paragraph run, "facts" the infobox key facts, "table" one
    # wikitable as compact Markdown rows, "list" one list as "- item" lines;
    # only prose carries sentences.
    kind: Literal["prose", "facts", "table", "list"] = "prose"
    citation_id: str
    heading_path: list[str]
    order: int
    text: str
    est_tokens: int
    relevance: float = Field(ge=0, le=1)
    cluster_id: int | None = None
    # Live links, never citations: they carry no revision pin. Prose chunks only.
    links: list[LinkSpan] = Field(default_factory=list)
    # TeX formulas inside the text, shown as code by the Markdown renderer.
    formulas: list[FormulaSpan] = Field(default_factory=list)


class MachineSummaryParams(WkeModel):
    """The model parameters a summary was generated with."""

    num_beams: int | None = None
    min_length: int | None = None
    max_length: int | None = None
    input_tokens: int | None = None


class MachineSummary(WkeModel):
    """A condensing summary of a section, labelled as model output."""

    kind: Literal["machine_summary"] = "machine_summary"
    text: str
    model: str
    model_revision: str
    params: MachineSummaryParams
    input_chunk_ids: list[str] | None = None
    # Citation of the section the summary summarises; set when the summary
    # is attached to its section, never by the model.
    citation_id: str | None = None
    generated_at: datetime
    infer_seconds: float | None = None


class Section(WkeModel):
    """A cluster of passages under one label, with its summary state."""

    id: str
    label: str
    label_source: Literal["heading", "article_title", "structural"]
    chunk_ids: list[str]
    heading_path: list[str] = Field(default_factory=list)
    # Citation to the exact place of the section in the pinned revision.
    citation_id: str | None = None
    # Lists and tables of the section that no chunk carries.
    dropped_non_prose: bool = False
    dropped_lists: int = 0
    dropped_tables: int = 0
    summary: MachineSummary | None = None
    summary_state: SummaryState
    # Why a model summary was withheld; set only with summary_state "withheld".
    withheld_reason: str | None = None
    # Packer importance of the section in [0, 1] (wke.core.pack.importance);
    # 0.0 on dossiers stored before the field existed and on the lead.
    importance: float = Field(default=0.0, ge=0, le=1)


class GraphNode(WkeModel):
    """A page in the concept graph."""

    id: int
    title: str
    role: Literal["seed", "related"]
    section_ids: list[str] | None = None


class GraphEdge(WkeModel):
    """A similarity edge between two pages of the concept graph."""

    source: int
    target: int
    weight: float = Field(ge=0, le=1)


class DossierGraph(WkeModel):
    """The concept graph of a dossier."""

    nodes: list[GraphNode]
    edges: list[GraphEdge]


class Freshness(WkeModel):
    """How current the served dossier is against the live article."""

    state: FreshnessState
    pinned_rev_id: int
    latest_rev_id: int | None = None
    edits_since: int | None = None
    # When the watcher last observed an edit to this page; None while the
    # watcher has no data for it (source "none"). Never the request time.
    checked_at: datetime | None = None
    source: Literal["watcher", "poll", "none"]


class Budget(WkeModel):
    """How a view fits its token budget."""

    requested: BudgetTokens
    # What requested and used_est_tokens cover: the dossier part only.
    counts: Literal["dossier"] = "dossier"
    used_est_tokens: int
    estimator: Literal["chars/4"] = "chars/4"
    included_chunk_ids: list[str]
    omitted_chunks: int
    complete: bool
    # Passages cut at a sentence end to fit the budget (the lead only).
    shortened_chunk_ids: list[str] = Field(default_factory=list)


class BuildInfo(WkeModel):
    """How and when the dossier was built."""

    state: Literal["partial", "complete"]
    built_at: datetime
    pipeline_version: str
    analysis: Literal["ml", "structural"]
    summaries_done: int
    summaries_total: int
    truncated: bool | None = None
    stage_seconds: dict[str, float] | None = None


class DossierTopic(WkeModel):
    """The article a dossier is about."""

    page_id: int
    title: str
    description: str | None = None
    url: HttpUrl


class Dossier(WkeModel):
    """The stored dossier: sections, passages, citations and graph for one revision."""

    schema_version: Literal["1"] = "1"
    id: str = Field(pattern=r"^[0-9]+@[0-9]+:[0-9a-f]{12}$")
    topic: DossierTopic
    build: BuildInfo
    citations: list[Citation]
    sections: list[Section]
    chunks: list[Chunk]
    graph: DossierGraph
    license_notice: str


class DossierLinks(WkeModel):
    """Links to the other renderings of a dossier."""

    self_: HttpUrl = Field(alias="self")
    pinned: HttpUrl
    markdown: HttpUrl
    wikipedia: HttpUrl

    # extra="forbid" is inherited from WkeModel; the config merges.
    model_config = ConfigDict(populate_by_name=True)


class DossierView(Dossier):
    """A dossier packed to a token budget, as the API serves it."""

    freshness: Freshness
    budget: Budget
    links: DossierLinks


class DossierContent(WkeModel):
    """The dossier part of a response: the packed sections, passages and graph."""

    sections: list[Section]
    chunks: list[Chunk]
    graph: DossierGraph


class DossierMetadata(WkeModel):
    """The metadata part of a response: identity, build, freshness, budget and links."""

    id: str = Field(pattern=r"^[0-9]+@[0-9]+:[0-9a-f]{12}$")
    topic: DossierTopic
    build: BuildInfo
    freshness: Freshness
    budget: Budget
    links: DossierLinks


class DossierResponse(WkeModel):
    """The JSON body of a dossier read: the selected parts of a packed view.

    A part that was not selected is left out of the serialised body, never null.
    """

    schema_version: Literal["2"] = "2"
    license_notice: str
    dossier: DossierContent
    metadata: DossierMetadata | None = None
    sources: list[Citation] | None = None
