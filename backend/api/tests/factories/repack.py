"""A synthetic dossier at 2000 tokens whose pack leaves a table or list out or cut short."""

from __future__ import annotations

from tests.factories.packing import make_chunk, make_section
from tests.factories.synthetic import dossier_of
from wke.core.models import Chunk, ChunkKind, Dossier
from wke.core.text.tokens import est_tokens

BIG_SECTIONS = 6
HELD_LIST_ITEMS = 40


def structured_text(kind: ChunkKind, count: int, words: int) -> str:
    """Build the text of a table or list chunk whose rows or items are words long.

    Args:
        kind: "table" or "list".
        count: how many data rows or top-level items.
        words: how many words one row or item holds.

    Returns:
        str: the chunk text, without a count note.
    """
    cell = " ".join(["word"] * words)
    if kind == "table":
        head = ["Records", "| Year | Note |", "| --- | --- |"]
        return "\n".join(head + [f"| {2000 + n} | {cell} |" for n in range(count)])
    return "\n".join(f"- Item {n} {cell}" for n in range(count))


def _structured_chunk(cid: str, path: list[str], order: int, kind: ChunkKind, text: str) -> Chunk:
    chunk = make_chunk(cid, path, order, 1, 0.0, kind=kind)
    return chunk.model_copy(update={"text": text, "est_tokens": est_tokens(text)})


def make_repack_dossier(
    kind: ChunkKind | None = "table",
    count: int = 4,
    words: int = 30,
    extra_tokens: int = 250,
    relevance: dict[str, float] | None = None,
    held_list: bool = False,
) -> Dossier:
    """Build a dossier of a lead, six large sections and a small one holding a table or list.

    Every large section "S0".."S5" has an opening passage of 200 tokens and two more passages
    "S0:1", "S0:2" of extra_tokens each, scored 0.65 and 0.7. The small section "T" sits in the
    middle of the article and ranks last, so its table "T:table0" or list "T:list0" is
    placed late, if at all.

    Args:
        kind: the kind of the chunk in "T", or None for none.
        count: its data rows or items.
        words: the words of each of its rows or items.
        extra_tokens: the size of the passages that follow each opening one.
        relevance: scores that replace the default ones, by chunk id.
        held_list: whether "S5" also holds a long list "S5:list0", which the pack shows cut.

    Returns:
        Dossier: the dossier, packed at 2000 by the tests.
    """
    scores = relevance or {}
    chunks = [make_chunk("l0", [], 0, 100, scores.get("l0", 1.0))]
    sections = [make_section("s0", [], ["l0"])]
    names = [f"S{n}" for n in range(BIG_SECTIONS)]
    if kind is not None:
        names.insert(BIG_SECTIONS // 2, "T")
    order = 1
    for name in names:
        ids: list[str] = []
        if name == "T":
            chunks.append(make_chunk("T:0", ["T"], order, 40, scores.get("T:0", 0.1)))
            ids.append("T:0")
            order += 1
            assert kind is not None
            text = structured_text(kind, count, words)
            chunks.append(_structured_chunk(f"T:{kind}0", ["T"], order, kind, text))
            ids.append(f"T:{kind}0")
            order += 1
        else:
            for n, tokens, default in (
                (0, 200, 0.9),
                (1, extra_tokens, 0.65),
                (2, extra_tokens, 0.7),
            ):
                cid = f"{name}:{n}"
                chunks.append(make_chunk(cid, [name], order, tokens, scores.get(cid, default)))
                ids.append(cid)
                order += 1
            if held_list and name == "S5":
                text = structured_text("list", HELD_LIST_ITEMS, 12)
                chunks.append(_structured_chunk("S5:list0", [name], order, "list", text))
                ids.append("S5:list0")
                order += 1
        sections.append(make_section(name, [name], ids))
    return dossier_of(sections, chunks)
