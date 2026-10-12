"""
Tests for measured raga GESTURES — the data (src/gestures.py), the choice by approach, the
expression pass that stamps them on the sitar line, and the renderer that draws their path.
Pure, no LLM.

Runs as a script (`uv run python tests/test_gestures.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))

from crew.contracts import (  # noqa: E402
    ArrangementDraft,
    CompositionBrief,
    Note,
    Section,
    SectionKind,
    build_arrangement,
)
from crew.expression import express_section  # noqa: E402
from gestures import (  # noqa: E402
    GA_MA_LOOP,
    GA_RE_DIP,
    check_gestures,
    gesture_for,
    gesture_path,
)
from render import _wheel, path_wheel  # noqa: E402


def _express(notes: list[Note], raga: str = "darbari", bpm: int = 64):
    section = Section(kind=SectionKind.MELODY, bars=1, layers=["lead", "drone"],
                      foreground="lead", form_role="mukhada")
    draft = ArrangementDraft(raga=raga, subgenre="doom", tala="keherwa", bpm=bpm,
                             motif=["S"], sections=[section])
    arr = build_arrangement(draft, CompositionBrief())
    return express_section(notes, [n.model_copy() for n in notes], arr.sections[0], arr)


# --- the data ------------------------------------------------------------------------

def test_the_gesture_table_is_clean():
    assert check_gestures() == []


def test_darbari_ga_dips_to_re_only_when_it_arrives_from_ma():
    # guruji's recording: arriving from Ma (44.5 s, 48.4 s) Ga dips to Re; from Sa, from Pa
    # or after a rest (3.3, 8.8, 27.1, 52.0 s) it loops up to Ma
    assert gesture_for("darbari", "g", "m") is GA_RE_DIP
    for approach in ("S", "R", "P", None):
        assert gesture_for("darbari", "g", approach) is GA_MA_LOOP
    assert gesture_for("darbari", "d", "P") is None          # Dha's evidence was too thin
    assert gesture_for("yaman", "G", None) is None


def test_a_gesture_path_reaches_its_neighbour_the_short_way():
    loop = gesture_path(GA_MA_LOOP, "g")
    dip = gesture_path(GA_RE_DIP, "g")
    assert max(st for _, st in loop) == 2.0                  # g -> m is a whole tone up
    assert min(st for _, st in dip) == -1.0                  # g -> R is a semitone down
    assert loop[0][1] == loop[-1][1] == 0.0


# --- the expression pass -------------------------------------------------------------

def test_the_sitar_plays_ga_with_the_gesture_its_approach_calls_for():
    line = [Note(swara="S", start=0, dur=1), Note(swara="g", start=1, dur=1),
            Note(swara="m", start=2, dur=1), Note(swara="g", start=3, dur=1)]
    sitar, guitar = _express(line)
    assert [n.gesture for n in sitar] == [None, "ga_ma_loop", None, "ga_re_dip"]
    assert sitar[1].grace is None and sitar[3].grace is None  # the gesture IS the approach
    assert all(n.pitch_path is None for n in guitar)         # the lead guitar stays plain


def test_a_note_too_short_for_the_gesture_keeps_its_kan():
    # a 64-bpm eighth is 469 ms: room for the 370 ms loop and its settle; 0.3 beat (281 ms)
    # is not, but still carries the 60 ms kan
    line = [Note(swara="S", start=0, dur=1), Note(swara="g", start=1, dur=0.3)]
    sitar, _ = _express(line)
    assert sitar[1].gesture is None and sitar[1].grace == ["R"]


def test_the_llms_own_ornament_wins():
    line = [Note(swara="S", start=0, dur=1), Note(swara="g", start=1, dur=1, grace=["m"])]
    sitar, _ = _express(line)
    assert sitar[1].gesture is None and sitar[1].grace == ["m"]


def test_after_a_silence_ga_is_a_fresh_attack():
    line = [Note(swara="m", start=0, dur=1), Note(swara="g", start=3, dur=1)]
    sitar, _ = _express(line)
    assert sitar[1].gesture == "ga_ma_loop"                  # not approached from Ma


# --- the renderer --------------------------------------------------------------------

def test_the_path_is_drawn_in_milliseconds_and_returns_home():
    path = gesture_path(GA_MA_LOOP, "g")
    events, used = path_wheel(10.0, 1.0, 60, path)            # 60 bpm: 1 beat = 1000 ms
    assert used == 0.37
    assert events[0] == (10.0, 0) and events[-1] == (10.37, 0)
    assert max(v for _, v in events) == _wheel(2.0)          # the dwell sits on Ma
    on_ma = [t for t, v in events if v == _wheel(2.0)]
    assert min(on_ma) == 10.1 and max(on_ma) == 10.27        # rise ends 100 ms, dwell to 270


def test_the_taraf_waits_until_the_gesture_has_come_home():
    # GPT, 2026-10-12: an unbent Ga on the taraf channel sounded while the string bent up to Ma
    import mido

    from render import build_midi
    path = gesture_path(GA_MA_LOOP, "g")
    comp = {"raga": "darbari", "sa": 62, "bpm": 60, "layers": [{
        "role": "lead", "instrument": "sitar", "program": 104, "channel": 2,
        "notes": [{"swara": "g", "start": 0.0, "dur": 3.0, "andolan": True,
                   "andolan_st": -0.5, "pitch_path": path}]}]}
    out = os.path.join(ROOT, "tests", "_taraf.mid")
    build_midi(comp, out)
    mid = mido.MidiFile(out)
    os.remove(out)
    t, taraf_on = 0, []
    for m in mido.merge_tracks(mid.tracks):
        t += m.time
        if m.type == "note_on" and m.velocity > 0 and m.channel != 2:
            taraf_on.append(t / mid.ticks_per_beat)
    assert taraf_on and min(taraf_on) >= 0.37 - 1e-3          # 370 ms at 60 bpm = 0.37 beat


def test_a_path_longer_than_its_note_is_not_drawn():
    assert path_wheel(0.0, 0.2, 60, gesture_path(GA_MA_LOOP, "g")) == ([], 0.0)


def test_rasik_reads_the_gesture():
    from crew.rasik import _note_token
    looped = Note(swara="g", start=0, dur=1, gesture="ga_ma_loop",
                  pitch_path=gesture_path(GA_MA_LOOP, "g"))
    assert _note_token(looped) == "g{m}[1]"


# --- gamak cells ---------------------------------------------------------------------

def test_a_gamak_partner_must_be_an_adjacent_legal_neighbour():
    from gestures import gamak_interval
    assert gamak_interval("darbari", "g", "m") == 2           # guruji's opening pair
    assert gamak_interval("darbari", "d", "P") == -1          # his mandra Pa<->Dha
    assert gamak_interval("darbari", "g", "P") is None        # not adjacent
    assert gamak_interval("bageshree", "m", "P") is None      # Pa is never entered rising
    assert gamak_interval("yaman", "G", "M") == 2             # gamak is not Darbari-only


def test_gamak_strokes_fall_near_the_measured_quarter_second():
    from gestures import gamak_stroke_beats
    assert gamak_stroke_beats(120) == 0.5                     # guruji: two strokes a beat
    assert gamak_stroke_beats(64) == 0.25                     # 234 ms at doom tempo


def test_a_gamak_stroke_swings_out_and_back_at_the_measured_speed():
    from gestures import gamak_stroke_path
    path = gamak_stroke_path(250, 2)
    assert path == [[0.0, 0.0], [85.0, 0.0], [110.0, 2.0], [195.0, 2.0], [220.0, 0.0]]
    short = gamak_stroke_path(150, 2)                         # a fast tempo compresses it
    assert short[-1][0] <= 150 and max(st for _, st in short) == 2.0


def test_a_gamak_note_becomes_a_run_of_swinging_strokes():
    line = [Note(swara="S", start=0, dur=1),
            Note(swara="g", start=1, dur=1, vel=100, gamak_with="m")]
    sitar, guitar = _express(line)                             # 64 bpm -> sixteenth strokes
    strokes = [n for n in sitar if n.gesture == "gamak"]
    assert len(strokes) == 4 and [n.start for n in strokes] == [1.0, 1.25, 1.5, 1.75]
    assert strokes[0].vel == 100 and strokes[1].vel < 100      # the first stroke leads
    assert all(max(st for _, st in n.pitch_path) == 2.0 for n in strokes)
    assert all(n.pitch_path is None for n in guitar)          # the lead guitar plays it plain


def test_an_illegal_or_khada_gamak_plays_plain():
    bad, _ = _express([Note(swara="P", start=0, dur=1, gamak_with="S")])   # Pa's neighbours: m, d
    assert len(bad) == 1 and bad[0].pitch_path is None and bad[0].gamak_with is None
    khada, _ = _express([Note(swara="r", start=0, dur=1, gamak_with="G")], raga="marwa")
    assert len(khada) == 1 and khada[0].pitch_path is None


def test_the_alap_keeps_its_ornament_slow():
    # guruji's gestures and gamaks were measured in a GAT; the alap keeps the sourced slow
    # andolan and kan (GPT, 2026-10-12: "don't use the fast gat opening as the alap template")
    line = [Note(swara="S", start=0, dur=1), Note(swara="g", start=1, dur=2, andolan=True),
            Note(swara="m", start=3, dur=1, gamak_with="P")]
    section = Section(kind=SectionKind.ALAAP, bars=1, layers=["lead", "drone"],
                      foreground="lead", form_role="intro")
    draft = ArrangementDraft(raga="darbari", subgenre="doom", tala="keherwa", bpm=64,
                             motif=["S"], sections=[section])
    arr = build_arrangement(draft, CompositionBrief())
    sitar, _ = express_section(line, [], arr.sections[0], arr)
    assert all(n.pitch_path is None for n in sitar)           # no gesture, no gamak strokes
    assert sitar[1].andolan and sitar[1].grace == ["R"]       # the slow sway and its kan
    assert len(sitar) == 3


def test_in_the_gat_the_gesture_replaces_the_sway():
    # after the loop, guruji's Ga holds steady; a sway bolted on read as two movements
    line = [Note(swara="S", start=0, dur=1), Note(swara="g", start=1, dur=2, andolan=True)]
    sitar, _ = _express(line)
    assert sitar[1].gesture == "ga_ma_loop" and not sitar[1].andolan


def test_a_composed_gamak_replaces_the_climax_fallback():
    from crew.expression import express_section
    section = Section(kind=SectionKind.TAAN, bars=1, layers=["lead", "drone"],
                      foreground="lead", form_role="taan_long")
    draft = ArrangementDraft(raga="darbari", subgenre="doom", tala="keherwa", bpm=64,
                             motif=["S"], sections=[section])
    arr = build_arrangement(draft, CompositionBrief())
    line = [Note(swara="P", start=0, dur=1), Note(swara="m", start=1, dur=1, gamak_with="P")]
    sitar, _ = express_section(line, [], arr.sections[0], arr)
    assert sitar[0].gamak_st is None                          # no per-note shake on top


def test_the_composer_is_told_where_gamak_belongs():
    from crew.lead import render_gamak
    assert "g<>m" in render_gamak("darbari")
    assert "gamak_with" in render_gamak("yaman")
    assert render_gamak("marwa").startswith("NONE")


def test_junk_gamak_partners_are_absorbed_at_the_boundary():
    from crew.contracts import LeadNote
    assert LeadNote(swara="g", dur=1, gamak_with="x").gamak_with is None
    assert LeadNote(swara="g", dur=1, gamak_with="m").gamak_with == "m"


def test_rasik_and_the_density_measure_see_a_gamak():
    from crew.density import moves_per_beat
    from crew.rasik import _note_token
    sitar, _ = _express([Note(swara="g", start=0, dur=1, gamak_with="m")])
    assert _note_token(sitar[0]) == "g<>m"
    assert moves_per_beat(sitar, 1)[0] >= 8                   # four strokes, each out and back


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
