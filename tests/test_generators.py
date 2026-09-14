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
    harmonize_riff_to_lead,
    intro_jod_layer,
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


# --- the intro jod string (the alap's ringing home Sa) ------------------------

def _arr_with_intro(intro_bars: int = 3) -> Arrangement:
    sections = [Section(kind=SectionKind.ALAAP, bars=intro_bars, layers=["lead", "drone"],
                        foreground="lead", form_role="intro"),
                Section(kind=SectionKind.RIFF, bars=1, layers=["rhythm", "drone"],
                        foreground="rhythm", form_role="mukhada")]
    draft = ArrangementDraft(raga="kirwani", subgenre="symphonic", tala="keherwa", bpm=120,
                             motif=["S", "g", "P"], sections=sections)
    return build_arrangement(draft, CompositionBrief(mood="epic"))


def test_intro_jod_replucks_home_sa_each_avartan_ringing_and_fading():
    arr = _arr_with_intro(intro_bars=3)
    layer = intro_jod_layer(arr)
    assert layer is not None and layer.role == "jod"
    intro = section_spans(arr)[0]
    cycle = arr.beats_per_bar
    assert len(layer.notes) == 3                            # re-plucked once per avartan (3-bar alap)
    for bar, n in enumerate(layer.notes):
        assert n.swara == "S"                               # home
        assert n.start == intro.start + bar * cycle         # a pluck on each avartan's sam
        assert abs(n.dur - cycle) < 1e-6                    # rings for one cycle, then re-plucked
        assert n.fade is True                               # let to ring then FADE NATURALLY
        assert n.oct == arr.registers["drone"] + 1          # audible mandra, above the tanpura pad
    comp = assemble_composition(arr, [drone_layer(arr), layer])
    assert validate_composition(comp.model_dump(exclude_none=True)) == []   # trivially legal (Sa)


def test_intro_jod_is_none_without_an_intro():
    assert intro_jod_layer(_arr(bars=(1, 2))) is None       # no form_role='intro' -> no jod


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


def _sustained_change_riff() -> Layer:
    """A root HELD two beats, then a different root — a sustained bass note should walk
    up into the change (momentum), not just jump."""
    v = VOICES["rhythm"]
    notes = [Note(swara="S", oct=-2, start=0.0, dur=2.0, vel=110),
             Note(swara="m", oct=-2, start=2.0, dur=2.0, vel=110)]
    return Layer(role="rhythm", instrument=v.instrument, program=v.program,
                 channel=v.channel, notes=notes)


def test_bass_walks_up_into_a_sustained_root_change():
    # the held S is shortened and a raga-legal step (g, between S and m in Malkauns) leads
    # into the m — GPT's "climb into the next chord" momentum
    bass = bass_layer(_arr(), _sustained_change_riff())
    root = next(n for n in bass.notes if n.start == 0.0)
    assert root.swara == "S" and root.dur == 1.5              # shortened to make room
    approach = next(n for n in bass.notes if n.start == 1.5)
    assert approach.swara == "g" and approach.dur == 0.5      # the walk-up step into m
    assert approach.vel < root.vel                            # a lead-in, softer than the root


def test_bass_does_not_walk_up_on_short_roots():
    # a quick root change (each root under the min) stays a plain root line — no clutter
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
    # a few cents sharp — decorrelates the pair even when a specialized soundfont
    # routes BOTH sides to the same patch
    assert dbl.detune_cents and src.detune_cents is None


def test_the_second_take_is_a_performance_not_a_delayed_copy():
    """A CONSTANT offset on every note is a slapback, not a second guitarist — the external
    review measured the right take as the same MIDI shifted by exactly 19 ticks throughout.
    Each note must land, be picked and be held slightly differently."""
    src = _guitar_riff(-2)
    dbl = double_track(src)
    offsets = {round(d.start - s.start, 4) for d, s in zip(dbl.notes, src.notes)}
    assert len(offsets) > 1, "every note shifted by the same amount is a delay line"
    assert all(o > 0 for o in offsets), "the second take still sits behind the first"
    assert len({d.vel for d in dbl.notes}) > 1
    assert len({round(d.dur - s.dur, 4) for d, s in zip(dbl.notes, src.notes)}) > 1


def test_the_second_take_is_reproducible():
    """Keyed, never random: two renders of one composition must be byte-identical, and the
    tests must not flake."""
    src = _guitar_riff(-2)
    assert double_track(src).notes == double_track(src).notes


def test_the_second_take_never_drifts_far_enough_to_flam():
    """Past roughly 25 ms the ear stops fusing the pair and hears two attacks."""
    src = _guitar_riff(-2)
    for d, s in zip(double_track(src).notes, src.notes):
        assert 0 < d.start - s.start < 0.05          # beats — ~25 ms at 120 bpm
        assert d.dur > 0


def test_no_riff_means_no_double():
    assert double_track(None) is None


# --- the riff-under-lead consonance guard ---------------------------------------

def _lead_layer(*notes: Note) -> Layer:
    return Layer(role="lead", instrument="sitar", program=104, channel=2, notes=list(notes))


def test_clashing_riff_note_thins_to_a_soft_chug():
    # a held lead g (komal Ga) over a riff chugging R (a semitone below): the riff note
    # loses its chord, clips to a chug, and softens — the clash turns percussive
    lead = _lead_layer(Note(swara="g", oct=0, start=0.0, dur=2.0))
    riff = Layer(role="rhythm", instrument="gtr", program=29, channel=0,
                 notes=[Note(swara="R", oct=-2, start=0.0, dur=2.0, vel=100, chord=["R"])])
    out = harmonize_riff_to_lead(riff, [lead])
    n = out.notes[0]
    assert n.chord is None and n.dur == 0.5 and n.vel == 90
    assert n.swara == "R"                              # never re-pitched — code doesn't compose
    assert n.technique == "palm_mute"


def test_consonant_riff_notes_pass_untouched():
    # the same swara (ic 0) and a fifth (ic 7 vs Sa lead) are consonant — left alone
    lead = _lead_layer(Note(swara="S", oct=0, start=0.0, dur=4.0))
    riff = Layer(role="rhythm", instrument="gtr", program=29, channel=0,
                 notes=[Note(swara="S", oct=-2, start=0.0, dur=1.0, vel=100, chord=["S"]),
                        Note(swara="P", oct=-2, start=1.0, dur=1.0, vel=100)])
    out = harmonize_riff_to_lead(riff, [lead])
    assert out.notes == riff.notes


def test_fast_passing_lead_notes_do_not_trigger_the_guard():
    # a 16th-note run brushing a semitone is passing colour, not a sustained grind
    lead = _lead_layer(Note(swara="g", oct=0, start=0.0, dur=0.25))
    riff = Layer(role="rhythm", instrument="gtr", program=29, channel=0,
                 notes=[Note(swara="R", oct=-2, start=0.0, dur=2.0, vel=100)])
    out = harmonize_riff_to_lead(riff, [lead])
    assert out.notes == riff.notes


def test_guard_without_lead_or_riff_is_a_no_op():
    riff = _guitar_riff(-2)
    assert harmonize_riff_to_lead(riff, []) is riff
    assert harmonize_riff_to_lead(None, [_lead_layer()]) is None


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
