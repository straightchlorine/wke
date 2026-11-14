"""Link spans of a passage: which are usable, how the text splits at them, their URLs."""

from __future__ import annotations

from wke.core.models import LinkSpan
from wke.core.text.wikilinks import link_url, split_linked, usable_spans, wiki_origin

TEXT = "Jesus taught in Galilee and Judea."


def test_usable_spans_are_sorted_inside_the_text_and_never_overlap() -> None:
    galilee = LinkSpan(start=16, end=23, title="Galilee")
    overlapping = LinkSpan(start=20, end=27, title="Lee")
    judea = LinkSpan(start=28, end=33, title="Judea")
    past_a_cut = LinkSpan(start=28, end=33, title="Judea")

    assert usable_spans([judea, overlapping, galilee], len(TEXT)) == [galilee, judea]
    assert usable_spans([past_a_cut], 30) == []


def test_split_linked_joins_back_to_the_text() -> None:
    spans = [LinkSpan(start=16, end=23, title="Galilee")]
    runs = split_linked(TEXT, spans)
    assert runs == [("Jesus taught in ", None), ("Galilee", "Galilee"), (" and Judea.", None)]
    assert "".join(run for run, _ in runs) == TEXT


def test_link_url_uses_underscores_and_encodes_parentheses() -> None:
    origin = wiki_origin("https://en.wikipedia.org/w/index.php?oldid=1")
    assert origin == "https://en.wikipedia.org"
    assert link_url(origin, "Mary (mother of Jesus)") == (
        "https://en.wikipedia.org/wiki/Mary_%28mother_of_Jesus%29"
    )
