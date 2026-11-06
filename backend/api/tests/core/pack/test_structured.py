"""Tables and lists at pack time: whole when they fit, cut at row boundaries when not."""

from __future__ import annotations

from tests.factories.packing import make_chunk, make_section
from tests.factories.synthetic import dossier_of, list_chunk_text, table_chunk_text
from wke.core import pack
from wke.core.models import ChunkKind, Dossier
from wke.core.pack.state import Packer, PackState
from wke.core.pack.structured import STRUCTURED_SHARE, extend_structured, place_structured
from wke.core.text.tokens import est_tokens


def _structured_dossier(kind: ChunkKind, text: str, prose_tokens: int = 150) -> Dossier:
    sections = [
        make_section("s0", [], ["l0"]),
        make_section("s1", ["Data"], ["s1:0", f"s1:{kind}0"]),
    ]
    chunks = [make_chunk("l0", [], 0, 80, 1.0), make_chunk("s1:0", ["Data"], 1, prose_tokens, 0.5)]
    chunk = make_chunk(f"s1:{kind}0", ["Data"], 2, 1, 0.5, kind=kind)
    chunks.append(chunk.model_copy(update={"text": text, "est_tokens": est_tokens(text)}))
    return dossier_of(sections, chunks)


def test_a_table_takes_at_most_its_share_of_the_step_budget_before_the_leftover_pass() -> None:
    dossier = _structured_dossier("table", table_chunk_text(400))
    packer = Packer(dossier, 2000, PackState(used=0), False)
    place_structured(packer)
    text = packer.state.texts["s1:table0"]
    assert est_tokens(text) <= STRUCTURED_SHARE * 2000
    assert "s1:table0" in packer.state.shortened
    assert "(400 rows; " in text


def test_a_larger_budget_shows_more_rows_and_a_normal_table_whole() -> None:
    dossier = _structured_dossier("table", table_chunk_text(400))
    small = pack.pack(dossier, 2000).chunk_texts["s1:table0"]
    mid = pack.pack(dossier, 8000)
    assert len(mid.chunk_texts["s1:table0"]) > len(small)
    assert "s1:table0" not in mid.budget.shortened_chunk_ids
    assert mid.chunk_texts["s1:table0"] == table_chunk_text(400)


def test_a_table_does_not_crowd_out_the_opening_passage_at_2k() -> None:
    dossier = _structured_dossier("table", table_chunk_text(400), prose_tokens=900)
    packed = pack.pack(dossier, 2000)
    assert "s1:0" in packed.budget.included_chunk_ids


def test_a_list_is_packed_like_a_table_and_notes_its_items() -> None:
    dossier = _structured_dossier("list", list_chunk_text(400))
    packed = pack.pack(dossier, 2000)
    text = packed.chunk_texts["s1:list0"]
    assert "s1:list0" in packed.budget.shortened_chunk_ids
    assert text.splitlines()[-1].startswith("(400 items; ")
    whole = pack.pack(dossier, 32000)
    assert whole.chunk_texts["s1:list0"] == list_chunk_text(400)


def test_a_cut_table_takes_the_room_the_other_passes_left() -> None:
    dossier = _structured_dossier("table", table_chunk_text(400), prose_tokens=100)
    packed = pack.pack(dossier, 2000)
    cap = int(STRUCTURED_SHARE * 2000)
    text = packed.chunk_texts["s1:table0"]
    assert est_tokens(text) > cap
    assert packed.budget.used_est_tokens <= 2000
    assert text.splitlines()[-1].startswith("(400 rows;")
    assert "s1:table0" in packed.budget.shortened_chunk_ids


def test_the_extension_respects_the_reserve() -> None:
    dossier = _structured_dossier("table", table_chunk_text(400), prose_tokens=100)
    plain = pack.pack(dossier, 2000)
    held = pack.pack(dossier, 2000, reserve=400)
    assert est_tokens(held.chunk_texts["s1:table0"]) < est_tokens(plain.chunk_texts["s1:table0"])
    assert held.budget.used_est_tokens <= 2000 - 400


def test_a_table_cut_at_a_small_step_is_extended_only_to_the_larger_steps_share() -> None:
    dossier = _structured_dossier("table", table_chunk_text(400), prose_tokens=100)
    small = Packer(dossier, 2000, PackState(used=0), False)
    place_structured(small)
    packer = Packer(dossier, 8000, small.state, False)
    extend_structured(packer)
    text = packer.state.texts["s1:table0"]
    assert est_tokens(text) > STRUCTURED_SHARE * 2000
    assert est_tokens(text) <= STRUCTURED_SHARE * 8000
