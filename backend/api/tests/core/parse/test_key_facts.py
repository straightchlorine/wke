"""Where the infobox key facts go and which infobox they come from."""

from __future__ import annotations

from tests.factories.parsed import LEAD, REV_ID, parse_sections, texts
from wke.core.citations import home_section_id

BODY = "<p>History is told in full sentences here.</p>"


def _infobox(label: str, value: str) -> str:
    return (
        f"<table class='infobox'><tbody><tr><th>{label}</th><td>{value}</td></tr></tbody></table>"
    )


def test_infobox_in_a_body_section_becomes_the_key_facts_listed_in_the_lead() -> None:
    article = parse_sections(LEAD, _infobox("Born", "1900") + BODY)
    chunk = next(c for c in article.chunks if c.kind == "facts")
    lead, history = article.sections
    assert chunk.id == f"{REV_ID}:1:facts"
    assert chunk.id in lead.chunk_ids and chunk.id not in history.chunk_ids
    assert chunk.heading_path == ["Part 1"]
    assert lead.chunk_ids[-1] == chunk.id
    assert home_section_id(chunk.id, lead.id) == "1"
    assert [c.kind for c in article.chunks] == ["prose", "facts", "prose"]
    assert [c.order for c in article.chunks] == [0, 1, 2]


def test_only_the_first_infobox_in_the_article_is_the_key_facts() -> None:
    article = parse_sections(_infobox("Born", "1900") + LEAD, _infobox("Died", "1990") + BODY)
    assert texts(article, "facts") == ["Born: 1900"]
    assert article.sections[1].dropped_tables == 1
