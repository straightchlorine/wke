"""normalize_title: the one form a title takes before a Wikimedia call or a cache key."""

from __future__ import annotations

import pytest

from wke.core.errors import ApiException
from wke.core.titles import MAX_TITLE_LENGTH, normalize_title


@pytest.mark.parametrize(
    ("raw", "title"),
    [
        ("Gospel_of_Mark", "Gospel of Mark"),
        ("  jesus ", "Jesus"),
        ("e\u0301glise", "\u00c9glise"),
        ("x" * MAX_TITLE_LENGTH, "X" + "x" * (MAX_TITLE_LENGTH - 1)),
    ],
    ids=["underscores", "trimmed-and-capitalised", "nfc", "longest"],
)
def test_title_is_normalised(raw: str, title: str) -> None:
    assert normalize_title(raw) == title


@pytest.mark.parametrize(
    "raw",
    ["", "   ", "x" * (MAX_TITLE_LENGTH + 1), "A#B", "A|B", "A[B]", "A{B}", "A<B>", "A\x07B"],
    ids=["empty", "blank", "too-long", "hash", "pipe", "brackets", "braces", "angle", "control"],
)
def test_invalid_title_is_a_422(raw: str) -> None:
    with pytest.raises(ApiException) as caught:
        normalize_title(raw)
    assert (caught.value.status_code, caught.value.code) == (422, "validation_error")
