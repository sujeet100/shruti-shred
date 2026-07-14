"""
Tests for the renderer's DETERMINISTIC note geometry — chord stacking and technique
shaping — all pure (no fluidsynth, no audio). These are the two pieces of the
riff-voicing feature that live in `src/render.py`: `_stack_above` (a chord tone seats
at the lowest octave over the root) and `_apply_technique` (palm-mute chug / legato
attack). A final smoke builds a MIDI with chords + techniques to prove the wiring
holds; the actual SOUND of a slide/bend still needs Sujit's ear at the live render.

Runs as a script (`uv run python tests/test_render.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from render import (  # noqa: E402
    ANDOLAN_DEPTH_ST,
    BEND_ST,
    PALM_MUTE_DUR,
    PALM_MUTE_VEL,
    SLIDE_IN_ST,
    _andolan_wheel,
    _apply_technique,
    _bends,
    _meend_wheel,
    _stack_above,
    _wheel,
    build_midi,
)


# --- _stack_above: a chord tone seats at the lowest octave over the root --------

def test_power_chord_is_the_root_octave_above():
    # ["S"] on an S root: the chord tone starts AT the root, so it lifts one octave.
    assert _stack_above(60, 60) == 72


def test_fifth_already_above_the_root_stays_put():
    # ["P"] (7 semis) over S(60): already above, so it sounds as the fifth, unmoved.
    assert _stack_above(60, 67) == 67


def test_a_tone_below_the_root_is_lifted_over_it():
    # ["S"] over a P(67) root: S(60) is below, so it climbs to the octave above P.
    assert _stack_above(67, 60) == 72


def test_stacking_is_octave_by_octave_and_strictly_above():
    assert _stack_above(80, 60) == 84            # 60 -> 72 -> 84, first strictly > 80
    assert _stack_above(72, 72) == 84            # equal counts as "not above" -> lift


# --- _apply_technique: palm-mute chug + legato attack, pitch left alone ---------

def test_palm_mute_shortens_and_softens():
    dur, vel = _apply_technique("palm_mute", 1.0, 100)
    assert dur == round(1.0 * PALM_MUTE_DUR, 4)
    assert vel == int(100 * PALM_MUTE_VEL)


def test_legato_softens_attack_only():
    dur, vel = _apply_technique("hammer_on", 1.0, 100)
    assert dur == 1.0 and vel < 100
    assert _apply_technique("pull_off", 0.5, 90)[0] == 0.5


def test_slide_and_bend_leave_note_geometry_untouched():
    # slide/bend are pitch-wheel gestures — they must not change dur or vel.
    assert _apply_technique("slide", 1.0, 100) == (1.0, 100)
    assert _apply_technique("bend", 0.5, 110) == (0.5, 110)
    assert _apply_technique(None, 1.0, 100) == (1.0, 100)


def test_technique_velocity_never_drops_below_one():
    assert _apply_technique("palm_mute", 1.0, 1)[1] >= 1


# --- _meend_wheel: anchored on the target, a quick eased pull that settles in tune -----

def test_meend_pre_bends_to_the_source_and_settles_on_the_target():
    # Anchored on the target: the note is played at the TARGET, so the wheel starts pre-bent
    # at the SOURCE and eases to 0 — the sustained tail rests in tune on the target's sample.
    events = _meend_wheel(0.0, 4.0, from_pitch=60, to_pitch=62, bpm=120)   # +2 st glide up
    assert events[0][1] == _wheel(60 - 62)       # pre-bent DOWN to sound the source on a target note
    assert events[-1][1] == 0                    # ...and settles ON the target (wheel 0)


def test_meend_glide_eases_monotonically_onto_the_target():
    events = _meend_wheel(0.0, 4.0, from_pitch=64, to_pitch=60, bpm=120)   # -4 st (downward is fine)
    vals = [v for _, v in events]
    assert vals[0] == _wheel(64 - 60) and vals[-1] == 0
    assert all(abs(a) >= abs(b) for a, b in zip(vals, vals[1:]))  # magnitude never grows: settles


def test_meend_glide_is_short_and_capped_not_proportional_to_note_length():
    # The pull is a brisk fixed-ish time, NOT a fraction of the note: a long note gets the
    # same quick glide as a short one (no slow swoop lingering on the micro-pitches).
    short = _meend_wheel(0.0, 2.0, 60, 65, bpm=120)
    long = _meend_wheel(0.0, 8.0, 60, 65, bpm=120)
    assert short[-1][0] == long[-1][0]           # identical glide end time regardless of dur
    assert long[-1][0] < 1.0                     # and well under a beat (a pull, not a swoop)


def test_meend_no_glide_when_source_equals_target():
    assert _meend_wheel(0.0, 2.0, 62, 62, bpm=120) == []


# --- _bends: which notes need the wide pitch-bend range armed -------------------

def test_bends_flags_glides_and_pitch_techniques():
    assert _bends({"swara": "S", "meend_swara": "g"}) is True
    assert _bends({"swara": "S", "technique": "slide"}) is True
    assert _bends({"swara": "S", "technique": "bend"}) is True
    assert _bends({"swara": "S", "technique": "palm_mute"}) is False
    assert _bends({"swara": "S"}) is False


def test_bends_flags_andolan_so_the_channel_arms_its_range():
    # andolan moves the wheel too, so the channel must arm the wide bend range for it
    assert _bends({"swara": "g", "andolan": True}) is True
    assert _bends({"swara": "g", "andolan": None}) is False


# --- _andolan_wheel: a slow, shallow sway that starts and ends at 0 -------------

def test_andolan_starts_and_ends_at_zero():
    # whole cycles -> the sine returns to centre, so nothing bleeds into the next note
    events = _andolan_wheel(0.0, 4.0, bpm=120)
    assert events[0][1] == 0 and events[-1][1] == 0


def test_andolan_stays_within_its_shallow_depth():
    events = _andolan_wheel(0.0, 4.0, bpm=120)
    cap = abs(_wheel(ANDOLAN_DEPTH_ST))
    assert all(abs(v) <= cap for _, v in events)
    assert max(abs(v) for _, v in events) > 0          # it actually sways


def test_andolan_sways_both_ways():
    # a real oscillation goes both sharp and flat of the note, not just one side
    vals = [v for _, v in _andolan_wheel(0.0, 4.0, bpm=120)]
    assert max(vals) > 0 and min(vals) < 0


def test_andolan_none_when_note_too_short_for_a_cycle():
    # a sub-cycle note can't read as a slow sway -> no andolan
    assert _andolan_wheel(0.0, 0.1, bpm=120) == []


def test_andolan_span_covers_the_note():
    events = _andolan_wheel(2.0, 4.0, bpm=120)
    assert events[0][0] == 2.0 and events[-1][0] == 6.0   # spans start..start+dur


# --- build_midi smoke: chords + techniques render without crashing --------------

def test_build_midi_renders_chords_and_techniques():
    comp = {
        "raga": "malkauns", "sa": 60, "bpm": 90,
        "tala": {"name": "teentaal", "beats_per_bar": 4},
        "layers": [{
            "role": "rhythm", "instrument": "gtr", "program": 30, "channel": 3, "pan": 20,
            "notes": [
                {"swara": "S", "oct": -2, "start": 0.0, "dur": 1.0,
                 "chord": ["S"], "technique": "palm_mute"},
                {"swara": "g", "oct": -2, "start": 1.0, "dur": 1.0, "technique": "slide"},
                {"swara": "m", "oct": -2, "start": 2.0, "dur": 1.0,
                 "chord": ["P"], "technique": "bend"},
                {"swara": "S", "oct": -2, "start": 3.0, "dur": 1.0, "technique": "hammer_on"},
            ],
        }],
    }
    scratch = os.environ.get("TMPDIR", "/tmp")
    path = os.path.join(scratch, "rma_test_render.mid")
    build_midi(comp, path)
    assert os.path.exists(path) and os.path.getsize(path) > 0
    os.remove(path)


def test_build_midi_emits_bank_select_for_a_banked_layer():
    # A layer carrying `bank` gets Bank Select (CC0=controller 0, CC32=controller 32)
    # emitted before its program change so it routes to a stacked soundfont.
    comp = {
        "raga": "darbari", "sa": 50, "bpm": 120,
        "tala": {"name": "teentaal", "beats_per_bar": 4},
        "layers": [{
            "role": "rhythm", "instrument": "dist_guitar", "program": 0, "channel": 0,
            "bank": 126,
            "notes": [{"swara": "S", "oct": 0, "start": 0.0, "dur": 0.5, "vel": 100}],
        }],
    }
    scratch = os.environ.get("TMPDIR", "/tmp")
    path = os.path.join(scratch, "rma_test_bank.mid")
    build_midi(comp, path)
    data = open(path, "rb").read()
    os.remove(path)
    # Control Change on channel 0 is status 0xB0; controllers 0x00 (MSB) and 0x20 (LSB).
    assert b"\xb0\x00" in data, "bank-select MSB (CC0) not emitted"
    assert b"\xb0\x20" in data, "bank-select LSB (CC32) not emitted"


def test_build_midi_plays_a_routed_tabla_as_melodic_notes():
    # A tabla layer carrying a `bank` (routed to a real tabla soundfont) is emitted as
    # pitched notes on its own melodic channel (8) — bank-select there, NOT GM percussion.
    comp = {
        "raga": "darbari", "sa": 62, "bpm": 90,
        "tala": {"name": "teentaal", "beats_per_bar": 4},
        "layers": [{
            "role": "tabla", "channel": 8, "bank": 50, "program": 0,
            "hits": [{"drum": "tabla_hi", "start": 0.0, "vel": 90},
                     {"drum": "tabla_lo", "start": 1.0, "vel": 90}],
        }],
    }
    scratch = os.environ.get("TMPDIR", "/tmp")
    path = os.path.join(scratch, "rma_test_tabla.mid")
    build_midi(comp, path)
    data = open(path, "rb").read()
    os.remove(path)
    assert b"\xb8\x00" in data, "bank-select MSB (CC0) on channel 8 not emitted"
    assert b"\x98" in data, "no note-on on channel 8 (melodic tabla not played)"


def test_constants_are_sane():
    assert 0 < PALM_MUTE_DUR < 1 and 0 < PALM_MUTE_VEL <= 1
    assert SLIDE_IN_ST < 0 and BEND_ST > 0


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
