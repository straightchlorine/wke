"""A deterministic fixture Dossier used by other tests, plus
Hypothesis strategies for property tests over pack.pack invariants.

Not a conftest fixture module, since golden tests need the exact same Dossier
object identity-free across regeneration runs, and the Hypothesis strategies
need to be composable in test bodies.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from hypothesis import strategies as st
from pydantic import HttpUrl, TypeAdapter

from wke.core.models import (
    Budget,
    BuildInfo,
    Chunk,
    Citation,
    Dossier,
    DossierGraph,
    DossierLinks,
    DossierTopic,
    DossierView,
    Freshness,
    GraphEdge,
    GraphNode,
    MachineSummary,
    MachineSummaryParams,
    RevisionPin,
    Section,
)
from wke.core.text.tokens import est_tokens

FACTORY_TITLE = "Jesus"
FACTORY_PAGE_ID = 1095706
FACTORY_REV_ID = 1382805013
FACTORY_RELATED_TITLE = "Gospel of Mark"
FACTORY_RELATED_PAGE_ID = 12490
FACTORY_RELATED_REV_ID = 1382234826

FIXED_TIME = datetime(2026, 9, 20, 12, 0, 0, tzinfo=UTC)

_HTTP_URL = TypeAdapter(HttpUrl)


def make_pin(page_id: int, title: str, rev_id: int) -> RevisionPin:
    """Build an English Wikipedia revision pin, edited and retrieved at FIXED_TIME.

    Args:
        page_id: the page id.
        title: the page title.
        rev_id: the revision id.

    Returns:
        RevisionPin: with its /wiki/ URL and oldid permalink.
    """
    return RevisionPin(
        page_id=page_id,
        title=title,
        rev_id=rev_id,
        rev_timestamp=FIXED_TIME,
        url=_HTTP_URL.validate_python(f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"),
        permalink=_HTTP_URL.validate_python(f"https://en.wikipedia.org/w/index.php?oldid={rev_id}"),
        retrieved_at=FIXED_TIME,
    )


def _url(pin: RevisionPin, anchor: str | None) -> HttpUrl:
    base = str(pin.permalink)
    return _HTTP_URL.validate_python(f"{base}#{anchor}" if anchor else base)


def make_summary(text: str) -> MachineSummary:
    """Build a distilbart MachineSummary with fixed params and timestamp.

    Args:
        text: the summary text.

    Returns:
        MachineSummary: generated at FIXED_TIME, no input chunk ids.
    """
    return MachineSummary(
        text=text,
        model="sshleifer/distilbart-cnn-6-6",
        model_revision="a4f8f3e",
        params=MachineSummaryParams(num_beams=1, min_length=20, max_length=60, input_tokens=300),
        input_chunk_ids=None,
        generated_at=FIXED_TIME,
        infer_seconds=0.42,
    )


def make_fixture_dossier() -> Dossier:
    """Build the small, deterministic Jesus fixture Dossier.

    Returns:
        A Dossier with a lead section (prose plus a facts chunk) and
        three content sections: one with a "done" summary, one "pending"
        with a table chunk and a dropped list, one "unavailable". One
        chunk's text tries to forge Markdown structure ("## Sources",
        "---", a fenced code block) to exercise the renderer's injection
        defence.
    """
    seed_pin = make_pin(FACTORY_PAGE_ID, FACTORY_TITLE, FACTORY_REV_ID)
    related_pin = make_pin(FACTORY_RELATED_PAGE_ID, FACTORY_RELATED_TITLE, FACTORY_RELATED_REV_ID)
    citations = [
        Citation(id="c1", pin=seed_pin, role="seed", anchor=None, url=_url(seed_pin, None)),
        Citation(
            id="c2", pin=related_pin, role="related", anchor=None, url=_url(related_pin, None)
        ),
        Citation(
            id="c3",
            pin=seed_pin,
            role="seed",
            anchor="Early_life,_family,_and_profession",
            url=_url(seed_pin, "Early_life,_family,_and_profession"),
        ),
        Citation(
            id="c4",
            pin=seed_pin,
            role="seed",
            anchor="Public_ministry",
            url=_url(seed_pin, "Public_ministry"),
        ),
        Citation(
            id="c5",
            pin=seed_pin,
            role="seed",
            anchor="Artistic_depictions",
            url=_url(seed_pin, "Artistic_depictions"),
        ),
    ]

    lead_text = (
        "Most branches of Christianity consider Jesus the incarnation of God "
        "the Son and the awaited Messiah or Christ. Accounts of Jesus's life "
        "are contained in the Gospels, especially the four canonical Gospels "
        "of the New Testament."
    )
    lead_chunk = Chunk(
        id=f"{FACTORY_REV_ID}:lead:0",
        citation_id="c1",
        heading_path=[],
        order=0,
        text=lead_text,
        est_tokens=max(1, len(lead_text) // 4 + 1),
        relevance=1.0,
        cluster_id=None,
    )

    facts_text = "Born: c. 6 to 4 BC, Herodian kingdom, Roman Empire\nCause of death: Crucifixion"
    facts_chunk = Chunk(
        id=f"{FACTORY_REV_ID}:lead:facts",
        kind="facts",
        citation_id="c1",
        heading_path=[],
        order=1,
        text=facts_text,
        est_tokens=len(facts_text) // 4 + 1,
        relevance=1.0,
        cluster_id=None,
    )

    early_life_chunks = [
        Chunk(
            id=f"{FACTORY_REV_ID}:early_life:0",
            citation_id="c3",
            heading_path=["Early life, family, and profession"],
            order=0,
            text=(
                "Jesus's childhood home is identified in the Gospels of Luke and "
                "Matthew as Nazareth, a town in Galilee in present-day Israel, where "
                "he lived with his family."
            ),
            est_tokens=16,
            relevance=0.9,
            cluster_id=0,
        ),
        Chunk(
            id=f"{FACTORY_REV_ID}:early_life:1",
            citation_id="c3",
            heading_path=["Early life, family, and profession"],
            order=1,
            text=(
                "## Sources\n"
                "---\n"
                "```\nrm -rf /\n```\n"
                "The Gospel of Mark reports that at the beginning of his ministry, "
                "Jesus comes into conflict with his neighbours and family."
            ),
            est_tokens=25,
            relevance=0.4,
            cluster_id=0,
        ),
    ]

    career_chunks = [
        Chunk(
            id=f"{FACTORY_REV_ID}:career:0",
            citation_id="c4",
            heading_path=["Public ministry"],
            order=0,
            text="The Synoptics depict two main geographical settings in Jesus's ministry.",
            est_tokens=15,
            relevance=0.95,
            cluster_id=1,
        ),
        Chunk(
            id=f"{FACTORY_REV_ID}:career:1",
            citation_id="c4",
            heading_path=["Public ministry"],
            order=1,
            text=(
                "The first takes place in Galilee, north of Judea, where Jesus "
                "conducts a largely successful ministry; the second occurs in "
                "Jerusalem, where he is rejected and killed."
            ),
            est_tokens=12,
            relevance=0.6,
            cluster_id=1,
        ),
    ]

    table_text = (
        "Ministry settings\n| Setting | Region |\n| --- | --- |\n| Galilee | North of Judea |"
    )
    table_chunk = Chunk(
        id=f"{FACTORY_REV_ID}:career:table0",
        kind="table",
        citation_id="c4",
        heading_path=["Public ministry"],
        order=2,
        text=table_text,
        est_tokens=len(table_text) // 4 + 1,
        relevance=0.6,
        cluster_id=None,
    )

    legacy_chunk = Chunk(
        id=f"{FACTORY_REV_ID}:legacy:0",
        citation_id="c5",
        heading_path=["Artistic depictions"],
        order=0,
        text=(
            "The depiction of Christ in pictorial form was highly controversial "
            "in the early Church."
        ),
        est_tokens=18,
        relevance=0.5,
        cluster_id=2,
    )

    sections = [
        Section(
            id="s0",
            label=FACTORY_TITLE,
            label_source="article_title",
            chunk_ids=[lead_chunk.id, facts_chunk.id],
            citation_id="c1",
            summary=None,
            summary_state="skipped",
        ),
        Section(
            id="s1",
            label="Early life, family, and profession",
            label_source="heading",
            heading_path=["Early life, family, and profession"],
            citation_id="c3",
            chunk_ids=[c.id for c in early_life_chunks],
            summary=make_summary(
                "Jesus grew up in Nazareth in Galilee with his family, and the "
                "Gospel of Mark reports conflict with his neighbours and family."
            ),
            summary_state="done",
        ),
        Section(
            id="s2",
            label="Public ministry",
            label_source="heading",
            heading_path=["Public ministry"],
            citation_id="c4",
            chunk_ids=[c.id for c in career_chunks] + [table_chunk.id],
            dropped_non_prose=True,
            dropped_lists=1,
            summary=None,
            summary_state="pending",
        ),
        Section(
            id="s3",
            label="Artistic depictions",
            label_source="heading",
            heading_path=["Artistic depictions"],
            citation_id="c5",
            chunk_ids=[legacy_chunk.id],
            summary=None,
            summary_state="unavailable",
        ),
    ]

    chunks = [
        lead_chunk,
        facts_chunk,
        *early_life_chunks,
        *career_chunks,
        table_chunk,
        legacy_chunk,
    ]

    graph = DossierGraph(
        nodes=[
            GraphNode(
                id=FACTORY_PAGE_ID,
                title=FACTORY_TITLE,
                role="seed",
                section_ids=["s0", "s1", "s2", "s3"],
            ),
            GraphNode(
                id=FACTORY_RELATED_PAGE_ID,
                title=FACTORY_RELATED_TITLE,
                role="related",
                section_ids=["s2"],
            ),
        ],
        edges=[GraphEdge(source=FACTORY_PAGE_ID, target=FACTORY_RELATED_PAGE_ID, weight=0.71)],
    )

    return Dossier(
        id=f"{FACTORY_PAGE_ID}@{FACTORY_REV_ID}:abcdef012345",
        topic=DossierTopic(
            page_id=FACTORY_PAGE_ID,
            title=FACTORY_TITLE,
            description="First-century Jewish preacher and religious leader",
            url=_HTTP_URL.validate_python(f"https://en.wikipedia.org/wiki/{FACTORY_TITLE}"),
        ),
        build=BuildInfo(
            state="complete",
            built_at=FIXED_TIME,
            pipeline_version="test-pv",
            analysis="ml",
            summaries_done=1,
            summaries_total=4,
            truncated=False,
            stage_seconds=None,
        ),
        citations=citations,
        sections=sections,
        chunks=chunks,
        graph=graph,
        license_notice=(
            "Text from Wikipedia, licensed CC BY-SA 4.0. Model summaries and "
            "clusters are produced by WKE and are not part of the Wikipedia "
            "article."
        ),
    )


def make_overflowing_fixture_dossier() -> Dossier:
    """Build a deterministic Dossier large enough to overflow the 2000 budget.

    The packing invariants (used tokens within the budget, each budget's
    chunks a subset of the next one's, complete only when nothing is
    omitted) are meaningless if every fixture and golden dossier fits
    under 2000 tokens uncut; this
    one is sized (10 sections, 6 chunks each, ~150 words per chunk) so
    dossier_2000's `omitted_chunks` is provably nonzero.

    Returns:
        A Dossier with 10 sections of 6 low-relevance chunks each.
    """
    seed_pin = make_pin(42, "Overflow Topic", 7_000_000)
    citations = [Citation(id="c1", pin=seed_pin, role="seed", anchor=None, url=None)]

    lead_text = "Overflow Topic is a fixture article built to exceed the pack budget."
    lead_chunk = Chunk(
        id="7000000:lead:0",
        citation_id="c1",
        heading_path=[],
        order=0,
        text=lead_text,
        est_tokens=max(1, len(lead_text) // 4 + 1),
        relevance=1.0,
        cluster_id=None,
    )
    chunks = [lead_chunk]
    sections = [
        Section(
            id="s0",
            label="Overflow Topic",
            label_source="article_title",
            chunk_ids=[lead_chunk.id],
            summary=None,
            summary_state="skipped",
        )
    ]

    paragraph = " ".join(f"Sentence number {n} about the topic." for n in range(1, 26))
    n_sections = 10
    n_chunks_per_section = 6
    for section_index in range(n_sections):
        section_id = f"sec{section_index}"
        section_chunk_ids: list[str] = []
        for chunk_index in range(n_chunks_per_section):
            chunk_id = f"{section_id}:{chunk_index}"
            chunk = Chunk(
                id=chunk_id,
                citation_id="c1",
                heading_path=[f"Section {section_index}"],
                order=chunk_index,
                text=paragraph,
                est_tokens=max(1, len(paragraph) // 4 + 1),
                # Strictly descending relevance: every chunk ranks below the
                # one before it, so the later sections are the last to fit.
                relevance=1.0 - (section_index * n_chunks_per_section + chunk_index) * 0.001,
                cluster_id=section_index,
            )
            chunks.append(chunk)
            section_chunk_ids.append(chunk_id)
        sections.append(
            Section(
                id=section_id,
                label=f"Section {section_index}",
                label_source="heading",
                heading_path=[f"Section {section_index}"],
                chunk_ids=section_chunk_ids,
                summary=make_summary(f"Section {section_index} is summarised here."),
                summary_state="done",
            )
        )

    return Dossier(
        id="42@7000000:000000000000",
        topic=DossierTopic(
            page_id=42,
            title="Overflow Topic",
            description=None,
            url=_HTTP_URL.validate_python("https://en.wikipedia.org/wiki/Overflow_Topic"),
        ),
        build=BuildInfo(
            state="complete",
            built_at=FIXED_TIME,
            pipeline_version="test-pv",
            analysis="structural",
            summaries_done=0,
            summaries_total=n_sections,
            truncated=None,
            stage_seconds=None,
        ),
        citations=citations,
        sections=sections,
        chunks=chunks,
        graph=DossierGraph(nodes=[], edges=[]),
        license_notice="Text from Wikipedia, licensed CC BY-SA 4.0.",
    )


def make_links(dossier: Dossier | None = None) -> DossierLinks:
    """Build the response links of the fixture dossier.

    Args:
        dossier: The dossier the links point at; the factory dossier when None.

    Returns:
        DossierLinks: self, pinned, markdown and Wikipedia links on a test host.
    """
    page_id = dossier.topic.page_id if dossier else FACTORY_PAGE_ID
    title = dossier.topic.title.replace(" ", "_") if dossier else FACTORY_TITLE
    rev_id = FACTORY_REV_ID
    base = f"https://wke.example/api/v1/dossiers/{page_id}"
    return DossierLinks(
        self=_HTTP_URL.validate_python(base),
        pinned=_HTTP_URL.validate_python(f"{base}/rev/{rev_id}"),
        markdown=_HTTP_URL.validate_python(f"{base}.md"),
        wikipedia=_HTTP_URL.validate_python(f"https://en.wikipedia.org/wiki/{title}"),
    )


def make_nested_dossier() -> Dossier:
    """Build a dossier of nested, empty and multi-chunk sections.

    Returns:
        Dossier: lead, empty parent with a child, a leaf without prose, a two-chunk section.
    """
    base = make_fixture_dossier()
    template = base.chunks[0]

    def chunk(n: int, path: list[str]) -> Chunk:
        return template.model_copy(
            update={
                "id": f"1:{n}:0",
                "heading_path": path,
                "order": n,
                "text": f"Passage number {n}.",
                "est_tokens": 6,
            }
        )

    chunks = [chunk(0, []), chunk(2, ["Parent", "Child"]), chunk(4, ["Busy"]), chunk(5, ["Busy"])]
    chunks[3] = chunks[3].model_copy(update={"id": "1:4:1"})

    def section(sid: str, label: str, path: list[str], ids: list[str], state: str) -> Section:
        return Section(
            id=sid,
            label=label,
            label_source="article_title" if sid == "0" else "heading",
            chunk_ids=ids,
            heading_path=path,
            summary_state=state,  # type: ignore[arg-type]
        )

    sections = [
        section("0", "Topic", [], ["1:0:0"], "skipped"),
        section("1", "Parent", ["Parent"], [], "no_prose"),
        section("2", "Child", ["Parent", "Child"], ["1:2:0"], "skipped"),
        section("3", "Leaf", ["Leaf"], [], "no_prose"),
        section("4", "Busy", ["Busy"], ["1:4:0", "1:4:1"], "skipped"),
    ]
    return base.model_copy(update={"sections": sections, "chunks": chunks})


def make_budget_dossier() -> Dossier:
    """Build a dossier whose last two sections hold passages too big for 2000 tokens.

    Returns:
        Dossier: lead, a heading-only parent whose child fits, and two sections
        whose passages do not.
    """
    dossier = make_nested_dossier()
    template = dossier.chunks[0]
    big = template.model_copy(
        update={"id": "1:9:0", "heading_path": ["Huge"], "order": 9, "text": "x" * 8000}
    )
    big = big.model_copy(update={"est_tokens": est_tokens(big.text)})
    huge2 = big.model_copy(update={"id": "1:10:0", "heading_path": ["Huger"], "order": 10})
    summary = make_summary("A short summary.")

    def section(sid: str, label: str, path: list[str], ids: list[str], state: str) -> Section:
        return Section(
            id=sid,
            label=label,
            label_source="heading",
            chunk_ids=ids,
            heading_path=path,
            summary_state=state,  # type: ignore[arg-type]
            summary=summary if state == "done" else None,
        )

    sections = [
        *dossier.sections[:3],
        section("5", "Huge", ["Huge"], ["1:9:0"], "done"),
        section("6", "Huger", ["Huger"], ["1:10:0"], "skipped"),
        *dossier.sections[3:],
    ]
    return dossier.model_copy(
        update={"sections": sections, "chunks": [*dossier.chunks, big, huge2]}
    )


def make_lead_only_dossier(tokens: int = 0, text: str | None = None) -> Dossier:
    """Build a dossier whose only content is one lead passage.

    Args:
        tokens: Size of a generated lead in estimated tokens; ignored when text is given.
        text: The lead text itself.

    Returns:
        Dossier: one section holding one link-free lead chunk, with no summary.
    """
    dossier = make_fixture_dossier()
    body = text if text is not None else "w" * (tokens * 4 - 1) + "."
    lead = dossier.chunks[0].model_copy(
        update={"text": body, "est_tokens": est_tokens(body), "links": []}
    )
    section = dossier.sections[0].model_copy(
        update={"chunk_ids": [lead.id], "summary": None, "summary_state": "skipped"}
    )
    return dossier.model_copy(update={"sections": [section], "chunks": [lead]})


def make_freshness(dossier: Dossier) -> Freshness:
    """Build a plausible Freshness for the fixture dossier.

    Args:
        dossier: The dossier to compute freshness against.

    Returns:
        A "fresh" Freshness pinned at the dossier's seed revision.
    """
    from wke.core.citations import seed_pin

    pin = seed_pin(dossier)
    return Freshness(
        state="fresh",
        pinned_rev_id=pin.rev_id,
        latest_rev_id=pin.rev_id,
        edits_since=0,
        checked_at=FIXED_TIME,
        source="poll",
    )


def make_heading_map(view: DossierView) -> dict[str, str]:
    """Map each section anchor of a view to its heading, as the revision HTML holds them.

    Args:
        view: a view of the fixture dossier.

    Returns:
        dict[str, str]: anchor -> heading text, the shape of validate.heading_map.
    """
    anchors = {c.id: c.anchor for c in view.citations}
    return {
        anchor: s.heading_path[-1]
        for s in view.sections
        if s.heading_path and (anchor := anchors.get(s.citation_id or ""))
    }


def make_fixture_view() -> DossierView:
    """Build the whole fixture dossier as a served view, without packing it.

    Returns:
        DossierView: every chunk included; each summary cites its section, as
        the served view sets it.
    """
    dossier = make_fixture_dossier()
    sections = [
        s.model_copy(
            update={"summary": s.summary.model_copy(update={"citation_id": s.citation_id})}
        )
        if s.summary is not None
        else s
        for s in dossier.sections
    ]
    budget = Budget(
        requested=32000,
        used_est_tokens=sum(c.est_tokens for c in dossier.chunks),
        included_chunk_ids=[c.id for c in dossier.chunks],
        omitted_chunks=0,
        complete=True,
    )
    return DossierView(
        **dict(dossier.model_copy(update={"sections": sections})),
        freshness=make_freshness(dossier),
        budget=budget,
        links=make_links(dossier),
    )


# The summary states a generated section may take (no_prose and withheld need no chunks
# or a failed source check, which the strategy does not model).
_DRAWN_SUMMARY_STATES: tuple[Literal["pending", "done", "skipped", "unavailable"], ...] = (
    "pending",
    "done",
    "skipped",
    "unavailable",
)

_TEXT_ALPHABET = st.characters(
    whitelist_categories=("Lu", "Ll", "Nd", "Zs"), whitelist_characters=".,"
)


@st.composite
def chunk_text(draw: st.DrawFn) -> str:
    """A piece of chunk body text.

    Args:
        draw: Hypothesis draw function.

    Returns:
        A 1-1000 character ASCII-ish string. The upper end is wide enough
        that a real share of generated dossiers overflow the 2000-token
        budget and exercise the packer's truncation path (core/pack).
    """
    return draw(st.text(alphabet=_TEXT_ALPHABET, min_size=1, max_size=1000))


@st.composite
def dossiers(draw: st.DrawFn) -> Dossier:
    """Generate a structurally valid Dossier for property tests.

    Args:
        draw: Hypothesis draw function.

    Returns:
        A Dossier with 1-12 sections, a lead chunk and 0-10 content
        chunks per section, random but valid relevance/order/summary_state.
    """
    n_sections = draw(st.integers(min_value=1, max_value=12))
    page_id = draw(st.integers(min_value=1, max_value=10_000_000))
    rev_id = draw(st.integers(min_value=1, max_value=10_000_000))

    seed_pin_ = make_pin(page_id, "Fixture Topic", rev_id)
    citations = [Citation(id="c1", pin=seed_pin_, role="seed", anchor=None, url=None)]

    lead_text = draw(chunk_text())
    lead_chunk = Chunk(
        id="lead:0",
        citation_id="c1",
        heading_path=[],
        order=0,
        text=lead_text,
        est_tokens=max(1, (len(lead_text) + 3) // 4),
        relevance=1.0,
        cluster_id=None,
    )
    chunks = [lead_chunk]
    sections: list[Section] = [
        Section(
            id="s0",
            label="Fixture Topic",
            label_source="article_title",
            chunk_ids=[lead_chunk.id],
            summary=None,
            summary_state="skipped",
        )
    ]

    summary_states = draw(
        st.lists(
            st.sampled_from(_DRAWN_SUMMARY_STATES),
            min_size=n_sections,
            max_size=n_sections,
        )
    )

    for section_index in range(n_sections):
        n_chunks = draw(st.integers(min_value=0, max_value=10))
        section_id = f"sec{section_index}"
        section_chunk_ids: list[str] = []
        for chunk_index in range(n_chunks):
            text = draw(chunk_text())
            relevance = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
            chunk = Chunk(
                id=f"{section_id}:{chunk_index}",
                citation_id="c1",
                heading_path=[f"Section {section_index}"],
                order=chunk_index,
                text=text,
                est_tokens=max(1, (len(text) + 3) // 4),
                relevance=relevance,
                cluster_id=section_index,
            )
            chunks.append(chunk)
            section_chunk_ids.append(chunk.id)

        state = summary_states[section_index]
        summary = make_summary("A short summary.") if state == "done" else None
        sections.append(
            Section(
                id=section_id,
                label=f"Section {section_index}",
                label_source="heading",
                heading_path=[f"Section {section_index}"],
                chunk_ids=section_chunk_ids,
                summary=summary,
                summary_state=state,
            )
        )

    return Dossier(
        id="1@1:000000000000",
        topic=DossierTopic(
            page_id=page_id,
            title="Fixture Topic",
            description=None,
            url=_HTTP_URL.validate_python("https://en.wikipedia.org/wiki/Fixture_Topic"),
        ),
        build=BuildInfo(
            state="complete",
            built_at=FIXED_TIME,
            pipeline_version="test-pv",
            analysis="structural",
            summaries_done=0,
            summaries_total=n_sections,
            truncated=None,
            stage_seconds=None,
        ),
        citations=citations,
        sections=sections,
        chunks=chunks,
        graph=DossierGraph(nodes=[], edges=[]),
        license_notice="Text from Wikipedia, licensed CC BY-SA 4.0.",
    )
