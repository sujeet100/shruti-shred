"""
Tests for the soundfont ROUTING config (`src/soundfont.py`) — pure, no fluidsynth, no
audio, no on-disk soundfont required. Covers the guitar-routing decision (stack a
dedicated distorted bank over the GM base) and the Bank-Select math, both injectable so
the logic is tested regardless of whether the gitignored .sf2 files are downloaded.

Runs as a script (`uv run python tests/test_soundfont.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import soundfont as sf  # noqa: E402


# --- bank_select_cc: 14-bit bank -> (CC0 MSB, CC32 LSB) under 'mma' mode ---------

def test_bank_select_low_bank_is_all_in_the_lsb():
    assert sf.bank_select_cc(126) == (0, 126)     # Dethmetal's bank
    assert sf.bank_select_cc(0) == (0, 0)         # GM bank 0


def test_bank_select_high_bank_splits_across_msb_and_lsb():
    assert sf.bank_select_cc(200) == (1, 72)      # 1*128 + 72
    assert sf.bank_select_cc(128) == (1, 0)


# --- route_guitars: guitars -> Dethmetal, everything else untouched --------------

def _layers() -> list[dict]:
    return [
        {"role": "rhythm", "instrument": "overdrive_guitar", "program": 29, "channel": 0},
        {"role": "rhythm", "instrument": "dist_guitar", "program": 30, "channel": 5},
        {"role": "lead", "instrument": "dist_guitar_lead", "program": 30, "channel": 4},
        {"role": "lead", "instrument": "sitar", "program": 104, "channel": 2},   # NOT a guitar
        {"role": "bass", "instrument": "electric_bass", "program": 33, "channel": 3},
    ]


def test_routes_every_guitar_to_dethmetal_distorted_when_present():
    layers = _layers()
    sf.route_guitars(layers, dethmetal_present=True)
    for L in layers[:3]:                          # the three guitar voices
        assert L["bank"] == 126 and L["program"] == 0


def test_leaves_sitar_and_bass_on_the_base():
    layers = _layers()
    sf.route_guitars(layers, dethmetal_present=True)
    sitar, bass = layers[3], layers[4]
    assert "bank" not in sitar and sitar["program"] == 104
    assert "bank" not in bass and bass["program"] == 33


def test_no_op_when_dethmetal_absent_guitars_stay_gm():
    layers = _layers()
    sf.route_guitars(layers, dethmetal_present=False)
    for L in layers:
        assert "bank" not in L                    # no routing -> GM overdrive/distortion
    assert layers[0]["program"] == 29 and layers[1]["program"] == 30


# --- route_indian: classical voices -> the Indian Ensemble presets -------------

def _classical() -> list[dict]:
    return [
        {"role": "drone", "instrument": "strings", "program": 48, "channel": 1,
         "notes": [{"swara": "S", "oct": 0}, {"swara": "P", "oct": 0}]},
        {"role": "lead", "instrument": "sitar", "program": 104, "channel": 2,
         "notes": [{"swara": "S", "oct": 0}, {"swara": "g", "oct": 1, "meend_oct": 0}]},
        {"role": "tabla", "channel": 9, "hits": [{"drum": "tabla_hi", "start": 0.0}]},
    ]


def test_sitar_routes_to_indian_and_is_corrected_up_an_octave():
    # the Indian sitar sounds an octave low, so route_indian lifts its notes +1 octave
    # (and any cross-octave meend target with them) to sit in the band's register.
    layers = _classical()
    sf.route_indian(layers, sa=62, indian_present=True)
    sitar = layers[1]
    assert sitar["bank"] == 50 and sitar["program"] == 2
    assert sitar["notes"][0]["oct"] == 1                 # 0 -> +1
    assert sitar["notes"][1]["oct"] == 2 and sitar["notes"][1]["meend_oct"] == 1


def test_drone_stays_on_gm_strings():
    # the tamboura is worse than the GM string pad, so the drone is NOT routed to the Indian SF.
    layers = _classical()
    sf.route_indian(layers, sa=62, indian_present=True)
    drone = layers[0]
    assert "bank" not in drone and drone["program"] == 48


def test_tabla_moves_to_a_melodic_channel_off_gm_percussion():
    layers = _classical()
    sf.route_indian(layers, sa=62, indian_present=True)
    tabla = layers[2]
    assert tabla["bank"] == 50 and tabla["program"] == 0
    assert tabla["channel"] != 9 and tabla["channel"] == 8


def test_tabla_coarse_tune_aligns_the_dayan_to_sa():
    # the dayan sits ~C; tune it to Sa's pitch class by the nearest signed offset (±6).
    assert sf.tabla_coarse_tune(60) == 0     # Sa = C -> no shift
    assert sf.tabla_coarse_tune(62) == 2     # Sa = D -> +2
    assert sf.tabla_coarse_tune(67) == -5    # Sa = G -> nearest is down 5, not up 7
    assert all(-6 <= sf.tabla_coarse_tune(sa) <= 6 for sa in range(48, 84))


def test_route_indian_stamps_the_tabla_tuning():
    layers = _classical()
    sf.route_indian(layers, sa=62, indian_present=True)
    assert layers[2]["coarse_tune"] == 2     # tabla channel tuned +2 to a D-key piece


def test_route_indian_no_op_when_absent():
    layers = _classical()
    sf.route_indian(layers, sa=62, indian_present=False)
    for L in layers:
        assert "bank" not in L
    assert layers[2]["channel"] == 9        # tabla stays on GM percussion (congas)


def test_tabla_keys_are_inside_the_tabla_range():
    # the mapped stroke keys must sit in preset 0's tabla span (53-96), not the tamboura's.
    assert all(53 <= key <= 96 for key in sf.TABLA_KEYS.values())


# --- fluidsynth_soundfont_args: base first, extras follow with their -b offset ----

def test_soundfont_args_start_with_the_base():
    args = sf.fluidsynth_soundfont_args()
    assert args[0] == str(sf.BASE_SOUNDFONT)
    # any present extra appears after a -b <offset> flag
    for extra in sf.present_extras():
        i = args.index(str(extra.path))
        assert args[i - 2] == "-b" and args[i - 1] == str(extra.bank_offset)


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
