"""
Tests for PHRASE-AWARE ARTICULATION — the rhythm guitar rings through the sitar's held notes,
ornaments and bursts, strikes the sam and the sitar's arrivals, plays as written where the sitar
rests, and never changes a pitch. Pure, no LLM.

Runs as a script (`uv run python tests/test_articulation.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.articulation import articulate, expressive_spans  # noqa: E402
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
from crew.generators import VOICES  # noqa: E402

_BAND = ["lead", "rhythm", "drums", "drone"]


def _arr(second_role: str = "antara") -> Arrangement:
    kind = SectionKind.TAAN if second_role.startswith("taan") else SectionKind.MELODY
    draft = ArrangementDraft(
        raga="darbari", subgenre="progressive", tala="teentaal", bpm=120, motif=["g", "m", "R", "S"],
        sections=[Section(kind=SectionKind.MELODY, bars=1, layers=list(_BAND), foreground="lead",
                          riff_slot="main", form_role="mukhada"),
                  Section(kind=kind, bars=1, layers=list(_BAND), foreground="lead",
                          riff_slot="main", form_role=second_role)])
    return build_arrangement(draft, CompositionBrief(sa=62))


def _riff(bars: int = 2) -> Layer:
    """A chug on every beat, alternating S and R, palm-muted — the kind of riff that strikes
    through everything."""
    v = VOICES["rhythm"]
    notes = [Note(swara="S" if t % 2 == 0 else "R", oct=-2, start=float(t), dur=1.0, vel=100,
                  chord=["P", "S"] if t % 2 == 0 else None, technique="palm_mute")
             for t in range(16 * bars)]
    return Layer(role="rhythm", instrument=v.instrument, program=v.program, channel=v.channel,
                 notes=notes)


def _sitar(*notes: Note) -> list[Layer]:
    v = VOICES["sitar"]
    return [Layer(role="lead", instrument=v.instrument, program=v.program, channel=v.channel,
                  notes=list(notes))]


def _at(layer: Layer, t: float) -> Note | None:
    return next((n for n in layer.notes if abs(n.start - t) < 1e-6), None)


def test_the_guitar_rings_through_a_held_sitar_note_instead_of_striking():
    # a held g from beat 2 to 6: the strokes on 3, 4 and 5 fall inside it
    out = articulate(_riff(), _sitar(Note(swara="g", oct=0, start=2.0, dur=4.0)), _arr())
    for t in (3.0, 4.0, 5.0):
        assert _at(out, t) is None
    arrival = _at(out, 2.0)
    assert arrival.technique is None and arrival.dur == 4.0      # lands with the sitar, rings
    assert _at(out, 6.0) is not None and _at(out, 6.0).technique == "palm_mute"


def test_the_sam_is_always_struck():
    out = articulate(_riff(), _sitar(Note(swara="g", oct=0, start=14.0, dur=4.0)), _arr())
    assert _at(out, 16.0) is not None                               # the next section's sam


def test_where_the_sitar_rests_the_riff_plays_as_written():
    riff = _riff()
    out = articulate(riff, _sitar(Note(swara="S", oct=0, start=0.0, dur=0.5)), _arr())
    assert [n for n in out.notes if n.start >= 1.0] == [n for n in riff.notes if n.start >= 1.0]


def test_inside_a_sitar_burst_the_guitar_holds():
    burst = [Note(swara=sw, oct=0, start=4.0 + i * 0.25, dur=0.25)
             for i, sw in enumerate(["g", "m", "R", "S"])]
    out = articulate(_riff(), _sitar(*burst), _arr())
    assert _at(out, 4.0) is None                                       # not struck afresh...
    assert _at(out, 3.0).dur == 2.0 and _at(out, 3.0).technique is None  # ...the chord rings
    assert _at(out, 5.0) is not None                                     # and the riff resumes


def test_a_gamak_cell_struck_twice_is_one_event():
    cell = [Note(swara="g", oct=0, start=2.0, dur=0.5, gamak_with="m"),
            Note(swara="g", oct=0, start=2.5, dur=0.5, gamak_with="m")]
    assert expressive_spans(cell) == [(2.0, 3.0)]


def test_a_taan_keeps_its_full_drive():
    # Sujit (f65dbce): under the long taan the band simplifies harmonically, never rhythmically
    riff = _riff()
    held = Note(swara="g", oct=0, start=18.0, dur=8.0)
    out = articulate(riff, _sitar(held), _arr("taan_long"))
    assert [n for n in out.notes if n.start >= 16.0] == [n for n in riff.notes if n.start >= 16.0]


def test_no_pitch_the_riff_did_not_play():
    riff = _riff()
    sitar = _sitar(Note(swara="g", oct=0, start=1.0, dur=3.0, andolan=True),
                   Note(swara="R", oct=0, start=8.0, dur=4.0))
    out = articulate(riff, sitar, _arr())
    def pitches(layer: Layer) -> set:
        return {(n.swara, n.oct, tuple(n.chord or [])) for n in layer.notes}
    assert pitches(out) <= pitches(riff)


def test_the_band_rings_but_the_bass_and_kit_still_follow_the_riff():
    arr = _arr()
    riff = _riff()
    layers = band_layers(arr, _sitar(Note(swara="g", oct=0, start=2.0, dur=10.0)), riff)
    guitars = [ly for ly in layers if ly.role == "rhythm"]
    assert len(guitars) == 2 and all(len(g.notes) < len(riff.notes) for g in guitars)
    plain = band_layers(arr, _sitar(Note(swara="S", oct=0, start=0.0, dur=0.5)), riff)
    def count(ls: list[Layer], role: str) -> int:
        return sum(len(ly.notes or ly.hits or []) for ly in ls if ly.role == role)
    assert count(layers, "bass") == count(plain, "bass")
    assert count(layers, "drums") == count(plain, "drums")


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
