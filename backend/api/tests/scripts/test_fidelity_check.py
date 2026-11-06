"""The offline fidelity script reports what the summary gate withholds."""

from __future__ import annotations

from typing import Any

import pytest

from tests.factories.summaries import DEFECTIVE_SUMMARIES
from tests.support.scripts import load_script
from wke.core.text.sentences import split_sentences

fidelity = load_script("eval/fidelity_check.py")


@pytest.mark.parametrize("name", DEFECTIVE_SUMMARIES)
def test_script_reports_the_same_defect_as_hard(name: str) -> None:
    summary, source, _ = DEFECTIVE_SUMMARIES[name]
    assert any(f.severity == "hard" for f in fidelity.check(summary, source))


def test_script_reports_a_missing_full_stop_after_a_quotation_as_soft() -> None:
    summary = 'Manon said the hiatus was for "personal wellbeing" Sophia also took a break .'
    source = 'Manon said the hiatus was for "personal wellbeing". Sophia also took a break.'
    failures = fidelity.check(summary, source)
    assert {(f.sub, f.severity) for f in failures if f.rule == "glitch"} == {("run_on", "soft")}


@pytest.mark.parametrize(
    ("summary", "sub"),
    [
        ("The film , which opened in May , was a hit .", "space_before"),
        ("Yes indeed . The film opened in May and it was a hit with the critics .", "short"),
        (
            "The film opened in May and was a hit . It ran for a year in London . "
            "The film opened in May and was a hit .",
            "duplicate_sentence",
        ),
        (
            "The film opened in May to a large crowd. A sequel followed later. "
            "The film opened in May to critics.",
            "duplicate_ngram",
        ),
        (
            "The film opened in May and was a hit . The film opened in May and was a hit .",
            "duplicate_sentence",
        ),
    ],
)
def test_soft_glitches_names_each_glitch(summary: str, sub: str) -> None:
    found = fidelity.soft_glitches(split_sentences(summary))
    assert sub in {f.sub for f in found}
    assert {f.severity for f in found} == {"soft"}


def test_check_adds_the_soft_novel_phrase_after_the_hard_rules() -> None:
    failures = fidelity.check("The film opened in June .", "The film opened in May.")
    assert [(f.rule, f.severity) for f in failures] == [("novel_phrase", "soft")]


def test_the_model_style_space_before_the_final_stop_is_not_a_glitch() -> None:
    assert fidelity.soft_glitches(split_sentences("The film opened in May and ran a year .")) == []


_DEFECT_SUMMARY, _DEFECT_SOURCE, _ = DEFECTIVE_SUMMARIES["swapped roles"]
_LABELS = [{"title": "Film", "label": "release", "verdict": "no", "role": "target"}]


def _dossier(summary: dict[str, Any] | None, state: str = "done") -> dict[str, Any]:
    return {
        "topic": {"title": "Film", "page_id": 7},
        "chunks": [
            {"id": "c1", "text": _DEFECT_SOURCE},
            {"id": "c2", "text": "A chunk the model did not read."},
        ],
        "sections": [
            {
                "id": "s1",
                "label": "Release history",
                "summary_state": state,
                "summary": summary,
                "heading_path": ["Release"],
            }
        ],
    }


def test_evaluate_rebuilds_the_source_and_attaches_the_label() -> None:
    summary = {"text": _DEFECT_SUMMARY, "input_chunk_ids": ["c1", "gone"]}
    (row,) = fidelity.evaluate([_dossier(summary)], _LABELS)
    assert (row.page_id, row.section_id, row.verdict, row.role) == (7, "s1", "no", "target")
    assert fidelity.hard(row)


@pytest.mark.parametrize(
    "summary",
    [
        None,
        {"text": _DEFECT_SUMMARY, "input_chunk_ids": None},
        {"text": _DEFECT_SUMMARY, "input_chunk_ids": []},
    ],
)
def test_evaluate_skips_a_summary_whose_source_is_unknown(summary: dict[str, Any] | None) -> None:
    assert fidelity.evaluate([_dossier(summary)], []) == []


def test_evaluate_skips_a_summary_that_is_not_done() -> None:
    summary = {"text": _DEFECT_SUMMARY, "input_chunk_ids": ["c1"]}
    assert fidelity.evaluate([_dossier(summary, state="pending")], []) == []


def test_rule_table_counts_a_rule_in_its_label_group_and_the_corpus() -> None:
    summary = {"text": _DEFECT_SUMMARY, "input_chunk_ids": ["c1"]}
    rows = fidelity.evaluate([_dossier(summary)], _LABELS)
    (entry,) = (e for e in fidelity.rule_table(rows) if e["rule"] == "roles")
    assert (entry["targets"], entry["no"], entry["yes"], entry["corpus"]) == (1, 1, 0, 1)
    assert (entry["targets_of"], entry["yes_of"], entry["corpus_of"]) == (1, 0, 1)
