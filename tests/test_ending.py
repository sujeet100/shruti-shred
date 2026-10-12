"""
Tests for the ENDING — a hard stop lands one stroke on the sam after the last section and then
nothing sounds; a ring-out lets what still sounds at the end decay past it. Pure, no LLM.

Runs as a script (`uv run python tests/test_ending.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.band import band_layers  # noqa: E402
from crew.contracts import (  # noqa: E402
    Arrangement,
    ArrangementDraft,
    CompositionBrief,
    Layer,
    Note,
    Section,
    SectionKind,
    build_arrangement,
)
from crew.ending import RING_TAIL_S, apply_ending  # noqa: E402
from crew.generators import VOICES, assemble_composition, total_beats  # noqa: E402

_BAND = ["lead", "rhythm", "drums", "drone"]


def _arr(ending: str = "hard_stop", raga: str = "bhairav") -> Arrangement:
    draft = ArrangementDraft(
        raga=raga, subgenre="heavy", tala="teentaal", bpm=128, motif=["S", "m", "S"],
        ending=ending,
        sections=[Section(kind=SectionKind.MELODY, bars=1, layers=list(_BAND), foreground="lead",
                          riff_slot="main", form_role="mukhada"),
                  Section(kind=SectionKind.TAAN, bars=1, layers=list(_BAND), foreground="lead",
                          riff_slot="main", form_role="taan_long")])
    return build_arrangement(draft, CompositionBrief(sa=64))


def _lead(end: float) -> list[Layer]:
    v = VOICES["sitar"]
    notes = [Note(swara="S", oct=0, start=t, dur=1.0) for t in range(0, int(end))]
    return [Layer(role="lead", instrument=v.instrument, program=v.program, channel=v.channel,
                  notes=notes)]


def _rhythm(end: float) -> Layer:
    v = VOICES["rhythm"]
    notes = [Note(swara="S", oct=-2, start=float(t), dur=1.0, vel=110) for t in range(0, int(end))]
    return Layer(role="rhythm", instrument=v.instrument, program=v.program, channel=v.channel,
                 notes=notes)


def _band(arr: Arrangement) -> list[Layer]:
    end = total_beats(arr)
    return band_layers(arr, _lead(end), _rhythm(end))


def _at(layers: list[Layer], role: str, t: float) -> list[Note]:
    return [n for la in layers if la.role == role for n in la.notes or [] if n.start == t]


def test_ring_out_is_the_default():
    draft_default = ArrangementDraft(
        raga="bhairav", subgenre="heavy", tala="teentaal", bpm=128, motif=["S"],
        sections=[Section(kind=SectionKind.RIFF, bars=1, layers=["rhythm", "drone"],
                          foreground="rhythm", riff_slot="main")])
    assert draft_default.ending == "ring_out"


def test_ring_out_lets_what_sounds_at_the_end_decay_past_it():
    # it used to change nothing, so every voice released on the last beat at full level
    arr = _arr("ring_out")
    end = total_beats(arr)
    tail = RING_TAIL_S * arr.bpm / 60.0
    rung = apply_ending(_band(arr), arr)
    last_lead = max((n for la in rung if la.role == "lead" for n in la.notes),
                    key=lambda n: n.start)
    assert last_lead.start + last_lead.dur == end + tail
    assert last_lead.fade_tail == tail                     # the decay is the tail, not the note
    drone = [n for la in rung if la.role == "drone" for n in la.notes]
    assert all(n.fade_tail == tail for n in drone if n.start + n.dur > end)
    early = [n for la in rung for n in la.notes or [] if n.start + n.dur < end - 1e-6]
    assert all(n.fade_tail is None for n in early)        # nothing before the end changes


def test_a_palm_muted_chug_does_not_ring():
    arr = _arr("ring_out")
    end = total_beats(arr)
    v = VOICES["rhythm"]
    chug = Note(swara="S", oct=-2, start=end - 0.5, dur=0.5, technique="palm_mute")
    layer = Layer(role="rhythm", instrument=v.instrument, program=v.program, channel=v.channel,
                  notes=[chug])
    [rung] = apply_ending([layer], arr)
    assert rung.notes == [chug]


def test_the_lead_lands_on_taar_sa_on_the_final_sam():
    arr = _arr()
    sam = total_beats(arr)
    [landing] = _at(_band(arr), "lead", sam)
    assert landing.swara == "S" and landing.oct == arr.registers["lead"] + 1


def test_guitar_bass_and_kit_strike_low_sa_underneath():
    arr = _arr()
    layers = _band(arr)
    sam = total_beats(arr)
    guitars = _at(layers, "rhythm", sam)
    assert len(guitars) == 2                                  # both takes of the double-track
    assert all(g.swara == "S" and g.oct == -2 and g.chord == ["S", "P"] for g in guitars)
    [bass] = _at(layers, "bass", sam)
    assert bass.swara == "S" and bass.oct < -2
    kit = {h.drum for la in layers if la.role == "drums" for h in la.hits or [] if h.start == sam}
    assert {"kick", "crash"} <= kit


def test_nothing_sounds_after_the_stroke():
    arr = _arr()
    sam = total_beats(arr)
    for layer in _band(arr):
        for n in layer.notes or []:
            assert n.start + n.dur <= sam + 1.0 + 1e-6
            assert n.start == sam or n.start + n.dur <= sam + 1e-6   # only the stroke crosses
        for h in layer.hits or []:
            assert h.start <= sam


def test_a_raga_without_pa_gets_a_plain_octave_chord():
    arr = _arr(raga="malkauns")
    guitars = _at(_band(arr), "rhythm", total_beats(arr))
    assert guitars and all(g.chord == ["S"] for g in guitars)


def test_a_note_straddling_the_sam_is_cut_there():
    arr = _arr()
    sam = total_beats(arr)
    v = VOICES["drone"]
    drone = Layer(role="drone", instrument=v.instrument, program=v.program, channel=v.channel,
                  notes=[Note(swara="S", oct=-2, start=0.0, dur=sam + 8)])
    [out] = apply_ending([drone], arr)
    assert out.notes[0].dur == sam


def test_the_ended_piece_is_legal_and_measurable():
    from crew.metrics import composition_metrics
    from raga import validate_composition
    arr = _arr()
    comp = assemble_composition(arr, _band(arr))
    assert validate_composition(comp.model_dump(exclude_none=True)) == []
    composition_metrics(comp, arr)        # the stroke past the last section must not trip it


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
