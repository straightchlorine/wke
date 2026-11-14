"""Which section owns a chunk, which sections enclose another, and what a chunk id says."""

from __future__ import annotations

import pytest

from tests.factories.packing import make_section
from tests.factories.synthetic import dossier_of
from wke.core import pack
from wke.core.pack.owners import ancestors, section_of


@pytest.mark.parametrize(
    ("chunk_id", "kind"),
    [
        ("7:3:list0", "list"),
        ("7:3:table1", "table"),
        ("7:3:facts", "facts"),
        ("7:3:0", "prose"),
    ],
)
def test_chunk_kind_names_the_kind_from_the_id(chunk_id: str, kind: str) -> None:
    assert pack.chunk_kind(chunk_id) == kind


def test_a_chunk_listed_by_two_sections_belongs_to_the_first() -> None:
    sections = [make_section("a", ["A"], ["c1", "c2"]), make_section("b", ["B"], ["c2"])]
    assert section_of(dossier_of(sections, [])) == {"c1": "a", "c2": "a"}


def test_ancestors_are_the_sections_whose_heading_path_encloses_a_later_one() -> None:
    sections = [
        make_section("lead", [], []),
        make_section("a", ["A"], []),
        make_section("ab", ["A", "B"], []),
        make_section("abc", ["A", "B", "C"], []),
        make_section("d", ["D"], []),
        make_section("de", ["D", "E"], []),
    ]
    assert ancestors(sections) == {
        "lead": [],
        "a": [],
        "ab": ["a"],
        "abc": ["a", "ab"],
        "d": [],
        "de": ["d"],
    }
