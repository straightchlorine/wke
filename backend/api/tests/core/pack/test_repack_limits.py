"""The limits a repack sets on the packer: the passages allowed and the lists carried over."""

from __future__ import annotations

from tests.factories.repack import make_repack_dossier, structured_text
from wke.core import pack
from wke.core.pack.state import NO_ROOM, Packer, PackState
from wke.core.text.tokens import est_tokens


def test_only_the_allowed_passages_are_placed() -> None:
    dossier = make_repack_dossier(None)
    allowed = frozenset({"l0", "S0:0", "S1:0", "S1:2"})
    packed = pack.pack(dossier, 2000, allowed_prose=allowed)
    assert set(packed.budget.included_chunk_ids) == allowed


def test_a_passage_outside_the_allowed_ones_has_no_room() -> None:
    dossier = make_repack_dossier(None)
    packer = Packer(dossier, 2000, PackState(used=0), False, allowed_prose=frozenset({"l0"}))
    by_id = {c.id: c for c in dossier.chunks}
    assert packer.chunk_room(by_id["S0:2"]) == NO_ROOM
    assert not packer.fits_chunk(by_id["S0:2"])
    assert packer.chunk_room(by_id["l0"]) > 0


def test_a_table_is_not_held_back_by_the_allowed_passages() -> None:
    dossier = make_repack_dossier("table", 4)
    packed = pack.pack(dossier, 2000, allowed_prose=frozenset({"l0", "S0:0"}))
    assert packed.chunk_texts["T:table0"] == structured_text("table", 4, 30)


def test_a_held_list_is_placed_as_given_and_left_cut_though_room_remains() -> None:
    dossier = make_repack_dossier(None, held_list=True)
    chunk = next(c for c in dossier.chunks if c.id == "S5:list0")
    held = "\n".join([*chunk.text.split("\n")[:3], "(40 items; 3 shown)"])
    packed = pack.pack(
        dossier, 2000, allowed_prose=frozenset({"l0", "S5:0"}), held_lists={chunk.id: held}
    )
    assert packed.chunk_texts[chunk.id] == held
    assert chunk.id in packed.budget.shortened_chunk_ids
    free = 2000 - packed.budget.used_est_tokens
    assert free > est_tokens(chunk.text.split("\n")[3])


def test_a_held_list_shown_whole_is_not_marked_cut() -> None:
    dossier = make_repack_dossier(None, held_list=True)
    chunk = next(c for c in dossier.chunks if c.id == "S5:list0")
    packed = pack.pack(
        dossier, 2000, allowed_prose=frozenset({"l0", "S5:0"}), held_lists={chunk.id: chunk.text}
    )
    assert packed.chunk_texts[chunk.id] == chunk.text
    assert chunk.id not in packed.budget.shortened_chunk_ids


def test_a_held_list_is_placed_after_the_openers_and_before_any_table() -> None:
    dossier = make_repack_dossier("table", 12, 30, held_list=True)
    chunk = next(c for c in dossier.chunks if c.id == "S5:list0")
    allowed = frozenset({"l0", "S0:0", "S5:0", "T:0"})
    packed = pack.pack(dossier, 2000, allowed_prose=allowed, held_lists={chunk.id: chunk.text})
    order = packed.budget.included_chunk_ids
    assert order.index("S5:0") < order.index(chunk.id) < order.index("T:table0")


def test_the_pack_names_the_passages_it_placed_as_openers() -> None:
    dossier = make_repack_dossier("table", 4)
    packed = pack.pack(dossier, 2000)
    shown = set(packed.budget.included_chunk_ids)
    assert packed.opener_ids <= shown
    assert {"S0:0", "S1:0", "S5:0"} <= packed.opener_ids
    assert "l0" not in packed.opener_ids
    assert not packed.opener_ids & {"S0:2", "S5:2"}
