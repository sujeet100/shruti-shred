"""
Tests for the renderer's DETERMINISTIC note geometry — chord voicing and technique
shaping — all pure (no fluidsynth, no audio). These are the two pieces of the
riff-voicing feature that live in `src/render.py`: `_seat_chord_tone` (a chord tone
seats at a distortion-CONSONANT interval over the root — octave / fifth / fourth /
add9 / tenth — or has no seat and degrades to octave weight) and `_apply_technique`
(palm-mute chug / legato attack). A final smoke builds a MIDI with chords + techniques
to prove the wiring holds; the actual SOUND still needs Sujit's ear at the live render.

Runs as a script (`uv run python tests/test_render.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from render import (  # noqa: E402
    ANDOLAN_CC11_DIP,
    ANDOLAN_DELAY_MS,
    ANDOLAN_DEPTH_ST,
    ANDOLAN_MIN_MS,
    ANDOLAN_PERIOD_MS,
    ANDOLAN_STEPS_PER_CYCLE,
    BEND_ST,
    PALM_MUTE_MS,
    SLIDE_IN_ST,
    _andolan_cc,
    _andolan_wheel,
    _apply_technique,
    _bends,
    _meend_wheel,
    _pull_offset,
    _render_bend,
    _seat_chord_tone,
    _wheel,
    build_midi,
)


# --- _seat_chord_tone: consonant-under-distortion voicing ----------------------

def test_own_swara_seats_as_the_power_chord_octave():
    # ["S"] on an S root: same pitch class -> the octave, whatever octave it was written in.
    assert _seat_chord_tone(60, 60) == 72
    assert _seat_chord_tone(60, 48) == 72


def test_perfect_fifth_and_fourth_keep_their_seats():
    assert _seat_chord_tone(60, 67) == 67        # Sa root + Pa: the true fifth
    assert _seat_chord_tone(67, 60) == 72        # Pa root + Sa: the INVERTED power chord (a fourth)


def test_seconds_and_thirds_lift_above_the_octave():
    assert _seat_chord_tone(60, 62) == 74        # major second -> add9
    assert _seat_chord_tone(60, 63) == 75        # minor third  -> a minor tenth
    assert _seat_chord_tone(60, 64) == 76        # major third  -> a major tenth


def test_clashing_intervals_have_no_seat():
    # semitone, tritone, sixths, sevenths: mud under distortion -> None (octave substitute).
    for tone in (61, 66, 68, 69, 70, 71):
        assert _seat_chord_tone(60, tone) is None


# --- _fade_ramp: the ring-out — expression dies away, then snaps back -----------

def test_fade_ramp_decays_to_the_floor_and_resets():
    from render import _FADE_FLOOR, _fade_ramp
    ramp = _fade_ramp(10.0, 8.0)
    assert ramp[0] == (10.0, 127)                 # starts at full expression
    assert ramp[-1] == (18.0, 127)                # ...and SNAPS BACK at the note's end
    assert ramp[-2][1] == _FADE_FLOOR             # having decayed to the quiet floor
    values = [v for _, v in ramp[:-1]]
    assert values == sorted(values, reverse=True)  # monotonic decay — a dying string


# --- _apply_technique: palm-mute chug + legato attack, pitch left alone ---------

def test_palm_mute_gates_but_keeps_its_punch():
    dur, vel = _apply_technique("palm_mute", 1.0, 100, 120)
    assert dur == round(PALM_MUTE_MS * 120 / 60000.0, 4)   # a fixed wall-clock gate
    assert _apply_technique("palm_mute", 0.05, 100, 120)[0] == 0.05  # capped at written dur
    assert vel == 100    # NO velocity cut — the muted timbre carries the softness


def test_legato_softens_attack_only():
    dur, vel = _apply_technique("hammer_on", 1.0, 100, 120)
    assert dur == 1.0 and vel < 100
    assert _apply_technique("pull_off", 0.5, 90, 120)[0] == 0.5


def test_slide_and_bend_leave_note_geometry_untouched():
    # slide/bend are pitch-wheel gestures — they must not change dur or vel.
    assert _apply_technique("slide", 1.0, 100, 120) == (1.0, 100)
    assert _apply_technique("bend", 0.5, 110, 120) == (0.5, 110)


def test_long_slide_and_pick_scrape_are_wheel_gestures_too():
    # the sitar-fusion gestures: geometry untouched, but the wheel gets armed for them.
    assert _apply_technique("long_slide", 1.0, 100, 120) == (1.0, 100)
    assert _apply_technique("pick_scrape", 0.5, 110, 120) == (0.5, 110)
    assert _bends({"technique": "long_slide"}) and _bends({"technique": "pick_scrape"})


def test_bend_apex_follows_the_per_note_depth():
    # the sequencer stamps a raga-aware bend_st per note; the renderer's held apex
    # must follow it (the fixed BEND_ST is only the fallback for hand-authored dicts)
    class _Rec:
        def __init__(self) -> None:
            self.wheels: list[tuple[float, int]] = []

        def addPitchWheelEvent(self, track, ch, t, v) -> None:
            self.wheels.append((t, v))

    rec = _Rec()
    _render_bend(rec, 0, 0, 0.0, 1.0, st=3)
    assert max(v for _, v in rec.wheels) == _wheel(3)   # the apex is the stamped depth
    assert rec.wheels[-1][1] == 0                       # ...and the wheel recenters


def test_legato_arms_the_wheel_and_pulls_from_the_previous_pitch():
    # hammer_on/pull_off are now real legato: the wheel arms for them, and the pull
    # offset is the previous note's pitch relative to this one, capped.
    assert _bends({"technique": "hammer_on"}) and _bends({"technique": "pull_off"})
    assert _pull_offset(62, 60, 4) == 2.0        # pull-off from a tone above
    assert _pull_offset(57, 60, 4) == -3.0       # hammer-on from below
    assert _pull_offset(50, 60, 4) == -4.0       # wide travel is capped
    assert _pull_offset(None, 60, 4) is None     # no previous note -> no gesture
    assert _pull_offset(60, 60, 4) is None       # no travel -> no gesture


def test_build_midi_routes_chugs_to_a_muted_guitar_channel():
    # palm-muted rhythm notes sound on a companion channel playing GM muted guitar
    # (program 28), with the open notes staying on the take's own channel.
    comp = {
        "raga": "malkauns", "sa": 50, "bpm": 120,
        "tala": {"name": "teentaal", "beats_per_bar": 4},
        "layers": [{
            "role": "rhythm", "instrument": "gtr", "program": 29, "channel": 0, "pan": 20,
            "notes": [
                {"swara": "S", "oct": 0, "start": 0.0, "dur": 0.5, "technique": "palm_mute"},
                {"swara": "S", "oct": 0, "start": 0.5, "dur": 0.5, "technique": "palm_mute"},
                {"swara": "g", "oct": 0, "start": 1.0, "dur": 1.0},
            ],
        }],
    }
    scratch = os.environ.get("TMPDIR", "/tmp")
    path = os.path.join(scratch, "rma_test_mute.mid")
    build_midi(comp, path)
    data = open(path, "rb").read()
    os.remove(path)
    # the companion lands on the first free channel (1 here): program change 0xC1 to 28,
    # and note-ons 0x91 carry the chugs; the take (0x90) still sounds the open note.
    assert b"\xc1\x1c" in data, "no muted-guitar program on the companion channel"
    assert b"\x91" in data, "chugs not sounded on the companion channel"
    assert b"\x90" in data, "open notes must stay on the take's channel"


def test_build_midi_bank_selects_a_real_pm_patch_on_the_companion():
    # a layer routed with pm_bank (SGM's muted-distortion articulation) bank-selects
    # the companion channel there instead of the GM mute; 301 -> CC0=2, CC32=45.
    comp = {
        "raga": "malkauns", "sa": 50, "bpm": 120,
        "tala": {"name": "teentaal", "beats_per_bar": 4},
        "layers": [{
            "role": "rhythm", "instrument": "gtr", "program": 29, "channel": 0,
            "pm_bank": 301, "pm_program": 28,
            "notes": [
                {"swara": "S", "oct": 0, "start": 0.0, "dur": 0.5, "technique": "palm_mute"},
            ],
        }],
    }
    scratch = os.environ.get("TMPDIR", "/tmp")
    path = os.path.join(scratch, "rma_test_pm_bank.mid")
    build_midi(comp, path)
    data = open(path, "rb").read()
    os.remove(path)
    assert b"\xb1\x00\x02" in data, "PM bank-select MSB missing on the companion"
    assert b"\xb1\x20\x2d" in data, "PM bank-select LSB missing on the companion"
    assert b"\xc1\x1c" in data, "PM program change missing on the companion"


def test_build_midi_renders_a_legato_pull_on_the_wheel():
    comp = {
        "raga": "malkauns", "sa": 50, "bpm": 120,
        "tala": {"name": "teentaal", "beats_per_bar": 4},
        "layers": [{
            "role": "rhythm", "instrument": "gtr", "program": 29, "channel": 0,
            "notes": [
                {"swara": "S", "oct": 0, "start": 0.0, "dur": 0.5},
                {"swara": "g", "oct": 0, "start": 0.5, "dur": 0.5, "technique": "hammer_on"},
            ],
        }],
    }
    scratch = os.environ.get("TMPDIR", "/tmp")
    path = os.path.join(scratch, "rma_test_legato.mid")
    build_midi(comp, path)
    data = open(path, "rb").read()
    os.remove(path)
    assert b"\xe0" in data, "a connected hammer-on must move the pitch wheel"
    assert _apply_technique(None, 1.0, 100, 120) == (1.0, 100)


def test_technique_velocity_never_drops_below_one():
    assert _apply_technique("palm_mute", 1.0, 1, 120)[1] >= 1


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


# --- _andolan_wheel: settle, then a slow, uneven, downward undulation -----------

def test_andolan_starts_and_ends_at_zero():
    # every wave returns to the swara and the gesture ends at 0 — no bleed onward
    events = _andolan_wheel(0.0, 4.0, bpm=120)
    assert events[0][1] == 0 and events[-1][1] == 0


def test_andolan_stays_within_its_depth():
    events = _andolan_wheel(0.0, 4.0, bpm=120)
    cap = abs(_wheel(ANDOLAN_DEPTH_ST))
    assert all(abs(v) <= cap for _, v in events)
    assert max(abs(v) for _, v in events) > 0          # it actually sways


def test_andolan_dips_below_the_note_only():
    # AUTRIM: ga's movements occur BETWEEN Re and Ga — the wheel never rises above
    # the swara's own pitch (ga leans toward Re, dha toward Pa)
    vals = [v for _, v in _andolan_wheel(0.0, 4.0, bpm=120)]
    assert max(vals) == 0 and min(vals) < 0


def test_andolan_settles_before_it_sways():
    # the note lands and holds steady for the settle window before the first dip
    delay_beats = ANDOLAN_DELAY_MS * 120 / 60000.0
    events = _andolan_wheel(0.0, 4.0, bpm=120)
    assert all(v == 0 for t, v in events if t < delay_beats)


def test_andolan_none_when_note_too_short_for_a_cycle():
    # a sub-cycle note can't read as a slow sway -> no andolan
    assert _andolan_wheel(0.0, 0.1, bpm=120) == []


def test_andolan_none_on_a_hold_below_the_real_time_gate():
    # 2 beats at 160 bpm = 750 ms — long enough for the OLD fast wobble, but a slow
    # sway squeezed in would read as vibrato -> plays plain (the Darbari-render bug)
    dur_ms = 2.0 * 60000.0 / 160
    assert dur_ms < ANDOLAN_MIN_MS                     # the premise of the test
    assert _andolan_wheel(0.0, 2.0, bpm=160) == []


def test_andolan_waves_are_slow():
    # 4 beats at 120 = 2000 ms -> settle + two waves, each near the ~900 ms period
    events = _andolan_wheel(0.0, 4.0, bpm=120)
    waves = (len(events) - 1) / ANDOLAN_STEPS_PER_CYCLE
    assert waves == 2
    sway_ms = 4.0 * 60000.0 / 120 - ANDOLAN_DELAY_MS
    assert sway_ms / waves >= 0.75 * ANDOLAN_PERIOD_MS


def test_andolan_waves_are_uneven():
    # no two waves alike — a perfectly periodic dip reads as machine vibrato
    events = _andolan_wheel(0.0, 4.0, bpm=120)
    vals = [v for _, v in events[1:]]                  # drop the settle event
    per_wave = [vals[k * ANDOLAN_STEPS_PER_CYCLE:(k + 1) * ANDOLAN_STEPS_PER_CYCLE]
                for k in range(len(vals) // ANDOLAN_STEPS_PER_CYCLE)]
    assert len({min(w) for w in per_wave}) > 1         # depths differ wave to wave


def test_andolan_is_deterministic():
    # jitter is hash-keyed, not RNG — same note, same sway (re-renders reproducible,
    # and unison doubles at the same start sway in phase)
    assert _andolan_wheel(3.0, 4.0, bpm=120) == _andolan_wheel(3.0, 4.0, bpm=120)


def test_andolan_span_covers_the_note():
    events = _andolan_wheel(2.0, 4.0, bpm=120)
    assert events[0][0] == 2.0 and events[-1][0] == 6.0   # spans start..start+dur


def test_andolan_cc_shimmer_tracks_the_dip_and_recenters():
    # expression rides the sway: full (127) at the swara, dipped at the trough
    assert _andolan_cc(0) == 127
    assert _andolan_cc(_wheel(-ANDOLAN_DEPTH_ST)) == 127 - ANDOLAN_CC11_DIP


def test_andolan_after_a_glide_leaves_the_onset_to_the_meend():
    # meend INTO the sway ("R -> g~~"): the sway drops its settle-at-0 event — a 0 at
    # the onset would yank the wheel mid-glide — and the waves are otherwise identical
    full = _andolan_wheel(0.0, 4.0, bpm=120)
    composed = _andolan_wheel(0.0, 4.0, bpm=120, after_glide=True)
    assert composed == full[1:]
    assert all(t > 0.0 for t, _ in composed)
    # the invariant that makes the composition safe: the settle outlasts any glide,
    # so the first wave always departs from an in-tune, settled swara
    from render import ANDOLAN_DELAY_MS as delay, MEEND_GLIDE_MAX_MS as glide_max
    assert delay > glide_max


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
    assert 30 <= PALM_MUTE_MS <= 120
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
