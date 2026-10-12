"""
Tests for EXPRESSION — the code-set gestures on a placed lead line (andolan direction and depth,
slow alap meend, climax gamak, a plain lead guitar) and the renderer that draws them (holds at
the andolan's turns, the unbent sympathetic layer, the slow meend's stops, the gamak's swings).
No LLM.

Runs as a script (`uv run python tests/test_expression.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.contracts import (  # noqa: E402
    ArrangementDraft,
    CompositionBrief,
    Note,
    Section,
    SectionKind,
    build_arrangement,
)
from crew.expression import ANDOLAN_REACH, express_section  # noqa: E402
from render import (  # noqa: E402
    GAMAK_MAX_CYCLES,
    _andolan_wheel,
    _wheel,
    build_midi,
    gamak_wheel,
    meend_via,
    slow_meend_wheel,
)

_LAYERS = ["lead", "drone"]


def _arr(raga: str, role: str, kind: SectionKind = SectionKind.MELODY, bpm: int = 72):
    section = Section(kind=kind, bars=1, layers=list(_LAYERS), foreground="lead", form_role=role)
    draft = ArrangementDraft(raga=raga, subgenre="doom", tala="teentaal", bpm=bpm,
                             motif=["S"], sections=[section])
    return build_arrangement(draft, CompositionBrief())


def _express(notes: list[Note], raga: str, role: str = "mukhada",
             kind: SectionKind = SectionKind.MELODY, bpm: int = 72):
    arr = _arr(raga, role, kind, bpm)
    return express_section(notes, [n.model_copy() for n in notes], arr.sections[0], arr)


# --- what code stamps --------------------------------------------------------------------

def test_andolan_swings_toward_the_raga_specific_neighbour():
    bageshree, _ = _express([Note(swara="g", start=0, dur=4, andolan=True)], "bageshree")
    bhairav, _ = _express([Note(swara="r", start=0, dur=4, andolan=True)], "bhairav")
    assert bageshree[0].andolan_st == ANDOLAN_REACH * 2       # up toward ma (two semitones)
    assert bhairav[0].andolan_st == -ANDOLAN_REACH * 1        # down toward Sa


def test_slow_meend_belongs_to_the_alap_only():
    glide = [Note(swara="m", start=0, dur=4, meend_swara="g")]
    alap, _ = _express(glide, "bageshree", role="intro", kind=SectionKind.ALAAP)
    gat, _ = _express(glide, "bageshree")
    assert alap[0].meend_style == "slow" and gat[0].meend_style is None


def test_gamak_rides_the_climax_on_notes_long_enough_to_swing():
    line = [Note(swara="m", start=0, dur=0.5), Note(swara="m", start=0.5, dur=0.25),
            Note(swara="g", start=1, dur=2, andolan=True)]
    taan, _ = _express(line, "bageshree", role="taan_long", kind=SectionKind.TAAN)
    # m's next ENTERABLE swara is D, not P: Bageshree's Pa is descent-only
    assert taan[0].gamak_st == 4 and taan[0].vel > line[0].vel
    assert taan[1].gamak_st is None                       # 0.25 beat at 72 bpm is too short
    assert taan[2].gamak_st is None                       # an andolit note keeps its own sway
    plain, _ = _express(line, "bageshree")
    assert all(n.gamak_st is None for n in plain)         # only the climax


def test_an_andolit_swara_never_takes_the_climax_gamak():
    # Darbari's g and d are defined by their slow sway; a short one in the climax plays
    # straight rather than inheriting Sa's and Pa's up-shake
    line = [Note(swara="P", start=0, dur=1), Note(swara="d", start=1, dur=0.5),
            Note(swara="g", start=1.5, dur=0.5)]
    taan, _ = _express(line, "darbari", role="taan_long", kind=SectionKind.TAAN, bpm=64)
    assert taan[0].gamak_st is not None
    assert taan[1].gamak_st is None and taan[2].gamak_st is None


def test_the_gamak_leaves_a_slow_taans_sixteenths_alone():
    # a 64-bpm sixteenth (234 ms) used to clear the bar, so the gamak shook nearly every note
    taan, _ = _express([Note(swara="R", start=0, dur=0.25)], "darbari", role="taan_long",
                       kind=SectionKind.TAAN, bpm=64)
    assert taan[0].gamak_st is None


def test_kan_follows_the_direction_the_line_arrives_from():
    # Darbari: g takes Re rising and Ma falling; d takes Pa rising and Ni falling. The g notes
    # are too short for the measured loop (a held Ga gets that instead — test_gestures), and the
    # falling one comes from Pa: arriving from Ma itself, Ga takes guruji's Re dip
    line = [Note(swara="R", start=0, dur=1), Note(swara="g", start=1, dur=0.3),
            Note(swara="P", start=2, dur=1), Note(swara="g", start=3, dur=0.3),
            Note(swara="P", start=4, dur=1), Note(swara="d", start=5, dur=1),
            Note(swara="n", start=6, dur=1), Note(swara="d", start=7, dur=1)]
    sitar, guitar = _express(line, "darbari", bpm=64)
    assert [n.grace for n in sitar] == [None, ["R"], None, ["m"], None, ["P"], None, ["n"]]
    assert all(n.grace is None for n in guitar)           # the lead guitar plays it plain


def test_a_one_direction_kan_touches_only_that_way():
    # Jog: komal ga takes a Sa touch only coming DOWN (Tanarang "m (S)g S")
    falling = [Note(swara="m", start=0, dur=1), Note(swara="g", start=1, dur=1)]
    rising = [Note(swara="S", start=0, dur=1), Note(swara="g", start=1, dur=1)]
    assert _express(falling, "jog", bpm=64)[0][1].grace == ["S"]
    assert _express(rising, "jog", bpm=64)[0][1].grace is None


def test_kan_respects_what_is_already_there():
    line = [Note(swara="R", start=0, dur=1), Note(swara="g", start=1, dur=1, grace=["m"]),
            Note(swara="g", start=2, dur=1), Note(swara="m", start=3, dur=0.1),
            Note(swara="g", start=3.1, dur=0.2)]
    sitar, _ = _express(line, "darbari", bpm=64)
    assert sitar[1].grace == ["m"]                        # the LLM's kan wins
    assert sitar[2].grace is None                         # a repeated pitch has no approach
    assert sitar[4].grace is None                         # too short to land after a touch
    rising = [Note(swara="R", start=0, dur=1), Note(swara="g", start=1, dur=1)]
    plain, _ = _express(rising, "bhairavi", bpm=64)
    assert plain[1].grace is None                         # a raga with no kan data: untouched


def test_a_khada_raga_gets_no_gamak():
    taan, _ = _express([Note(swara="r", start=0, dur=1)], "marwa", role="taan_long",
                       kind=SectionKind.TAAN)
    assert taan[0].gamak_st is None


def test_the_lead_guitar_plays_the_line_plain():
    line = [Note(swara="g", start=0, dur=4, andolan=True, meend_swara="m")]
    _, guitar = _express(line, "bageshree", role="intro", kind=SectionKind.ALAAP)
    assert not guitar[0].andolan and guitar[0].andolan_st is None
    assert guitar[0].meend_style is None and guitar[0].meend_swara == "m"   # a quick bend stays


# --- what the renderer draws ------------------------------------------------------------

def test_an_upward_andolan_never_dips_below_the_swara():
    vals = [v for _, v in _andolan_wheel(0.0, 6.0, 60, depth_st=1.0)]
    assert min(vals) == 0 and max(vals) > 0


def test_the_andolan_holds_at_its_turns():
    # "multiple meend in succession, punctuated by delicate holds" — the edge is a plateau
    vals = [v for _, v in _andolan_wheel(0.0, 6.0, 60, depth_st=-1.0)]
    deepest = min(vals)
    run = longest = 0
    for v in vals:
        run = run + 1 if v == deepest else 0
        longest = max(longest, run)
    assert longest >= 3


def test_a_slow_meend_holds_its_source_and_rests_on_the_swaras_between():
    # Bhairavi n -> d -> P descending: the glide must pause on komal dha (ITC's example)
    sa = 60
    via = meend_via("bhairavi", sa, sa + 10, sa + 7)
    assert via == [sa + 8]
    ramp = slow_meend_wheel(0.0, 8.0, sa + 10, sa + 7, 60, via)
    vals = [v for _, v in ramp]
    assert vals[0] == vals[1] == _wheel(3)                # holds the source
    assert vals.count(_wheel(1)) >= 2                     # rests on dha on the way
    assert vals[-1] == 0                                  # settles on Pa


def test_a_slow_meend_passes_only_swaras_sung_in_that_direction():
    # Bageshree ascending skips Pa (descent-only): m -> D passes nothing; D -> m passes Pa
    sa = 60
    assert meend_via("bageshree", sa, sa + 5, sa + 9) == []
    assert meend_via("bageshree", sa, sa + 9, sa + 5) == [sa + 7]


def test_a_gamak_swings_to_the_neighbour_and_back_a_few_times():
    ramp = gamak_wheel(0.0, 4.0, 120, 2)
    vals = [v for _, v in ramp]
    assert max(vals) == _wheel(2) and min(vals) == 0 and vals[-1] == 0
    tops = sum(1 for a, b in zip(vals, vals[1:]) if a < _wheel(2) == b)
    assert 1 <= tops <= GAMAK_MAX_CYCLES
    assert gamak_wheel(0.0, 0.05, 120, 2) == []           # too short to swing


def test_a_swaying_note_gets_an_unbent_sympathetic_layer():
    import mido
    lead = {"role": "lead", "instrument": "sitar", "program": 104, "channel": 2,
            "notes": [{"swara": "g", "oct": 0, "start": 0.0, "dur": 4.0, "vel": 100,
                       "andolan": True, "andolan_st": 1.0},
                      {"swara": "m", "oct": 0, "start": 4.0, "dur": 0.5, "vel": 100,
                       "andolan": True, "andolan_st": 1.0}]}           # too short to sway
    comp = {"raga": "bageshree", "sa": 60, "bpm": 60,
            "tala": {"name": "teentaal", "beats_per_bar": 16}, "layers": [lead]}
    path = os.path.join(os.environ.get("TMPDIR", "/tmp"), "rma_test_taraf.mid")
    build_midi(comp, path)
    msgs = [m for t in mido.MidiFile(path).tracks for m in t]
    os.remove(path)
    others = [m for m in msgs if m.type == "note_on" and m.velocity > 0 and m.channel != 2]
    assert len(others) == 1                                # only the swaying note gets one
    assert others[0].note == 63 and others[0].velocity < 100
    assert not any(m.type == "pitchwheel" and m.channel == others[0].channel for m in msgs)


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
