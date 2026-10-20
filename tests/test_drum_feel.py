"""
Tests for the kit's FEEL chosen by the rhythm section (crew/drum_feel.py, played by crew/groove.py and
crew/dynamics.py) — pure, no LLM. Runs as a script or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.contracts import (  # noqa: E402
    ArrangementDraft,
    CompositionBrief,
    Layer,
    Note,
    RhythmSection,
    RhythmSectionDraft,
    Section,
    SectionKind,
    SectionPart,
    SectionPartDraft,
    build_arrangement,
)
from crew.drum_feel import drum_feels  # noqa: E402
from crew.dynamics import apply_dynamics  # noqa: E402
from crew.groove import GrooveEnergy, _energy_for, groove_layer  # noqa: E402
from crew.rhythm_section import from_draft  # noqa: E402


def _arr(parts=None):
    draft = ArrangementDraft(
        raga="darbari", subgenre="heavy", tala="teentaal", bpm=120, motif=["S", "R", "g"],
        sections=[Section(kind=SectionKind.RIFF, bars=2, layers=["rhythm", "drums", "drone"], foreground="rhythm", intent="a"),
                  Section(kind=SectionKind.MELODY, bars=2, layers=["lead", "rhythm", "drums"], foreground="lead", intent="b")])
    arr = build_arrangement(draft, CompositionBrief(mood="dark"))
    return arr.model_copy(update={"rhythm_section": RhythmSection(parts=parts)}) if parts else arr


def test_feels_resolve_through_same_as_and_skip_silent_parts():
    arr = _arr([SectionPart(section=0, drum_feel="half"), SectionPart(section=1, same_as=0)])
    assert drum_feels(arr) == {0: "half", 1: "half"}
    assert drum_feels(_arr([SectionPart(section=0)])) == {} and drum_feels(_arr()) == {}


def test_the_chosen_feel_overrides_codes_default_except_in_an_alaap():
    riff = Section(kind=SectionKind.RIFF, bars=1, layers=["drums"], foreground="drums", intent="x")
    alaap = Section(kind=SectionKind.ALAAP, bars=1, layers=["drums"], foreground="drums", intent="x")
    assert _energy_for(riff) is GrooveEnergy.DRIVE and _energy_for(riff, "half") is GrooveEnergy.HALF
    assert _energy_for(alaap, "climax") is None


def test_the_kit_plays_the_feel_the_rhythm_section_chose():
    rhythm = Layer(role="rhythm", notes=[Note(swara="S", oct=-1, start=float(b), dur=1.0) for b in range(64)])
    default = groove_layer(_arr(), rhythm).hits
    halved = groove_layer(_arr([SectionPart(section=0, drum_feel="half")]), rhythm).hits
    first = lambda hits: sorted((h.start, h.drum) for h in hits if h.start < 32)   # noqa: E731 — section 0
    assert first(default) != first(halved)
    later = lambda hits: sorted((h.start, h.drum, h.vel) for h in hits if h.start >= 34)   # noqa: E731
    assert later(default) == later(halved)                               # the other section is untouched


def test_a_song_form_section_takes_its_energy_from_the_feel():
    lead = Layer(role="lead", notes=[Note(swara="S", oct=0, start=40.0, dur=1.0, vel=100)])
    untouched = apply_dynamics([lead], _arr())                            # no gat role, no feel: as written
    shaped = apply_dynamics([lead], _arr([SectionPart(section=1, drum_feel="verse")]))
    assert untouched[0].notes[0].vel == 100 and shaped[0].notes[0].vel < 100


def test_the_models_draft_carries_the_feel():
    draft = RhythmSectionDraft(parts=[SectionPartDraft(section=0, drum_feel="climax", guitar=["S[16]"])])
    rs, faults = from_draft(draft)
    assert not faults and rs.parts[0].drum_feel == "climax"


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
