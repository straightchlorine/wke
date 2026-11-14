"""number_tokens: the numbers a summary check compares with its source."""

from __future__ import annotations

from wke.core.text.numbers import number_tokens


def test_numbers_lose_thousands_commas_and_keep_decimals() -> None:
    assert number_tokens("In 1,250 BC, 3.5 million and 30 or 33 AD") == [
        "1250",
        "3.5",
        "30",
        "33",
    ]
