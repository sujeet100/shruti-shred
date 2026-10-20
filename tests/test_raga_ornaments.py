"""
Tests for RAGA-SPECIFIC ornaments (2026-10-13, the Bageshree alap of fusion_20261013_081705): its
three held komal Ga swung up to shuddha Ga (+98 cents) and turned there ~250 ms — the one andolan
depth rule (half the gap to the neighbour) was microtonal for Darbari's semitone neighbours and a
foreign swara for Bageshree's whole-tone one. Code stamped the sway on every held Ga, whatever the
phrase. These pin the fix per raga: where a sway turns, which ornament each phrase gets, that a
glide may cross a foreign pitch but never rest on one, and that Darbari and the ragas without an
andolan play exactly as before. Pure, no LLM.

Runs as a script (`uv run python tests/test_raga_ornaments.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from crew.contracts import (  # noqa: E402
    ArrangementDraft,
    CompositionBrief,
    Note,
    Section,
    SectionKind,
    build_arrangement,
)
from crew.expression import ANDOLAN_SHALLOW_ST, andolan_turn_st, express_section  # noqa: E402
from gestures import (  # noqa: E402
    GA_MA_LOOP,
    GA_MA_RELEASE,
    RELEASE,
    Gesture,
    GestureRule,
    check_gestures,
    gesture_for,
    gesture_path,
)
from ornament_audit import audit_midi  # noqa: E402
from raga import ANDOLAN_TOWARD, RAGAS, SWARAS  # noqa: E402
from render import _wheel, build_midi, path_wheel  # noqa: E402

_SA = 62


def _arr(raga: str, role: str, kind: SectionKind, bpm: int):
    section = Section(kind=kind, bars=4, layers=["lead", "drone"], foreground="lead",
                      form_role=role)
    draft = ArrangementDraft(raga=raga, subgenre="doom", tala="teentaal", bpm=bpm,
                             motif=["S"], sections=[section])
    return build_arrangement(draft, CompositionBrief())


def _alap(notes: list[Note], raga: str, bpm: int = 120) -> list[Note]:
    arr = _arr(raga, "intro", SectionKind.ALAAP, bpm)
    return express_section(notes, [], arr.sections[0], arr)[0]


def _gat(notes: list[Note], raga: str, bpm: int = 120) -> list[Note]:
    arr = _arr(raga, "mukhada", SectionKind.MELODY, bpm)
    return express_section(notes, [], arr.sections[0], arr)[0]


def _n(swara: str, start: float, dur: float, oct: int = 0, andolan: bool | None = None) -> Note:
    return Note(swara=swara, oct=oct, start=start, dur=dur, vel=86, andolan=andolan)


def _audit(raga: str, notes: list[Note], bpm: int = 120) -> set[str]:
    comp = {"raga": raga, "sa": _SA, "bpm": bpm,
            "tala": {"name": "teentaal", "beats_per_bar": 16},
            "layers": [{"role": "lead", "instrument": "sitar", "program": 104, "channel": 2,
                        "notes": [n.model_dump(exclude_none=True) for n in notes]}]}
    path = os.path.join(tempfile.mkdtemp(), "ornaments.mid")
    build_midi(comp, path)
    return {f.kind for f in audit_midi(path, raga=raga, sa=_SA) if f.channel == 2}


def _owned(raga: str) -> set[int]:
    return {SWARAS[sw] % 12 for sw in RAGAS[raga]["allowed"]}


# The opening alap of fusion_20261013_081705_bageshree, as placed (andolan flagged by lead
# placement on every held Ga), before expression.
_BAGESHREE_OPENING = [
    _n("S", 2, 2), _n("n", 4, 1, -1), _n("D", 5, 2, -1), _n("n", 7, 1, -1), _n("S", 8, 3),
    _n("g", 13, 2, andolan=True), _n("m", 15, 4), _n("m", 19, 1),
    _n("g", 20, 2, andolan=True), _n("R", 22, 1), _n("S", 23, 3),
    _n("S", 28, 1), _n("g", 29, 1, andolan=True), _n("m", 30, 2),
    _n("D", 32, 1.5), _n("n", 33.5, 1.5), _n("D", 35, 2), _n("m", 37, 2),
    _n("D", 39, 0.5), _n("P", 39.5, 0.5), _n("m", 40, 1), _n("g", 41, 2, andolan=True),
    _n("m", 45, 1.5), _n("g", 46.5, 1.5, andolan=True),
]


# --- where a sway turns: on pitch the raga owns, for every andolit swara --------------------

def test_every_andolan_turns_on_a_pitch_its_raga_owns():
    for raga, swaras in ANDOLAN_TOWARD.items():
        for sw in swaras:
            turn = SWARAS[sw] + andolan_turn_st(raga, sw)
            assert round(turn) % 12 in _owned(raga), (raga, sw, turn)
            assert _audit(raga, [_n(sw, 0, 4, andolan=True).model_copy(
                update={"andolan_st": andolan_turn_st(raga, sw)})]) == set(), (raga, sw)


def test_the_old_bageshree_sway_is_caught_dwelling_on_shuddha_ga():
    old = _n("g", 0, 2, andolan=True).model_copy(update={"andolan_st": 1.0})
    assert "foreign_dwell" in _audit("bageshree", [old])


def test_darbari_sways_25_cents_toward_its_semitone_neighbour():
    # Sujit's blind A/B (2026-10-20) chose 25 cents over the 50 the code drew; van der Meer & Rao's
    # measured dha region is ~25 cents
    for raga, sw in (("darbari", "g"), ("darbari", "d")):
        assert andolan_turn_st(raga, sw) == -0.25, (raga, sw)


# --- Bhairav (2026-10-18): the sway lives inside the swara, approached from above, in descent ----

def test_bhairav_sways_up_inside_re_and_dha_never_toward_sa_or_pa():
    # van der Meer & Rao measured Bhairav's dha within ~32 cents; Parrikar "(G)r S", "(N)d P"
    for sw in ("r", "d"):
        assert andolan_turn_st("bhairav", sw) == 0.2
    assert _audit("bhairav", _alap([_n("G", 0, 1), _n("r", 1, 3, andolan=True), _n("S", 4, 2)], "bhairav")) == set()


def test_bhairav_re_and_dha_take_their_touch_from_above_in_descent():
    line = _alap([_n("G", 0, 1), _n("r", 1, 3, andolan=True), _n("S", 4, 1),
                  _n("N", 5, 1), _n("d", 6, 3, andolan=True), _n("P", 9, 2)], "bhairav")
    assert line[1].grace == ["G"] and line[1].andolan_st == 0.2
    assert line[4].grace == ["N"] and line[4].andolan_st == 0.2


def test_bhairav_re_risen_through_is_plain_and_a_turn_keeps_its_sway():
    passing = _alap([_n("S", 0, 1), _n("r", 1, 2, andolan=True), _n("G", 3, 2)], "bhairav")
    assert not passing[1].andolan and not passing[1].grace    # S r G: r is alpa in the aroha
    turn = _alap([_n("S", 0, 1), _n("r", 1, 2, andolan=True), _n("S", 3, 2)], "bhairav")
    assert turn[1].andolan and turn[1].andolan_st == 0.2       # S r S: the chalan's turn sways


def test_a_whole_tone_neighbour_keeps_the_sway_inside_its_own_swara():
    # half way would be shuddha Ga in Bageshree, shuddha Re in Todi — both foreign
    assert andolan_turn_st("bageshree", "g") == ANDOLAN_SHALLOW_ST
    assert andolan_turn_st("todi", "r") == ANDOLAN_SHALLOW_ST


# --- Bageshree: each Ga gets the ornament its phrase asks for ---------------------------------

def test_bageshree_opening_alap_chooses_each_ga_ornament_by_its_phrase():
    line = {n.start: n for n in _alap(_BAGESHREE_OPENING, "bageshree")}
    rising = [line[13.0], line[29.0]]            # S . g m — Ga steps up into a held Ma
    falling = [line[20.0], line[41.0]]           # m g — Ga arrives from Ma and is held
    for g in rising:                              # Ragajunglism "(m)gm": a Ma kan, no sway
        assert g.grace == ["m"] and not g.andolan and g.pitch_path is None
    for g in falling:                             # guruji's slow Ma->Ga release
        assert g.gesture == GA_MA_RELEASE.name and not g.andolan and not g.grace
        assert g.pitch_path[0][1] == 2.0 and g.pitch_path[-1][1] == 0.0
    assert falling[0].pitch_path != falling[1].pitch_path        # no two alike
    # 750 ms is too short for the slowest release: it keeps the Ma touch, and its shallow sway
    # (under the renderer's 800 ms gate) plays as a steady Ga
    assert line[46.5].grace == ["m"] and line[46.5].pitch_path is None


def test_bageshree_ga_where_the_phrase_rests_keeps_a_shallow_sway():
    line = _alap([_n("S", 0, 2), _n("g", 2, 3, andolan=True), _n("R", 6, 1), _n("S", 7, 2)],
                 "bageshree")
    assert line[1].andolan and line[1].andolan_st == ANDOLAN_SHALLOW_ST
    assert line[1].grace is None                  # no kan into a sway (Sujit, 2026-10-20) — FLAG in raga.py


def test_the_corrected_bageshree_alap_passes_the_audit():
    kinds = _audit("bageshree", _alap(_BAGESHREE_OPENING, "bageshree"))
    assert not kinds & {"foreign_dwell", "unsettled", "held_away", "mechanical", "clipped"}


def test_a_release_is_plucked_at_its_neighbour_and_reaches_its_swara():
    path = gesture_path(GA_MA_RELEASE, "g", seed=20.0)
    events, used = path_wheel(10.0, 2.0, 120, path)
    assert events[0][0] < 10.0 and events[0][1] == _wheel(2.0)   # set before the pluck
    assert events[-1][1] == 0 and used <= 2.0                    # and home on Ga


# --- glides may cross a foreign pitch; they never rest on one ---------------------------------

def test_a_slow_meend_crosses_foreign_pitches_without_dwelling():
    bageshree = _alap([_n("m", 0, 4).model_copy(update={"meend_swara": "g"})], "bageshree")
    yaman = _alap([_n("N", 0, 4).model_copy(update={"meend_swara": "D"})], "yaman")
    assert _audit("bageshree", bageshree) == set()     # m -> g passes shuddha Ga
    assert _audit("yaman", yaman) == set()             # N -> D passes komal Ni


# --- Darbari: exactly as approved ------------------------------------------------------------

def test_darbari_alap_keeps_its_sway_and_the_gat_keeps_guruji_gestures():
    alap = _alap([_n("R", 0, 1), _n("g", 1, 3, andolan=True), _n("R", 4, 1), _n("S", 5, 2)],
                 "darbari")
    assert alap[1].andolan and alap[1].andolan_st == -0.25 and alap[1].pitch_path is None
    gat = _gat([_n("S", 0, 1), _n("g", 1, 2, andolan=True)], "darbari")
    assert gat[1].gesture == GA_MA_LOOP.name     # measured in a gat, played only in one
    assert gesture_for("darbari", "g", "S", alap=True) is None


# --- no kan into a sway; a kan on its own stays (Sujit, 2026-10-20) --------------------------------

def test_a_kan_stays_on_a_note_that_does_not_sway():
    line = _alap([_n("S", 0, 1), _n("m", 1, 2), _n("g", 3, 0.5), _n("R", 3.5, 2)], "darbari")
    swaying = [n for n in line if n.andolan]
    assert not any(n.grace for n in swaying)
    from crew.expression import without_kan_into_sway
    plain = _n("m", 0, 2).model_copy(update={"grace": ["P"]})
    assert without_kan_into_sway([plain], "darbari", 64)[0].grace == ["P"]


def test_bhairav_keeps_the_kan_its_sources_put_into_the_sway():
    from crew.expression import without_kan_into_sway
    held = _n("r", 0, 3, andolan=True).model_copy(update={"grace": ["G"], "andolan_st": 0.2})
    assert without_kan_into_sway([held], "bhairav", 64)[0].grace == ["G"]
    assert without_kan_into_sway([held], "darbari", 64)[0].grace is None


# --- ragas with other ornament traditions stay plain where they have no sway ---------------

def test_ragas_without_andolan_get_no_sway_or_gesture():
    for raga, sw in (("yaman", "G"), ("bhairavi", "g"), ("malkauns", "g")):
        for line in (_alap([_n("S", 0, 1), _n(sw, 1, 3)], raga),
                     _gat([_n("S", 0, 1), _n(sw, 1, 3)], raga)):
            assert not line[1].andolan_st and line[1].pitch_path is None, (raga, line[1])


# --- the gesture data ------------------------------------------------------------------------

def test_the_gesture_table_admits_a_release_but_no_rest_between_swaras():
    assert check_gestures() == []
    assert gesture_for("bageshree", "g", "m", alap=True) is GA_MA_RELEASE
    assert gesture_for("bageshree", "g", "S", alap=True) is None
    from gestures import GESTURES
    bad = (Gesture(name="bad_release", toward="m", knots=((0, 0.0), (200, 1.0), (400, 0.0)),
                   source="test", motion=RELEASE),
           Gesture(name="bad_hold", toward="m", knots=((0, 0.0), (50, 0.5), (300, 0.5), (400, 0.0)),
                   source="test"))
    saved = dict(GESTURES)
    try:
        GESTURES["bageshree"] = tuple(GestureRule(swara="g", gesture=g) for g in bad)
        problems = " ".join(check_gestures())
        assert "bad_release" in problems and "bad_hold" in problems
    finally:
        GESTURES.clear()
        GESTURES.update(saved)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
