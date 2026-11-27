"""A 2000-token view may trade its weakest extra passages for table rows and list items."""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tests.factories.dossier import make_fixture_dossier, make_freshness, make_links
from tests.factories.packing import make_chunk, make_section
from tests.factories.repack import make_repack_dossier, structured_text
from tests.factories.synthetic import dossier_of
from wke.core import render
from wke.core.models import Chunk, ChunkKind, Dossier, DossierView
from wke.core.models.budgets import BudgetTokens
from wke.core.pack import pack
from wke.core.render import view as view_module
from wke.core.render.markdown import content_text
from wke.core.text.tokens import est_tokens

# Scores that leave only the passages a test names among the shown extra ones.
LOW = {f"S{n}:{j}": 0.2 for n in range(6) for j in (1, 2)}


def _build(dossier: Dossier, repack: bool, budget: BudgetTokens = 2000) -> DossierView:
    return render.build_view(
        dossier,
        budget,
        make_freshness(dossier),
        make_links(),
        False,
        lean=True,
        table_repack=repack,
    )


def _ids(view: DossierView) -> list[str]:
    return [chunk.id for chunk in view.chunks]


def _text(view: DossierView, cid: str) -> str:
    return next(chunk.text for chunk in view.chunks if chunk.id == cid)


def _units(view: DossierView, cid: str) -> int:
    """Count the data rows of a table or the top-level items of a list the view shows."""
    chunk = next(c for c in view.chunks if c.id == cid)
    lines = chunk.text.split("\n")
    if chunk.kind == "table":
        return sum(1 for line in lines if line.startswith("|")) - 2
    return sum(1 for line in lines if line.startswith("- "))


def test_the_repack_is_off_unless_asked_for() -> None:
    dossier = make_repack_dossier("table", 4)
    plain = render.build_view(
        dossier, 2000, make_freshness(dossier), make_links(), False, lean=True
    )
    assert plain == _build(dossier, False)
    assert plain != _build(dossier, True)


def test_a_table_the_pack_left_out_enters_when_a_passage_leaves() -> None:
    dossier = make_repack_dossier("table", 4)
    base, repacked = _build(dossier, False), _build(dossier, True)
    assert "T:table0" not in _ids(base)
    assert _text(repacked, "T:table0") == structured_text("table", 4, 30)
    assert set(_ids(repacked)) - {"T:table0"} < set(_ids(base))


def test_a_table_shown_cut_grows_when_a_passage_leaves() -> None:
    dossier = make_repack_dossier("table", 12, 30, 350)
    base, repacked = _build(dossier, False), _build(dossier, True)
    assert "(12 rows; 3 shown)" in _text(base, "T:table0")
    assert _units(repacked, "T:table0") > 3


def test_a_list_the_pack_left_out_may_enter() -> None:
    dossier = make_repack_dossier("list", 12, 50)
    base, repacked = _build(dossier, False), _build(dossier, True)
    assert "T:list0" not in _ids(base)
    assert _units(repacked, "T:list0") > 0


def test_a_list_the_pack_shows_keeps_exactly_its_items_while_a_table_grows() -> None:
    dossier = make_repack_dossier("table", 12, 30, 250, held_list=True)
    base, repacked = _build(dossier, False), _build(dossier, True)
    assert "(40 items; 12 shown)" in _text(base, "S5:list0")
    assert _text(repacked, "S5:list0") == _text(base, "S5:list0")
    assert "S5:list0" in repacked.budget.shortened_chunk_ids
    assert "T:table0" not in _ids(base)
    assert _text(repacked, "T:table0") == structured_text("table", 12, 30)


