"""clean_text: the one normalisation every prose, list and table string goes through."""

from __future__ import annotations

import pytest

from wke.core.text.clean import clean_text


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("Jesus\u200b of\u00ad Nazareth", "Jesus of Nazareth"),
        ("a\u2060b\ufeffc\x07d", "abcd"),
        ("a\u200cb\u200dc\x01d\x1fe\x7ff", "abcdef"),
        ("  two\n\tlines  ", "two lines"),
        ("Baha\u0301\u02bc\u00ed", "Bah\u00e1\u02bc\u00ed"),
    ],
    ids=[
        "zero-width-and-soft-hyphen",
        "joiners-bom-and-controls",
        "non-joiners-c0-and-delete",
        "whitespace",
        "nfc",
    ],
)
def test_clean_text(raw: str, clean: str) -> None:
    assert clean_text(raw) == clean
