"""
Tests for the generators' DETERMINISTIC backbone (step 4a) — all pure, no key.

Covers the chart -> audio spine that the LLM generators (Lead/Riff/Groove) will
plug into: the section timeline every generator shares, the raga-aware Drone
(legal by construction — the Malkauns-has-no-Pa case is the whole point), and the
assembly into the Composition contract. The LLM generators are exercised live in
later sub-steps, not here.

Runs as a script (`uv run python tests/test_generators.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.contracts import (  # noqa: E402
    Arrangement,
    ArrangementDraft,
    CompositionBrief,
    Section,
    SectionKind,
    build_arrangement,
    parse_composition,
    voice_registers,
)
from crew.contracts import Layer, Note  # noqa: E402
from crew.generators import (  # noqa: E402
    VOICES,
    assemble_composition,
    bass_layer,
    double_track,
    drone_layer,
    section_spans,
    total_beats,
)
from raga import RAGAS, drone_swaras, validate_composition  # noqa: E402


def _arr(raga: str = "malkauns", subgenre: str = "doom", tala: str = "teentaal",
         bars: tuple[int, ...] = (1, 2), motif=("d", "n", "S", "m")) -> Arrangement:
    """Build a real chart with N sections of the given bar-lengths (no LLM)."""
    sections = [Section(kind=SectionKind.RIFF, bars=b, layers=["rhythm", "drone"],
                        foreground="rhythm") for b in bars]
    draft = ArrangementDraft(raga=raga, subgenre=subgenre, tala=tala, bpm=72,
                             motif=list(motif), sections=sections)
    return build_arrangement(draft, CompositionBrief(mood="dark"))


# --- the section timeline ------------------------------------------------------

def test_section_spans_lay_end_to_end():
    arr = _arr(bars=(1, 2))                     # teentaal: 16 matras -> beats_per_bar 16
    spans = section_spans(arr)
    assert [(s.start, s.end) for s in spans] == [(0.0, 16.0), (16.0, 48.0)]
    assert [s.index for s in spans] == [0, 1]


def test_span_length_is_bars_times_cycle():
    span = section_spans(_arr(bars=(3,)))[0]    # 3 bars x 16 matras
    assert span.length == 48.0


def test_total_beats_sums_the_windows():
    assert total_beats(_arr(bars=(1, 2, 4))) == (1 + 2 + 4) * 16.0


def test_beats_per_bar_follows_the_tala():
    arr = _arr(tala="rupak", bars=(2,))         # rupak = 7 matras
    assert arr.beats_per_bar == 7.0
    assert section_spans(arr)[0].length == 14.0


# --- the drone: raga-aware, legal by construction ------------------------------

def test_drone_tones_are_always_legal_in_the_raga():
    for raga in RAGAS:
        tones = drone_swaras(raga)
        assert tones[0] == "S"                  # Sa is always present
        assert set(tones) <= set(RAGAS[raga]["allowed"])   # never an illegal swara


def test_malkauns_drone_tunes_to_ma_not_pa():
    # Malkauns has NO Pa; the tanpura companion falls back to Ma (Sa-ma).
    tones = drone_swaras("malkauns")
    assert "P" not in tones
    assert tones == ["S", "m"]


def test_ragas_with_pa_tune_sa_pa():
    assert drone_swaras("bhairav") == ["S", "P"]


def test_drone_spans_the_whole_piece_at_its_register():
    arr = _arr(bars=(1, 2))
    layer = drone_layer(arr)
    assert layer.role == "drone"
    assert layer.notes is not None and len(layer.notes) == 2
    for note in layer.notes:
        assert note.start == 0.0
        assert note.dur == total_beats(arr)     # one sustained pad, full length
        assert note.oct == arr.registers["drone"]


def test_drone_uses_the_configured_voice():
    layer = drone_layer(_arr())
    assert (layer.instrument, layer.program, layer.channel) == (
        VOICES["drone"].instrument, VOICES["drone"].program, VOICES["drone"].channel)


# --- assembly into the Composition contract ------------------------------------

def test_assemble_maps_the_arrangement_fields():
    arr = _arr(raga="darbari", tala="rupak", bars=(2,))
    comp = assemble_composition(arr, [drone_layer(arr)])
    assert comp.raga == "darbari" and comp.sa == arr.sa and comp.bpm == arr.bpm
    assert comp.tala == {"name": "rupak", "beats_per_bar": 7.0}
    assert [layer.role for layer in comp.layers] == ["drone"]


def test_assembled_composition_parses_structurally():
    arr = _arr()
    comp = assemble_composition(arr, [drone_layer(arr)])
    parsed, errors = parse_composition(comp.model_dump(exclude_none=True))
    assert errors == [] and parsed is not None


def test_drone_only_composition_is_grammar_clean_even_for_malkauns():
    # The payoff: Malkauns forbids Pa, but the raga-aware drone never sounds it,
    # so validate_composition (the guardrail's core) finds zero violations.
    arr = _arr(raga="malkauns")
    comp = assemble_composition(arr, [drone_layer(arr)])
    assert validate_composition(comp.model_dump(exclude_none=True)) == []


def test_voices_cover_the_melodic_roles_on_distinct_channels():
    assert {"drone", "sitar", "lead_guitar", "rhythm", "bass"} <= set(VOICES)
    channels = [v.channel for v in VOICES.values()]
    assert len(channels) == len(set(channels))   # no two melodic voices collide
    assert 9 not in channels                      # channel 9 is reserved for drums


# --- the bass: a deterministic shadow of the riff (follows its on-beat roots) --

def _busy_riff() -> Layer:
    """A riff with on-beat AND off-beat notes: S on beat 0, an off-beat g at 0.5,
    S on beat 1 — the bass should take the two on-beat roots and drop the g."""
    v = VOICES["rhythm"]
    notes = [Note(swara="S", oct=-3, start=0.0, dur=0.5, vel=120),
             Note(swara="g", oct=-3, start=0.5, dur=0.5, vel=100),
             Note(swara="S", oct=-3, start=1.0, dur=1.0, vel=118)]
    return Layer(role="rhythm", instrument=v.instrument, program=v.program,
                 channel=v.channel, notes=notes)


def _onbeat_riff() -> Layer:
    """A slow riff whose every note is on a beat — the bass should double it."""
    v = VOICES["rhythm"]
    notes = [Note(swara="S", oct=-3, start=0.0, dur=1.0, vel=120),
             Note(swara="g", oct=-3, start=1.0, dur=1.0, vel=110)]
    return Layer(role="rhythm", instrument=v.instrument, program=v.program,
                 channel=v.channel, notes=notes)


def test_bass_follows_on_beat_roots_and_drops_off_beat_notes():
    bass = bass_layer(_arr(), _busy_riff())
    assert bass is not None and bass.role == "bass"
    # takes the on-beat S at 0 and S at 1; the off-beat g at 0.5 is dropped
    assert [(n.swara, n.start) for n in bass.notes] == [("S", 0.0), ("S", 1.0)]


def test_bass_sustains_each_root_to_the_next():
    bass = bass_layer(_arr(), _busy_riff())
    assert bass.notes[0].dur == 1.0                    # 0.0 sustains to the next root at 1.0
    assert bass.notes[-1].start + bass.notes[-1].dur == 2.0   # last sustains to the riff's end


def test_bass_doubles_a_riff_that_is_all_on_the_beat():
    bass = bass_layer(_arr(), _onbeat_riff())
    assert [(n.swara, n.start) for n in bass.notes] == [("S", 0.0), ("g", 1.0)]


def _guitar_riff(oct_: int = -2) -> Layer:
    """A riff seated at the (clamped) rhythm register, for the octave-below bass test."""
    v = VOICES["rhythm"]
    return Layer(role="rhythm", instrument=v.instrument, program=v.program, channel=v.channel,
                 pan=v.pan, notes=[Note(swara="S", oct=oct_, start=0.0, dur=1.0, vel=120),
                                   Note(swara="g", oct=oct_, start=1.0, dur=1.0, vel=110)])


def test_bass_sounds_an_octave_below_the_guitar():
    # bass underpins the guitar rather than doubling its pitch — that's what stops the
    # guitar reading as "just bass". Riff at -2 -> bass at -3.
    bass = bass_layer(_arr(), _guitar_riff(-2))
    assert all(n.oct == -3 for n in bass.notes)
    assert all(n.vel < 121 for n in bass.notes)        # scaled down, sits under the guitar


def test_bass_never_goes_subsonic():
    # if the riff is already deep, the bass floors rather than dropping into inaudible sub-bass
    bass = bass_layer(_arr(), _guitar_riff(-3))
    assert all(n.oct == -3 for n in bass.notes)        # floored at _BASS_FLOOR, not -4


def test_bass_uses_the_bass_voice_not_the_guitar():
    bass = bass_layer(_arr(), _busy_riff())
    assert (bass.instrument, bass.program, bass.channel) == (
        VOICES["bass"].instrument, VOICES["bass"].program, VOICES["bass"].channel)
    assert bass.pan == 64                              # low end holds the centre


def test_rhythm_register_never_drops_to_subbass():
    # a distortion patch at oct -3 (~D1) reads as a rumble; the guitar floors at -2
    for subgenre in ("doom", "death", "thrash", "progressive"):
        assert voice_registers(subgenre)["rhythm"] >= -2


def test_double_track_is_a_second_track_panned_opposite_on_a_different_tone():
    src = _guitar_riff(-2)
    dbl = double_track(src)
    assert dbl is not None and dbl.role == "rhythm"
    assert (src.pan, dbl.pan) == (20, 108)             # hard L / hard R
    assert src.program != dbl.program                  # overdrive vs distortion — not one mono tone
    assert dbl.channel != src.channel                  # its own channel
    # nudged a hair late so the pair decorrelates (Haas width), not mono-summed
    assert dbl.notes[0].start > src.notes[0].start
    assert all(d.swara == s.swara for d, s in zip(dbl.notes, src.notes))   # same riff


def test_no_riff_means_no_double():
    assert double_track(None) is None


def test_no_riff_means_no_bass():
    # a bare alaap (no rhythm guitar) yields no bass — bass follows the riff.
    assert bass_layer(_arr(), None) is None


def test_bass_notes_are_grammar_clean_because_they_are_the_riffs():
    arr = _arr(raga="malkauns")
    bass = bass_layer(arr, _busy_riff())
    comp = assemble_composition(arr, [drone_layer(arr), bass])
    assert validate_composition(comp.model_dump(exclude_none=True)) == []


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
