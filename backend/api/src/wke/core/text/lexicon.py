"""Closed-class word lists: the summary checks compare by them, the packer reads openings."""

from __future__ import annotations

# Articles, pronouns, prepositions and conjunctions both lists hold.
COMMON_WORDS = frozenset(
    (
        "a about after all also an and as at before both but by during each for from "
        "he her here his how if in into it its more most no nor not on once only or "
        "other our over she since so some such that the their then there these they "
        "this those under until we what when where which while who whom whose why "
        "with without yet"
    ).split()
)

# Adverbs, numerals and connectives that only open a sentence capitalised.
_OPENER_ONLY = frozenset(
    (
        "according across against although among another around because between "
        "currently despite even eventually finally first five following four "
        "furthermore however initially instead last later many meanwhile moreover "
        "next now one originally overall previously second several soon still "
        "subsequently therefore third though three through thus today two upon "
        "whereas within"
    ).split()
)

# Auxiliary verbs and other fillers that carry no content in a comparison.
_AUXILIARY_ONLY = frozenset(
    (
        "again am any are be been being can could did do does done down further had "
        "has have having him i is just may me might must my of off onto out own s "
        "same shall should t than them to up us very was were will would you"
    ).split()
)

# Sentence openers that are capitalised only because they open a sentence.
FUNCTION_WORDS = COMMON_WORDS | _OPENER_ONLY
# Words left out when summary and source are compared by content.
STOPWORDS = COMMON_WORDS | _AUXILIARY_ONLY
# Leading words that may precede a name without being part of it.
LEAD_FUNCTION = frozenset(
    "in on at by for from with after before during when while as the a an".split()
)