def test_a_whole_list_the_pack_shows_is_not_cut_when_room_is_short() -> None:
    dossier = make_repack_dossier("table", 12, 30, 250)
    whole = structured_text("list", 5, 12)
    chunk = make_chunk("S5:list0", ["S5"], 99, 1, 0.0, kind="list")
    chunk = chunk.model_copy(update={"text": whole, "est_tokens": est_tokens(whole)})
    sections = [
        s.model_copy(update={"chunk_ids": [*s.chunk_ids, chunk.id]}) if s.id == "S5" else s
        for s in dossier.sections
    ]
    dossier = dossier.model_copy(update={"sections": sections, "chunks": [*dossier.chunks, chunk]})
    base, repacked = _build(dossier, False), _build(dossier, True)
    assert _text(base, "S5:list0") == whole
    assert _text(repacked, "S5:list0") == whole


def test_the_smallest_number_of_passages_leaves_when_more_would_show_no_more() -> None:
    dossier = make_repack_dossier("table", 4)
    base, repacked = _build(dossier, False), _build(dossier, True)
    gone = set(_ids(base)) - set(_ids(repacked))
    assert gone == {"S5:2"}
    assert "S0:2" in _ids(repacked)


@pytest.mark.parametrize(
    ("early", "late", "leaves"),
    [
        pytest.param(0.5, 0.6, "S0:2", id="the-lower-score-leaves-though-it-comes-first"),
        pytest.param(0.6, 0.5, "S5:2", id="the-lower-score-leaves-though-it-comes-last"),
        pytest.param(0.7, 0.7, "S5:2", id="on-a-tie-the-later-passage-leaves"),
    ],
)
def test_the_passage_with_the_lowest_score_leaves_first(
    early: float, late: float, leaves: str
) -> None:
    scores = {**LOW, "S0:2": early, "S5:2": late}
    dossier = make_repack_dossier("table", 4, relevance=scores)
    base, repacked = _build(dossier, False), _build(dossier, True)
    assert {"S0:2", "S5:2"} <= set(_ids(base))
    assert set(_ids(base)) - set(_ids(repacked)) == {leaves}


def test_lead_passages_and_openers_never_leave_however_low_their_score() -> None:
    scores = {"l0": 0.0, **{f"S{n}:0": 0.0 for n in range(6)}}
    dossier = make_repack_dossier("table", 4, relevance=scores)
    base, repacked = _build(dossier, False), _build(dossier, True)
    assert "T:table0" in _ids(repacked)
    kept = {"l0", "S0:0", "S1:0", "S3:0", "S4:0", "S5:0", "T:0"}
    assert kept <= set(_ids(base)) and kept <= set(_ids(repacked))
    # S2:0 was packed as an ordinary passage here, not as its section's opener.
    assert "S2:0" in _ids(base) and "S2:0" not in _ids(repacked)


def _everything_fits() -> Dossier:
    table = make_chunk("s1:table0", ["Data"], 2, 1, 0.5, kind="table")
    text = structured_text("table", 3, 5)
    table = table.model_copy(update={"text": text, "est_tokens": est_tokens(text)})
    return dossier_of(
        [make_section("s0", [], ["l0"]), make_section("s1", ["Data"], ["s1:0", "s1:1", table.id])],
        [
            make_chunk("l0", [], 0, 100, 1.0),
            make_chunk("s1:0", ["Data"], 1, 100, 0.5),
            make_chunk("s1:1", ["Data"], 2, 100, 0.4),
            table,
        ],
    )


@pytest.mark.parametrize(
    "dossier",
    [
        pytest.param(make_repack_dossier(None), id="no-table-or-list"),
        pytest.param(_everything_fits(), id="everything-fits"),
        pytest.param(make_fixture_dossier(), id="the-fixture-dossier"),
    ],
)
def test_with_nothing_to_gain_the_view_is_the_plain_pack(dossier: Dossier) -> None:
    assert _build(dossier, True) == _build(dossier, False)


