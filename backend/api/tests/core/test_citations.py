"""Section citations carry the heading id of the pinned revision."""

from __future__ import annotations

import pytest

from tests.factories.dossier import make_fixture_dossier, make_pin
from wke.core.citations import (
    assign_section_citations,
    citation_url,
    section_citation_id,
    seed_pin,
)
from wke.core.models import Chunk, Citation, Section

PIN = make_pin(1, "Example", 555)


def _chunk(cid: str, citation_id: str = "c1") -> Chunk:
    return Chunk(
        id=cid,
        citation_id=citation_id,
        heading_path=[],
        order=0,
        text="x.",
        est_tokens=1,
        relevance=0.0,
    )


def test_url_adds_the_anchor_percent_encoded_where_needed() -> None:
    assert citation_url(PIN, None) == "https://en.wikipedia.org/w/index.php?oldid=555"
    assert citation_url(PIN, "Early_life") == f"{PIN.permalink}#Early_life"
    assert citation_url(PIN, 'Say_"hi"_%C3%A9') == f"{PIN.permalink}#Say_%22hi%22_%25C3%25A9"


def test_each_section_gets_its_own_citation_and_the_lead_the_revision() -> None:
    seed = Citation(id="c1", pin=PIN, role="seed")
    # "555:2:facts" is listed in the lead but holds the infobox of section 2.
    chunks = [_chunk("a"), _chunk("555:2:facts"), _chunk("b"), _chunk("c")]
    created, of = assign_section_citations(
        [("0", ""), ("1", "Early_life"), ("2", "Career"), ("3", "Early_life")],
        chunks,
        {"0": ["a", "555:2:facts"], "1": ["b"], "2": ["c"], "3": []},
        seed,
        first_index=4,
    )
    assert [c.id for c in created] == ["c4", "c5"]
    assert [c.anchor for c in created] == ["Early_life", "Career"]
    assert all(c.role == "seed" and c.pin.rev_id == 555 for c in created)
    assert str(created[1].url) == "https://en.wikipedia.org/w/index.php?oldid=555#Career"
    assert of == {"0": "c1", "1": "c4", "2": "c5", "3": "c4"}
    assert [c.citation_id for c in chunks] == ["c1", "c5", "c4", "c5"]


def test_seed_pin_is_the_seed_citation_else_the_first_and_none_raises() -> None:
    dossier = make_fixture_dossier()
    seed = next(c for c in dossier.citations if c.role == "seed")
    assert seed_pin(dossier) == seed.pin

    related_only = dossier.model_copy(
        update={"citations": [c for c in dossier.citations if c.role == "related"]}
    )
    assert seed_pin(related_only) == related_only.citations[0].pin

    with pytest.raises(ValueError):
        seed_pin(dossier.model_copy(update={"citations": []}))


@pytest.mark.parametrize(
    ("own", "chunk_ids", "expected"),
    [("c7", ["x"], "c7"), (None, ["missing", "x"], "c3"), (None, ["missing"], "c1")],
    ids=["own-citation", "first-known-chunk", "default"],
)
def test_section_citation_id_prefers_the_section_then_its_chunk(
    own: str | None, chunk_ids: list[str], expected: str
) -> None:
    section = Section(
        id="s1",
        label="S",
        label_source="heading",
        chunk_ids=chunk_ids,
        citation_id=own,
        summary_state="skipped",
    )
    assert section_citation_id(section, {"x": _chunk("x", citation_id="c3")}) == expected
