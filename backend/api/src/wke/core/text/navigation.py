"""Detect text that sends the reader to another page."""

from __future__ import annotations

import re

# A sentence that matches is left out of a passage and makes a summary unfit
# to show: the text refers the reader nowhere but to its citation.
NAVIGATION_SENTENCE = re.compile(
    r"^(?:See(?: also)?(?: the article)?\b|Main articles?:|Further information:"
    r"|For (?:a (?:complete |full )?list|more (?:information|details))\b[^.]*,\s*see\b)"
)
NAVIGATION_ANYWHERE = re.compile(
    r"\b(?:See also|Main articles?|Further information|Not to be confused with)\b"
    r"|\bredirects? here\b|\bThis article is about\b"
    r"|\bFor (?:more|other) (?:information|details|uses)\b"
    r"|\bsee the\b[^.]{0,80}\b(?:article|page)\b"
    r"|\b(?:listed|shown|given|detailed|summari[sz]ed|presented)\b[^.]{0,40}\b(?:below|above)\b"
    r"|\b(?:Red|Blue|Green|Yellow|Orange|Purple|Grey|Gray|Pink|Brown|Black|White|Light|Dark)"
    r"\b[^.;]{0,30}\bdenotes?\b"
)


def points_elsewhere(text: str) -> bool:
    """Tell whether text sends the reader to another page.

    Args:
        text: a passage or summary.

    Returns:
        bool: True when a navigation phrase such as "See also", "Main
        article", "redirects here" or "see the ... article" occurs.
    """
    return bool(NAVIGATION_SENTENCE.match(text) or NAVIGATION_ANYWHERE.search(text))
