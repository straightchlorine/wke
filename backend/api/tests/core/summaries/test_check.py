"""The source check that decides whether a model summary may be shown."""

from __future__ import annotations

import pytest

from wke.core.summaries.check import check_summary

SOURCE = (
    "The Orange Order was founded in 1795 near Loughgall. The government backed the order "
    "from 1796 to thwart the United Irishmen. By 1,200 lodges existed in 1798."
)


def test_faithful_summary_passes() -> None:
    text = "The Orange Order was founded in 1795. The government backed it from 1796."
    assert check_summary(text, SOURCE) is None


def test_model_report_of_truncation_withholds() -> None:
    reason = check_summary("The Orange Order was founded in 1795.", SOURCE, truncated=True)
    assert reason == "the model output was cut off"


@pytest.mark.parametrize(
    "text",
    [
        "The Orange Order was founded in 1795 and the",
        "The Orange Order was founded in 1795, with",
        "The Orange Order was founded in 1795 ()",
    ],
)
def test_text_not_ending_at_a_sentence_end_withholds(text: str) -> None:
    assert check_summary(text, SOURCE) == "the text does not end at a sentence end"


def test_closing_quote_after_the_full_stop_is_a_sentence_end() -> None:
    assert (
        check_summary('It was called "the Order."', SOURCE + ' It was called "the Order."') is None
    )


@pytest.mark.parametrize(
    "text",
    [
        "The Orange Order was founded in 1795. See also Loughgall.",
        "The Orange Order was founded in 1795. Orange Order redirects here.",
        "The Orange Order was founded in 1795 (see the Loughgall article).",
        "This article is about the Orange Order.",
    ],
)
def test_text_pointing_to_another_page_withholds(text: str) -> None:
    assert check_summary(text, SOURCE) == "the text points to another page"


def test_name_absent_from_the_source_withholds() -> None:
    reason = check_summary("The Orange Order was formed by the United Irishman.", SOURCE)
    assert reason is not None and "Irishman" in reason


def test_name_comparison_ignores_case_and_possessive() -> None:
    assert check_summary("The government's order, the ORANGE ORDER, was backed.", SOURCE) is None


def test_sentence_opening_function_words_are_not_names() -> None:
    assert check_summary("However, the order grew. Later the government backed it.", SOURCE) is None


def test_number_absent_from_the_source_withholds() -> None:
    reason = check_summary("The Orange Order was founded in 1796 with 900 lodges.", SOURCE)
    assert reason is not None and "900" in reason


def test_numbers_compare_by_digits_not_separators() -> None:
    assert check_summary("There were 1200 lodges.", SOURCE) is None


def test_heading_year_counts_as_a_source_number() -> None:
    text = "The order grew in 1812."
    assert check_summary(text, SOURCE) is not None
    assert check_summary(text, SOURCE, heading="Spread (1812-1820)") is None


@pytest.mark.parametrize(
    ("text", "source", "title"),
    [
        (
            "The order was founded in 1795 near Loughgall.",
            "The order was founded in 1795 near Loughgall.",
            "Loughgall",
        ),
        (
            "The order began in 1795 as a political party.",
            "The order began in 1795 as a political movement.",
            "Art",
        ),
    ],
    ids=["title-in-the-source", "title-inside-another-word"],
)
def test_title_the_source_shares_or_the_text_does_not_name_passes(
    text: str, source: str, title: str
) -> None:
    assert check_summary(text, source, foreign_titles=[title]) is None


def test_title_of_another_article_not_in_the_source_withholds() -> None:
    reason = check_summary(
        "The order was founded in 1795. the Battle of the Diamond followed.",
        SOURCE + " Battle Diamond.",
        foreign_titles=["the Battle of the Diamond"],
    )
    assert reason == "the text names an article that is not in the source"
