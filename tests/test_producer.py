"""
Tests for the Producer, the COMPOSITION-QUALITY critic — the CODE side, no LLM (free).

The Producer's verdict is the model's (songwriting craft is not checkable), so what's
testable without an LLM is the plumbing: the renderers that turn the symbolic score into
prompt text (section timeline, subgenre, the riff line WITH power chords/techniques, the
lead, the ensemble), the `assess` control flow over an injected fake judge, and that the
CRITIQUE event carries the 8-criterion rubric. The real graded judgment is exercised live
via `uv run python -m crew.producer`, not here.

Runs as a script (`uv run python tests/test_producer.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.contracts import (  # noqa: E402
    ArrangementDraft,
    Composition,
    CompositionBrief,
    EventType,
    Layer,
    Note,
    ProducerScores,
    ProducerVerdict,
    Section,
    SectionKind,
    build_arrangement,
)
from crew.producer import (  # noqa: E402
    _render_ensemble,
    _render_riff_line,
    _render_sections,
    _render_subgenre,
    assess,
)


def _arr():
    draft = ArrangementDraft(
        raga="darbari", subgenre="doom", tala="teentaal", bpm=72,
        motif=["S", "R", "g", "m", "P"],
        sections=[
            Section(kind=SectionKind.RIFF, bars=1, layers=["rhythm", "drone"],
                    foreground="rhythm", intent="a crushing riff", transition="lift into the taan"),
            Section(kind=SectionKind.TAAN, bars=1, layers=["lead", "rhythm", "drone"],
                    foreground="lead", intent="an expressive lead")])
    return build_arrangement(draft, CompositionBrief(mood="dark"))


def _comp() -> Composition:
    riff = [Note(swara="S", oct=-2, start=0.0, dur=1.0, chord=["S"], technique="palm_mute"),
            Note(swara="g", oct=-2, start=1.0, dur=1.0)]
    lead = [Note(swara=sw, oct=0, start=float(i), dur=1.0) for i, sw in enumerate(["S", "R", "g", "m"])]
    return Composition(
        raga="darbari", sa=62, bpm=72, tala={"name": "teentaal", "beats_per_bar": 16.0},
        layers=[Layer(role="drone", notes=[Note(swara="S", oct=-2, start=0.0, dur=16.0)]),
                Layer(role="rhythm", notes=riff), Layer(role="lead", notes=lead)])


def _scores(**over) -> ProducerScores:
    base = dict(structure=4, dynamics=4, climax=4, motif=4, hook=4,
                balance=4, independence=4, mood_fit=4, repetition=4, performance=4)
    base.update(over)
    return ProducerScores(**base)


def _fake_judge(scores: ProducerScores, notes: str = ""):
    calls: list = []

    def fn(comp, arr):
        calls.append((comp, arr))
        return ProducerVerdict(scores=scores, notes=notes)

    return fn, calls


# --- renderers: the symbolic score -> prompt text ------------------------------

def test_sections_render_the_timeline_with_spotlight_and_transition():
    text = _render_sections(_arr())
    assert "riff" in text and "taan" in text
    assert "spotlight=rhythm" in text and "spotlight=lead" in text
    assert "lift into the taan" in text                 # the transition is shown for the arc


def test_subgenre_names_the_intended_feel():
    text = _render_subgenre(_arr())
    assert "doom" in text.lower() and "72 bpm" in text.replace("~", "")


def test_riff_line_shows_power_chords_and_techniques():
    # the hook criterion needs to SEE the voicing — a chord as +X, a technique as .name
    text = _render_riff_line(_comp(), _arr())
    assert "+S" in text                                 # the power chord
    assert ".palm_mute" in text                         # the technique


def test_riff_line_is_only_the_first_cycle():
    # notes past one cycle (beats_per_bar) are the loop repeat, so they're not shown twice
    arr = _arr()
    comp = Composition(
        raga="darbari", sa=62, bpm=72, tala={"name": "teentaal", "beats_per_bar": 16.0},
        layers=[Layer(role="rhythm", notes=[
            Note(swara="S", oct=-2, start=0.0, dur=1.0),
            Note(swara="g", oct=-2, start=float(arr.beats_per_bar), dur=1.0)])])
    text = _render_riff_line(comp, arr)
    assert text.count("S") == 1 and "g" not in text     # only the within-cycle note


def test_ensemble_reports_voices_and_percussion():
    from crew.contracts import DrumHit
    comp = _comp()
    comp.layers.append(Layer(role="drums", hits=[DrumHit(drum="kick", start=0.0)]))
    text = _render_ensemble(comp)
    assert "lead:" in text and "rhythm:" in text and "drone:" in text
    assert "drums:" in text and "percussion" in text


# --- assess: control flow over an injected judge -------------------------------

def test_assess_streams_every_criterion_as_event_scores():
    verdict, events = assess(_comp(), _arr(),
                             judge_fn=_fake_judge(_scores(motif=2), notes="motif never develops")[0])
    critique = [e for e in events if e.type == EventType.CRITIQUE]
    assert len(critique) == 1
    assert critique[0].agent == "Producer" and critique[0].text == "motif never develops"
    assert set(critique[0].scores) == {"structure", "dynamics", "climax", "motif", "hook",
                                       "balance", "independence", "mood_fit", "repetition",
                                       "performance"}
    assert critique[0].scores["motif"] == 2.0


def test_assess_passes_composition_and_arrangement_to_the_judge():
    fn, calls = _fake_judge(_scores())
    comp, arr = _comp(), _arr()
    assess(comp, arr, judge_fn=fn)
    assert len(calls) == 1 and calls[0][0] is comp and calls[0][1] is arr


def test_scores_are_bounded_1_to_5():
    try:
        ProducerScores(structure=6, dynamics=3, climax=3, motif=3, hook=3,
                       balance=3, independence=3, mood_fit=3, repetition=3, performance=3)
        assert False, "expected a validation error for a score above 5"
    except Exception:
        pass


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
