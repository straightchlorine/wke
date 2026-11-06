"""The recall script scores a dossier Markdown against fixed questions."""

from __future__ import annotations

import pytest

from tests.factories.dossier import make_fixture_view
from tests.support.scripts import load_script
from wke.core.render import render_markdown

recall = load_script("eval_recall.py")

DOCUMENT = """# Title

Header line that names Carpenter.

## Early life

Jesus grew up in Nazareth.

### Public ministry

He taught in Galilee.

## Sources

[c1] Carpenter source line
"""


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "Caf\N{LATIN SMALL LETTER E WITH ACUTE}  Z\N{LATIN SMALL LETTER U WITH DIAERESIS}rich",
            "cafe zurich",
        ),
        ("1990 \N{EN DASH} 2000, 1990\N{EM DASH}2000", "1990-2000, 1990-2000"),
        (
            "\N{LEFT DOUBLE QUOTATION MARK}quoted\N{RIGHT DOUBLE QUOTATION MARK} "
            "and it\N{RIGHT SINGLE QUOTATION MARK}s",
            '"quoted" and it\'s',
        ),
        ("[the link](https://example.org/a) text", "the link text"),
        ("snake\\_case and \\*stars\\*", "snake_case and *stars*"),
    ],
)
def test_normalise_folds_what_a_reader_does_not_see(raw: str, expected: str) -> None:
    assert recall.normalise(raw) == expected


def test_scored_text_drops_header_headings_and_sources() -> None:
    body = recall.scored_text(DOCUMENT, headings=False)
    assert body == "jesus grew up in nazareth. he taught in galilee."
    assert "early life" in recall.scored_text(DOCUMENT, headings=True)
    assert "carpenter" not in recall.scored_text(DOCUMENT, headings=True)


def test_scored_text_follows_the_rendered_summary_block() -> None:
    view = make_fixture_view()
    summary = next(s.summary.text for s in view.sections if s.summary is not None)
    markdown = render_markdown(view, include_summaries=True)
    assert recall.normalise(summary) in recall.scored_text(markdown, headings=False, summaries=True)
    assert recall.normalise(summary) not in recall.scored_text(markdown, headings=False)


def test_answered_matches_substrings_and_regular_expressions() -> None:
    text = recall.normalise("He was born on 19 July 1860 in Fall River.")
    assert recall.answered(text, ["July 19, 1860", "19 July 1860"])
    assert recall.answered(text, ["re:born on \\d+ july"])
    assert not recall.answered(text, ["1861", "re:^fall river"])


def test_score_topic_counts_hits_per_tag_and_importance() -> None:
    questions = [
        {"id": "q1", "tag": "prose", "importance": "key", "answers": ["nazareth"]},
        {"id": "q2", "tag": "prose", "answers": ["galilee"]},
        {
            "id": "q3",
            "tag": "table",
            "importance": "key",
            "answers": ["early life"],
            "headings_count": True,
        },
        {"id": "q4", "tag": "table", "answers": ["early life"]},
        {"id": "q5", "tag": "prose", "answers": ["nazareth"]},
        {"id": "q6", "tag": "prose", "answers": ["paris"]},
    ]
    scored = recall.score_topic(DOCUMENT, questions)
    assert scored["hits"] == dict(q1=True, q2=True, q3=True, q4=False, q5=True, q6=False)
    assert (scored["answered"], scored["total"], scored["recall"]) == (4, 6, 0.6667)
    assert scored["by_tag"] == {
        "prose": {"answered": 3, "total": 4},
        "table": {"answered": 1, "total": 2},
    }
    assert scored["by_importance"] == {
        "detail": {"answered": 2, "total": 4},
        "key": {"answered": 2, "total": 2},
    }
    assert scored["missed"] == ["q4", "q6"]


def test_summarise_adds_topics_up_per_budget() -> None:
    one = {
        "answered": 1,
        "total": 2,
        "tokens_est": 10,
        "by_tag": {"prose": {"answered": 1, "total": 2}},
        "by_importance": {"key": {"answered": 1, "total": 1}},
    }
    two = {**one, "answered": 2, "tokens_est": 5}
    out = recall.summarise({"a": {"2000": one}, "b": {"2000": two}}, [2000])["2000"]
    assert (out["answered"], out["total"], out["tokens_est"], out["recall"]) == (3, 4, 15, 0.75)
    assert out["by_tag"]["prose"] == {"answered": 2, "total": 4, "recall": 0.5}
    assert out["by_tag"]["table"]["recall"] is None
