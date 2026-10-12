"""
Tests for the ORNAMENT AUDIT and the ornament fixes it measures (2026-10-12, the out-of-tune 0:07
of fusion_20261012_213455): the audit catches a flat hold, a detuned unison and a mechanical
repeat; the new andolan, taraf rule, varied gestures, settling gamak, sitar sustain and pull
darkening all pass it. Pure, no LLM.

Runs as a script (`uv run python tests/test_ornament_audit.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import mido  # noqa: E402

from gestures import GA_MA_LOOP, GAMAK_SETTLE_SHARE, gamak_stroke_path, gesture_path  # noqa: E402
from ornament_audit import audit_midi  # noqa: E402
from render import SITAR_DECAY_TIMECENTS, build_midi  # noqa: E402

_SITAR = {"role": "lead", "instrument": "sitar", "program": 104, "channel": 2}


def _midi(comp: dict) -> str:
    path = os.path.join(tempfile.mkdtemp(), "audit.mid")
    build_midi(comp, path)
    return path


def _comp(*notes: dict, bpm: int = 120) -> dict:
    return {"raga": "darbari", "sa": 62, "bpm": bpm,
            "tala": {"name": "teentaal", "beats_per_bar": 16},
            "layers": [{**_SITAR, "notes": list(notes)}]}


def _kinds(path: str, channels: tuple[int, ...] = (2, 14)) -> set[str]:
    return {f.kind for f in audit_midi(path) if f.channel in channels}


# --- the audit catches what made 0:07 sound out of tune ----------------------------------------

def test_the_audit_catches_a_flat_hold_and_a_detuned_unison():
    mf = mido.MidiFile(ticks_per_beat=480)
    tr = mido.MidiTrack()
    mf.tracks.append(tr)
    tr += [mido.Message("note_on", channel=2, note=77, velocity=86, time=0),
           mido.Message("note_on", channel=14, note=77, velocity=30, time=0),
           mido.Message("pitchwheel", channel=2, pitch=0, time=480),            # settle 0.5 s
           mido.Message("pitchwheel", channel=2, pitch=-300, time=60),          # ~-44 cents...
           mido.Message("pitchwheel", channel=2, pitch=-300, time=400),         # ...held 0.42 s
           mido.Message("pitchwheel", channel=2, pitch=0, time=60),
           mido.Message("note_off", channel=2, note=77, velocity=0, time=440),
           mido.Message("note_off", channel=14, note=77, velocity=0, time=0)]
    path = os.path.join(tempfile.mkdtemp(), "old.mid")
    mf.save(path)
    assert {"held_away", "detuned_unison"} <= _kinds(path)


def test_the_new_andolan_after_a_kan_passes_the_audit():
    path = _midi(_comp({"swara": "R", "oct": 0, "start": 0.0, "dur": 1.0, "vel": 86},
                       {"swara": "g", "oct": 0, "start": 1.0, "dur": 3.0, "vel": 86,
                        "grace": ["R"], "andolan": True, "andolan_st": -0.5}))
    assert _kinds(path) == set()


def test_a_repeated_fixed_trajectory_is_mechanical_and_a_varied_one_is_not():
    fixed = gesture_path(GA_MA_LOOP, "g")
    def loops(path_for) -> list[dict]:
        return [{"swara": "g", "oct": 0, "start": float(t), "dur": 1.0, "vel": 86,
                 "gesture": "ga_ma_loop", "pitch_path": path_for(t)} for t in range(0, 12, 2)]
    assert "mechanical" in _kinds(_midi(_comp(*loops(lambda t: fixed))))
    varied = loops(lambda t: gesture_path(GA_MA_LOOP, "g", seed=float(t)))
    assert "mechanical" not in _kinds(_midi(_comp(*varied)))


# --- the fixes ---------------------------------------------------------------------------------

def test_a_varied_loop_holds_inside_its_measured_range_and_comes_home():
    lo, hi = GA_MA_LOOP.hold_range_ms
    holds = set()
    for seed in (0.0, 1.5, 3.25, 7.0, 11.5):
        path = gesture_path(GA_MA_LOOP, "g", seed=seed)
        top = [ms for ms, st in path if st == 2.0]
        holds.add(round(top[-1] - top[0]))
        assert lo - 1e-6 <= top[-1] - top[0] <= hi + 1e-6
        assert path[0][1] == path[-1][1] == 0 and path[-1][0] <= GA_MA_LOOP.length_ms
    assert len(holds) > 1                                   # not one fixed trajectory


def test_a_gamak_stroke_is_home_before_the_next_stroke():
    for seed in (0.0, 0.5, 1.0, 2.25, 9.75):
        path = gamak_stroke_path(250.0, 2, seed=seed)
        assert path[-1][1] == 0 and path[-1][0] <= 250.0 * GAMAK_SETTLE_SHARE + 1e-6


def test_every_sitar_channel_rings_longer_and_a_guitar_does_not():
    comp = _comp({"swara": "S", "oct": 0, "start": 0.0, "dur": 2.0, "vel": 86})
    comp["layers"].append({"role": "rhythm", "instrument": "dist_guitar", "program": 30,
                           "channel": 0, "notes": [{"swara": "S", "oct": -2, "start": 0.0,
                                                    "dur": 2.0, "vel": 100}]})
    msgs = [m for t in mido.MidiFile(_midi(comp)).tracks for m in t if m.type == "control_change"]
    def nrpn(ch: int) -> bool:
        cc = [(m.control, m.value) for m in msgs if m.channel == ch]
        value = 8192 + SITAR_DECAY_TIMECENTS
        return {(99, 120), (98, 36), (6, value >> 7), (38, value & 127)} <= set(cc)
    assert nrpn(2) and not nrpn(0)


def test_a_pull_to_the_neighbour_dips_the_expression_and_returns():
    path = _midi(_comp({"swara": "g", "oct": 0, "start": 0.0, "dur": 1.0, "vel": 86,
                        "gesture": "ga_ma_loop", "pitch_path": gesture_path(GA_MA_LOOP, "g")}))
    cc11 = [m.value for t in mido.MidiFile(path).tracks for m in t
            if m.type == "control_change" and m.control == 11 and m.channel == 2]
    assert min(cc11) < 127 and cc11[-1] == 127



# --- intonation: an ati-komal Ga sung low on purpose -------------------------------------------

def _wheels(path: str, ch: int = 2) -> list[tuple[float, int]]:
    out, t = [], 0.0
    for m in mido.MidiFile(path):
        t += m.time
        if m.type == "pitchwheel" and m.channel == ch:
            out.append((t, m.pitch))
    return out


def test_a_note_with_an_intonation_shifts_its_whole_gesture_and_resets_after():
    from render import MEEND_RANGE
    shift = round(-0.2 / MEEND_RANGE * 8191)
    plain = _wheels(_midi(_comp({"swara": "g", "oct": 0, "start": 0.0, "dur": 3.0, "vel": 86,
                                 "andolan": True, "andolan_st": -0.5})))
    low = _wheels(_midi(_comp({"swara": "g", "oct": 0, "start": 0.0, "dur": 3.0, "vel": 86,
                               "andolan": True, "andolan_st": -0.5, "cents": -20})))
    assert low[0][1] == shift                               # the swara starts where it is sung
    swing = [v for _, v in low[1:-1]]
    assert min(swing) == min(v for _, v in plain) + shift   # the sway rides on the low swara
    assert low[-1][1] == 0                                  # the next attack is tempered again


def test_an_intoned_note_never_wakes_the_taraf_and_is_not_an_excursion():
    path = _midi(_comp({"swara": "g", "oct": 0, "start": 0.0, "dur": 3.0, "vel": 86, "cents": -20}))
    notes = [m for t in mido.MidiFile(path).tracks for m in t if m.type == "note_on" and m.velocity]
    assert {m.channel for m in notes} == {2}                # no unbent copy at the tempered pitch
    assert audit_midi(path) == []                           # -20 c held is intonation, not a fault


def test_every_darbari_note_takes_its_shruti_and_an_explicit_value_stands():
    from crew.contracts import Note
    from crew.expression import with_intonation
    line = [Note(swara="g", start=0.0, dur=2.0), Note(swara="g", start=2.0, dur=0.25),
            Note(swara="S", start=2.25, dur=2.0), Note(swara="d", start=4.25, dur=1.0, cents=0.0)]
    out = with_intonation(line, "darbari", 120)
    assert [n.cents for n in out] == [-5.87, -5.87, None, 0.0]   # fast notes too; Sa is Sa
    assert with_intonation(line, "yaman", 120) == line            # not yet sourced: tempered


def test_darbari_is_tuned_by_its_22_shrutis():
    from raga import INTONATION, SHRUTI_OF
    from shruti import check_shrutis, shruti
    assert check_shrutis() == []
    assert shruti(SHRUTI_OF["darbari"]["g"]).name == "Dayavanti"   # the ati-komal Ga, 32/27
    assert shruti(SHRUTI_OF["darbari"]["d"]).name == "Kshiti"      # the ati-komal Dha, 128/81
    assert INTONATION["darbari"] == {"R": 3.91, "g": -5.87, "m": -1.96, "P": 1.96,
                                     "d": -7.82, "n": -3.91}


def test_a_shruti_tuned_ga_keeps_its_taraf_and_passes_the_audit():
    path = _midi(_comp({"swara": "g", "oct": 0, "start": 0.0, "dur": 3.0, "vel": 86,
                        "cents": -5.87}))
    notes = [m for t in mido.MidiFile(path).tracks for m in t if m.type == "note_on" and m.velocity]
    assert len({m.channel for m in notes}) == 2                   # the taraf rings with it
    assert audit_midi(path) == []

if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {t.__name__}: {e!r}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
