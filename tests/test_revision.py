"""
Tests for the EDIT-BASED revise (crew/revision.py) — pure, no LLM.

A plan threads its instruction AND its preserve list into exactly the sections it names (where
its voice plays), and only those sections' regenerated notes replace the old — every other
section keeps what was already accepted.

Runs as a script (`uv run python tests/test_revision.py`) or under pytest.
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
    ProducerScores,
    RevisionPlan,
    Section,
    SectionKind,
    build_arrangement,
)
from crew.revision import (  # noqa: E402
    is_stalled,
    revise_arrangement,
    splice_layer,
    splice_layers,
    target_sections,
)


def _arr():
    """Three 1-bar teentaal sections (16 beats each): riff only, lead+riff, lead+riff."""
    band = ["lead", "rhythm", "drums", "drone"]
    draft = ArrangementDraft(
        raga="darbari", subgenre="progressive", tala="teentaal", bpm=120, motif=["S", "R", "g"],
        sections=[
            Section(kind=SectionKind.RIFF, bars=1, layers=["rhythm", "drums", "drone"],
                    foreground="rhythm", intent="main riff"),
            Section(kind=SectionKind.MELODY, bars=1, layers=band, foreground="lead", intent="hook"),
            Section(kind=SectionKind.TAAN, bars=1, layers=band, foreground="lead", intent="taan")])
    return build_arrangement(draft, CompositionBrief(mood="dark"))


def _layer(role: str, *starts: float, swara: str = "S") -> Layer:
    return Layer(role=role, notes=[Note(swara=swara, oct=0, start=t, dur=1.0) for t in starts])


def test_a_plan_targets_its_sections_where_its_voice_plays():
    arr = _arr()
    assert target_sections(arr, RevisionPlan(voice="lead", instruction="x")) == [1, 2]
    assert target_sections(arr, RevisionPlan(voice="lead", sections=[0, 2], instruction="x")) == [2]
    assert target_sections(arr, RevisionPlan(voice="riff", sections=[0], instruction="x")) == [0]


def test_the_instruction_and_the_preserve_list_ride_only_the_targeted_intents():
    arr = _arr()
    plan = RevisionPlan(voice="lead", sections=[2], instruction="end on komal dha",
                        preserve=["the hook", "the main riff's rhythm"])
    revised = revise_arrangement(arr, plan)
    assert "end on komal dha" in revised.sections[2].intent
    assert "PRESERVE: the hook; the main riff's rhythm" in revised.sections[2].intent
    assert "REVISE" not in revised.sections[1].intent             # untargeted: untouched
    assert all("REVISE" not in (s.intent or "") for s in arr.sections)   # original not mutated


def test_only_the_targeted_section_takes_the_new_notes():
    arr = _arr()
    old = _layer("rhythm", 0.0, 16.0, 32.0, swara="S")
    new = _layer("rhythm", 0.0, 16.0, 32.0, swara="g")
    out = splice_layer(arr, RevisionPlan(voice="riff", sections=[1], instruction="x"), old, new)
    assert [(n.start, n.swara) for n in out.notes] == [(0.0, "S"), (16.0, "g"), (32.0, "S")]


def test_multi_layer_voices_splice_role_by_role():
    arr = _arr()
    plan = RevisionPlan(voice="lead", sections=[2], instruction="x")
    old = [_layer("lead", 16.0, 32.0, swara="S")]
    new = [_layer("lead", 16.0, 32.0, swara="m")]
    out = splice_layers(arr, plan, old, new)
    assert [(n.start, n.swara) for n in out[0].notes] == [(16.0, "S"), (32.0, "m")]



def _scores(v: int) -> ProducerScores:
    return ProducerScores(**{k: v for k in ProducerScores.model_fields})


def test_the_same_edit_without_gain_stalls_the_loop():
    arr = _arr()
    taan = RevisionPlan(voice="lead", sections=[2], instruction="vakra, not scalar")
    reworded = RevisionPlan(voice="lead", sections=[2], instruction="less scalar please")
    assert is_stalled(arr, taan, _scores(4), reworded, _scores(4))      # same target, no gain
    assert not is_stalled(arr, taan, _scores(3), reworded, _scores(4))  # it improved — keep going
    assert not is_stalled(arr, None, None, taan, _scores(4))            # the first plan never stalls
    other = RevisionPlan(voice="lead", sections=[1], instruction="vakra")
    assert not is_stalled(arr, taan, _scores(4), other, _scores(4))     # a new target is a new edit

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
