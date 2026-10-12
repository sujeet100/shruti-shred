"""
Tests for the CHORD FLOOR — home held long, the head's one recurring move into the sam, the manjha
and antara moving (the antara an octave up), departures only from the composers' harmony plan and
only on roots with a full power chord, never grinding against a held sitar note. Pure, no LLM.

Runs as a script (`uv run python tests/test_chord_floor.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.band import band_layers  # noqa: E402
from crew.chord_floor import FloorSpan, floor_spans, lift_antara, on_floor  # noqa: E402
from crew.contracts import (  # noqa: E402
    Arrangement,
    ArrangementDraft,
    CompositionBrief,
    HarmonyPlan,
    Layer,
    Note,
    Section,
    SectionKind,
    build_arrangement,
)
from crew.generators import VOICES  # noqa: E402

_BAND = ["lead", "rhythm", "drums", "drone"]


def _sec(role: str, bars: int = 2, mode: str = "modal_pedal", roots: list[str] | None = None,
         kind: SectionKind = SectionKind.MELODY) -> Section:
    return Section(kind=kind, bars=bars, layers=list(_BAND), foreground="lead", riff_slot="main",
                   form_role=role, harmony=HarmonyPlan(mode=mode, roots=roots or []))


def _arr(*sections: Section) -> Arrangement:
    draft = ArrangementDraft(raga="darbari", subgenre="progressive", tala="teentaal", bpm=120,
                             motif=["g", "m", "R", "S"], sections=list(sections))
    return build_arrangement(draft, CompositionBrief(sa=62))


def _sitar(*notes: Note, end: float = 0.0) -> list[Layer]:
    """A sitar line: the given notes, else one long quiet-free line to `end` (plain, passing)."""
    v = VOICES["sitar"]
    body = list(notes) or [Note(swara="S", oct=0, start=t * 0.5, dur=0.5) for t in range(int(end * 2))]
    return [Layer(role="lead", instrument=v.instrument, program=v.program, channel=v.channel,
                  notes=body)]


def _riff(beats: int) -> Layer:
    v = VOICES["rhythm"]
    notes = [Note(swara=sw, oct=-2, start=float(t), dur=1.0, vel=90 + t % 5,
                  technique="slide" if t % 7 == 3 else "palm_mute")
             for t, sw in zip(range(beats), ["S", "R", "g", "m", "P", "d", "n", "P"] * beats)]
    return Layer(role="rhythm", instrument=v.instrument, program=v.program, channel=v.channel,
                 notes=notes)


def _roots(spans: list[FloorSpan]) -> list[tuple[float, float, str]]:
    return [(s.start, s.end, s.root) for s in spans]


def test_the_heads_one_pattern_holds_home_and_departs_only_into_the_sam():
    arr = _arr(_sec("mukhada", roots=["R", "P"]))                # Re has no fifth in Darbari
    spans = floor_spans(arr, _sitar(end=32.0))
    assert _roots(spans) == [(0.0, 12.0, "S"), (12.0, 16.0, "P"),
                             (16.0, 28.0, "S"), (28.0, 32.0, "P")]   # identical every avartan


def test_the_manjha_moves_vibhag_by_vibhag():
    arr = _arr(_sec("manjha", bars=1, roots=["d", "n"]))
    assert _roots(floor_spans(arr, _sitar(end=16.0))) == [
        (0.0, 4.0, "S"), (4.0, 8.0, "d"), (8.0, 12.0, "n"), (12.0, 16.0, "n")]


def test_a_drone_harmony_never_departs():
    arr = _arr(_sec("mukhada", mode="drone"))
    assert {s.root for s in floor_spans(arr, _sitar(end=32.0))} == {"S"}


def test_a_departure_that_grinds_against_a_held_sitar_note_stays_home():
    # komal dha (Bb5: Bb + F) against a held sitar Pa (A): a semitone -> stay on Sa there
    arr = _arr(_sec("manjha", bars=1, roots=["d", "n"]))
    held = Note(swara="P", oct=0, start=4.0, dur=3.0)
    spans = floor_spans(arr, _sitar(held, Note(swara="m", oct=0, start=7.0, dur=9.0)))
    assert _roots(spans)[1] == (4.0, 8.0, "S")


def test_strokes_keep_their_rhythm_and_take_the_floors_root_as_a_power_chord():
    arr = _arr(_sec("mukhada", bars=1, roots=["P"]))
    riff = _riff(16)
    out = on_floor(riff, _sitar(end=16.0), arr)
    assert [(n.start, n.dur, n.vel) for n in out.notes] == [(n.start, n.dur, n.vel) for n in riff.notes]
    assert {n.swara for n in out.notes if n.start < 12} == {"S"}
    assert {n.swara for n in out.notes if n.start >= 12} == {"P"}
    assert all(n.chord == ["P", "S"] for n in out.notes if n.swara == "S")   # root + fifth
    assert all(n.technique != "slide" for n in out.notes)                     # a floor holds


def test_where_the_sitar_is_silent_the_riff_answers_as_written():
    arr = _arr(_sec("mukhada", bars=1, roots=["P"]))
    riff = _riff(16)
    out = on_floor(riff, _sitar(Note(swara="g", oct=0, start=0.0, dur=4.0)), arr)
    assert out.notes[8] == riff.notes[8]                         # beat 8: the sitar rests


def test_a_taan_keeps_its_own_riff():
    arr = _arr(_sec("taan_long", bars=1, kind=SectionKind.TAAN))
    riff = _riff(16)
    assert on_floor(riff, _sitar(end=16.0), arr).notes == riff.notes


def test_the_antara_climbs_an_octave_but_the_bass_stays_down():
    arr = _arr(_sec("mukhada", bars=1, roots=["P"]), _sec("antara", bars=1, roots=["P"]))
    riff = _riff(32)
    lifted = lift_antara(riff, arr)
    assert all(n.oct == -1 for n in lifted.notes if n.start >= 16)
    assert all(n.oct == -2 for n in lifted.notes if n.start < 16)
    layers = band_layers(arr, _sitar(end=32.0), riff)
    bass = next(ly for ly in layers if ly.role == "bass")
    assert {n.oct for n in bass.notes if n.start >= 16} <= {n.oct for n in bass.notes if n.start < 16}


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