def test_a_dossier_with_a_table_and_nothing_to_drop_is_the_plain_pack() -> None:
    lead = make_chunk("l0", [], 0, 100, 1.0)
    table = make_chunk("s1:table0", ["Data"], 2, 1, 0.5, kind="table")
    text = structured_text("table", 400, 12)
    table = table.model_copy(update={"text": text, "est_tokens": est_tokens(text)})
    dossier = dossier_of(
        [make_section("s0", [], ["l0"]), make_section("s1", ["Data"], ["s1:0", table.id])],
        [lead, make_chunk("s1:0", ["Data"], 1, 100, 0.5), table],
    )
    assert _build(dossier, True) == _build(dossier, False)


@pytest.mark.parametrize("budget", [8000, 32000])
def test_the_larger_budgets_are_never_repacked(
    budget: BudgetTokens, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("repacked")

    monkeypatch.setattr("wke.core.render.view._repack_for_tables", refuse)
    dossier = make_repack_dossier("table", 400, 30)
    assert _build(dossier, True, budget) == _build(dossier, False, budget)


def test_the_counts_of_the_view_are_those_of_the_chosen_pack() -> None:
    dossier = make_repack_dossier("table", 4)
    base = _build(dossier, False)
    repacked = _build(dossier, True)
    content, _ = content_text(repacked, False, notes=False)
    assert repacked.budget.used_est_tokens == est_tokens(content) <= 2000
    assert sorted(repacked.budget.included_chunk_ids) == sorted(_ids(repacked))
    assert repacked.budget.omitted_chunks == len(dossier.chunks) - len(repacked.chunks)
    assert repacked.budget.used_est_tokens != base.budget.used_est_tokens


def test_the_budget_line_of_the_markdown_counts_the_chosen_pack() -> None:
    dossier = make_repack_dossier("table", 4)
    view = render.build_view(
        dossier, 2000, make_freshness(dossier), make_links(), False, table_repack=True
    )
    text = render.render_markdown(
        view, False, False, frozenset({"dossier", "metadata"}), lean=False
    )
    prose = sum(1 for chunk in view.chunks if chunk.kind == "prose")
    total = sum(1 for chunk in dossier.chunks if chunk.kind == "prose")
    assert f"Budget 2,000 tokens: {prose} of {total} passages" in text


@st.composite
def _dossiers(draw: st.DrawFn) -> Dossier:
    kind: ChunkKind | None = draw(st.sampled_from([None, "table", "list"]))
    return make_repack_dossier(
        kind,
        count=draw(st.integers(min_value=1, max_value=40)),
        words=draw(st.integers(min_value=1, max_value=80)),
        extra_tokens=draw(st.integers(min_value=50, max_value=500)),
        relevance={
            f"S{n}:{j}": draw(st.floats(min_value=0.0, max_value=1.0))
            for n in range(6)
            for j in (0, 1, 2)
        },
        held_list=draw(st.booleans()),
    )


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(dossier=_dossiers())
def test_the_repacked_view_fits_the_budget_and_shows_no_fewer_rows_and_items(
    dossier: Dossier,
) -> None:
    base, repacked = _build(dossier, False), _build(dossier, True)
    content, _ = content_text(repacked, False, notes=False)
    assert repacked.budget.used_est_tokens == est_tokens(content) <= 2000

    def shown(view: DossierView) -> int:
        return sum(_units(view, c.id) for c in view.chunks if c.kind in ("table", "list"))

    held = {c.id for c in base.chunks if c.kind == "list"}
    assert shown(repacked) >= shown(base)
    for cid in held & set(_ids(repacked)):
        assert _text(repacked, cid) == _text(base, cid)


def _recording_assemble(monkeypatch: pytest.MonkeyPatch) -> list[tuple[tuple, dict]]:
    """Replace assemble_view by a wrapper that records each call and marks the view it returns."""
    calls: list[tuple[tuple, dict]] = []
    real = render.view.assemble_view

    def recording(*args, **kwargs):
        calls.append((args, kwargs))
        view = real(*args, **kwargs)
        return view.model_copy(
            update={"freshness": view.freshness.model_copy(update={"edits_since": 777})}
        )

    monkeypatch.setattr(render.view, "assemble_view", recording)
    return calls


@pytest.mark.parametrize("budget", [2000, 8000, 32000])
def test_the_pack_without_the_repack_goes_through_assemble_view(
    monkeypatch: pytest.MonkeyPatch, budget: BudgetTokens
) -> None:
    dossier = make_repack_dossier("table", 4)
    calls = _recording_assemble(monkeypatch)
    view = _build(dossier, False, budget)
    assert calls
    assert view.freshness.edits_since == 777
    for args, kwargs in calls:
        assert args[:2] == (dossier, budget)
        assert args[4] is False
        assert kwargs == {"facts": False}


def test_the_baseline_pack_of_the_repack_goes_through_assemble_view(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A dossier without tables or lists gains nothing, so the baseline view is the answer.
    dossier = make_fixture_dossier()
    calls = _recording_assemble(monkeypatch)
    view = _build(dossier, True)
    assert calls
    assert view.freshness.edits_since == 777


def test_without_the_repack_build_view_packs_through_the_assembler_and_nothing_else(
    monkeypatch,
) -> None:
    dossier = make_repack_dossier("table", 4)
    assembled: list[int] = []
    packed: list[int] = []
    assemble_view = view_module.assemble_view
    pack = view_module.pack

    def counting_assemble(*args, **kwargs):
        assembled.append(1)
        return assemble_view(*args, **kwargs)

    def counting_pack(*args, **kwargs):
        packed.append(1)
        return pack(*args, **kwargs)

    monkeypatch.setattr(view_module, "assemble_view", counting_assemble)
    monkeypatch.setattr(view_module, "pack", counting_pack)
    _build(dossier, False)
    assert assembled
    assert len(packed) == len(assembled)


def _table(cid: str, section: str, order: int, rows: int) -> Chunk:
    text = structured_text("table", rows, 5)
    chunk = make_chunk(cid, [section], order, 1, 0.0, kind="table")
    return chunk.model_copy(update={"text": text, "est_tokens": est_tokens(text)})


def test_a_table_header_and_separator_are_not_rows_when_two_tables_compete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The pack shows table A whole (8 rows). The one repack shows A cut to 5 rows and B with 3:
    # 8 rows against 8, so the plain pack stays. A header counted as a row would tip it over.
    without = make_repack_dossier(None)
    plain = _build(without, False)
    full_a, cut_a = _table("A", "S0", 90, 8), _table("A", "S0", 90, 5)
    table_b = _table("B", "S1", 91, 3)
    dossier = without.model_copy(update={"chunks": [*without.chunks, full_a, table_b]})
    baseline = plain.model_copy(update={"chunks": [*plain.chunks, full_a]})
    repacked = plain.model_copy(update={"chunks": [*plain.chunks, cut_a, table_b]})
    calls: list[int] = []

    def fit(*args: object, **kwargs: object) -> tuple[DossierView, int]:
        calls.append(1)
        return repacked, 0

    monkeypatch.setattr(view_module, "_fit_view", fit)
    chosen = view_module._repack_for_tables(
        dossier, baseline, 0, plain.freshness, plain.links, False, True, True
    )
    assert calls
    assert chosen is baseline


def test_the_rows_and_items_counted_are_the_data_rows_and_the_top_level_items() -> None:
    table = _table("A", "S0", 90, 5)
    cut = table.model_copy(update={"text": table.text + "\n(9 rows; 5 shown)"})
    items = "- one\n  - nested\n- two\n(4 items; 2 shown)"
    list_chunk = make_chunk("L", ["S0"], 92, 1, 0.0, kind="list")
    list_chunk = list_chunk.model_copy(update={"text": items})
    count = view_module._structured_units
    assert count([table], {}) == 5
    assert count([cut], {}) == 5
    assert count([list_chunk], {}) == 2
    assert count([list_chunk], {"L": items}) == 0
    assert count([make_chunk("p", ["S0"], 1, 3, 0.5)], {}) == 0


class _Counts:
    """Count the fits and the packs of one build_view call."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.fits = 0
        self.packs = 0
        fit, packer = view_module._fit_view, view_module.pack

        def counting_fit(*args: object, **kwargs: object) -> tuple[DossierView, int]:
            self.fits += 1
            return fit(*args, **kwargs)  # type: ignore[arg-type]

        def counting_pack(*args: object, **kwargs: object) -> object:
            self.packs += 1
            return packer(*args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(view_module, "_fit_view", counting_fit)
        monkeypatch.setattr(view_module, "pack", counting_pack)


def _unbounded(dossier: Dossier) -> DossierView:
    """Repack by the plain rule: every extra tried, no early stop, no skip."""
    freshness, links = make_freshness(dossier), make_links()
    base, reserve = view_module._fit_view(dossier, 2000, freshness, links, False, True, True)
    openers = pack(dossier, 2000, include_summaries=False, reserve=reserve, facts=False).opener_ids
    by_id = {c.id: c for c in dossier.chunks}
    shown = [c.id for c in base.chunks if c.kind == "prose"]
    extras = sorted(
        (by_id[i] for i in shown if by_id[i].heading_path and i not in openers),
        key=lambda c: (c.relevance, -c.order),
    )
    held = {c.id: c.text for c in base.chunks if c.kind == "list"}
    best, best_gain = base, view_module._structured_units(base.chunks, held)
    for count in range(1, len(extras) + 1):
        allowed = frozenset(shown) - {c.id for c in extras[:count]}
        view, _ = view_module._fit_view(
            dossier, 2000, freshness, links, False, True, True, allowed, held
        )
        gain = view_module._structured_units(view.chunks, held)
        if gain > best_gain:
            best, best_gain = view, gain
    return best


def _many_extras() -> Dossier:
    """A lead, three sections of many short passages and a table too long to ever show whole."""
    chunks = [make_chunk("l0", [], 0, 100, 1.0)]
    sections = [make_section("s0", [], ["l0"])]
    order = 1
    for name in ("S0", "S1", "S2", "T"):
        ids: list[str] = []
        for n in range(11 if name != "T" else 1):
            cid = f"{name}:{n}"
            chunks.append(make_chunk(cid, [name], order, 30, 0.9 if n == 0 else 0.2 + n / 40))
            ids.append(cid)
            order += 1
        if name == "T":
            chunks.append(_table("T:table0", "T", order, 400))
            ids.append("T:table0")
        sections.append(make_section(name, [name], ids))
    return dossier_of(sections, chunks)


def test_no_repack_is_tried_when_the_pack_already_shows_every_row_and_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for dossier in (make_repack_dossier(None), _everything_fits()):
        counts = _Counts(monkeypatch)
        view = _build(dossier, True)
        assert (counts.fits, counts.packs) == (1, 1)
        assert view == _unbounded(dossier)


def test_the_tries_stop_at_the_first_pack_that_shows_every_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dossier = make_repack_dossier("table", 4)
    expected = _unbounded(dossier)
    counts = _Counts(monkeypatch)
    view = _build(dossier, True)
    assert view == expected
    assert _text(view, "T:table0") == structured_text("table", 4, 30)
    # The plain pack, one opener pack and one try: the table is whole at the first.
    assert (counts.fits, counts.packs) == (2, 3)
    monkeypatch.undo()
    assert _build(dossier, False) != view


def test_at_most_twelve_extra_passages_are_tried(monkeypatch: pytest.MonkeyPatch) -> None:
    dossier = _many_extras()
    counts = _Counts(monkeypatch)
    view = _build(dossier, True)
    assert view_module.MAX_REPACK_EXTRAS == 12
    assert counts.fits == 1 + 12
    content, _ = content_text(view, False, notes=False)
    assert est_tokens(content) <= 2000
    # Without the bound the same dossier takes many more tries.
    monkeypatch.setattr(view_module, "MAX_REPACK_EXTRAS", 10**6)
    more = _Counts(monkeypatch)
    _build(dossier, True)
    assert more.fits > 1 + 12
