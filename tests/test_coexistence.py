"""
Tests for crew/coexistence.py — does the riff coexist with the melody? All pure (no LLM).

This is the detection half of "code decides the checkable, the LLM decides the rest": the
arithmetic here must be exactly right, because an arranger pass will spend tokens only on
what it flags, and will repair what it names. Darbari (komal g/d, komal n) gives real harsh
intervals to assert against: g over S is ic 3 (fine), but S under a held g is ic 9... so the
fixtures pick pairs deliberately — n (11) over S is a major seventh, M (6) over S a tritone,
r (1) over S a semitone.

Runs as a script (`uv run python tests/test_coexistence.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.coexistence import (  # noqa: E402
    LeadStability,
    coexistence_report,
    render_coexistence,
)
from crew.contracts import (  # noqa: E402
    ArrangementDraft,
    Composition,
    CompositionBrief,
    Layer,
    Note,
    Section,
    SectionKind,
    build_arrangement,
)

_MOTIF = ["S", "g", "m", "P"]


def _arr(bars: int = 1):
    """One SOLO section of `bars` cycles — lead and rhythm both playing, which is the
    only configuration where the question 'do these coexist?' even arises."""
    draft = ArrangementDraft(
        raga="bhairavi", subgenre="doom", tala="teentaal", bpm=72, motif=_MOTIF,
        sections=[Section(kind=SectionKind.SOLO, bars=bars,
                          layers=["lead", "rhythm"], foreground="lead")])
    return build_arrangement(draft, CompositionBrief(mood="dark"))


def _comp(riff: list[Note], lead: list[Note], *, double: bool = False) -> Composition:
    layers = [Layer(role="lead", notes=lead), Layer(role="rhythm", notes=riff)]
    if double:                       # the hard-right take: same performance, detuned
        layers.append(Layer(role="rhythm", detune_cents=8,
                            notes=[n.model_copy(update={"start": n.start + 0.02}) for n in riff]))
    return Composition(raga="bhairavi", sa=62, bpm=72,
                       tala={"name": "teentaal", "beats_per_bar": 16.0}, layers=layers)


# --- grinds: a harsh interval under a SETTLED melody note ----------------------

def test_a_semitone_under_a_held_melody_note_is_a_grind():
    # riff sits on r; the melody holds S above it for two beats -> ic 1
    report = coexistence_report(
        _comp(riff=[Note(swara="r", oct=-2, start=0.0, dur=1.0)],
              lead=[Note(swara="S", oct=0, start=0.0, dur=2.0)]), _arr())
    (section,) = report.sections
    (grind,) = section.grinds
    assert grind.interval_class == 1 and grind.stability is LeadStability.HELD
    assert grind.riff_swara == "r" and grind.lead_swara == "S" and not grind.from_chord
    assert not report.clean and report.flagged == (section,)


def test_the_same_interval_under_a_passing_note_is_not_reported():
    """A fast line over a static chug is ordinary metal — flagging it would flatten the
    music, so it is counted as context and never becomes a finding."""
    report = coexistence_report(
        _comp(riff=[Note(swara="r", oct=-2, start=0.0, dur=1.0)],
              lead=[Note(swara="S", oct=0, start=0.0, dur=0.25)]), _arr())
    (section,) = report.sections
    assert section.grinds == () and section.passing_grinds == 1 and section.clean


def test_a_chord_tone_grinds_even_when_its_root_does_not():
    """The renderer seats a chord tone consonantly against its ROOT and never against the
    melody, so a stack can fight the tune where the struck root is clean."""
    report = coexistence_report(
        _comp(riff=[Note(swara="S", oct=-2, start=0.0, dur=1.0, chord=["M"])],
              lead=[Note(swara="S", oct=0, start=0.0, dur=2.0)]), _arr())
    (grind,) = report.sections[0].grinds
    assert grind.from_chord and grind.riff_swara == "M" and grind.interval_class == 6


def test_a_meend_is_judged_where_it_LANDS():
    """The bug this module fixed in the old guard: the renderer sounds a meend at its
    TARGET, so a note written as S that glides to r must be judged as r."""
    riff = [Note(swara="S", oct=-2, start=0.0, dur=1.0)]
    # written as S (unison with the riff — nothing to report) but GLIDING to r, which the
    # renderer actually sounds: S under r is a major seventh.
    glides = coexistence_report(
        _comp(riff, lead=[Note(swara="S", oct=0, start=0.0, dur=2.0,
                              meend_swara="r", meend_oct=0)]), _arr())
    (grind,) = glides.sections[0].grinds
    assert grind.interval_class == 11, "judged against the written swara, not the sounding one"
    # ...and without the glide the very same pair is clean, which is what made the old
    # guard's written-swara comparison invisible.
    assert coexistence_report(
        _comp(riff, lead=[Note(swara="S", oct=0, start=0.0, dur=2.0)]), _arr()).clean


def test_consonant_voices_are_clean():
    report = coexistence_report(
        _comp(riff=[Note(swara="S", oct=-2, start=0.0, dur=1.0, chord=["P"])],
              lead=[Note(swara="P", oct=0, start=0.0, dur=2.0)]), _arr())
    assert report.clean
    assert render_coexistence(report).startswith("COEXISTENCE: the riff and the melody coexist")


def test_the_double_track_does_not_double_the_findings():
    """The second take is the same performance nudged late and detuned — counting it would
    report every clash twice and make a section look twice as broken as it is."""
    riff = [Note(swara="r", oct=-2, start=0.0, dur=1.0)]
    lead = [Note(swara="S", oct=0, start=0.0, dur=2.0)]
    assert len(coexistence_report(_comp(riff, lead, double=True).model_copy(), _arr())
               .sections[0].grinds) == 1


def test_a_percussive_touch_is_not_a_clash():
    """A short unchorded chug is over before the ear tunes it — which is precisely what the
    deterministic damp produces, so a repaired note must stop being reported as broken."""
    from crew.contracts import Note as N
    touch = N(swara="r", oct=-2, start=0.0, dur=0.5, technique="palm_mute")
    report = coexistence_report(
        _comp(riff=[touch], lead=[Note(swara="S", oct=0, start=0.0, dur=2.0)]), _arr())
    assert report.clean
    # ...but the same pitch left RINGING under the same note still is
    ringing = touch.model_copy(update={"dur": 2.0, "technique": None})
    assert not coexistence_report(
        _comp(riff=[ringing], lead=[Note(swara="S", oct=0, start=0.0, dur=2.0)]), _arr()).clean


# --- chases: harmony moving because the melody moved --------------------------

def test_a_root_change_under_a_moving_melody_is_a_chase():
    riff = [Note(swara="S", oct=-2, start=0.0, dur=1.0),
            Note(swara="m", oct=-2, start=1.0, dur=1.0)]
    lead = [Note(swara="P", oct=0, start=t / 4, dur=0.25) for t in range(8)]
    (chase,) = coexistence_report(_comp(riff, lead), _arr()).sections[0].chases
    assert chase.beat == 1.0 and chase.from_swara == "S" and chase.to_swara == "m"


def test_a_root_change_at_a_settled_melody_note_is_allowed():
    """Harmony SHOULD change at an arrival — that is the difference between supporting the
    melody and chasing it."""
    riff = [Note(swara="S", oct=-2, start=0.0, dur=1.0),
            Note(swara="m", oct=-2, start=1.0, dur=1.0)]
    lead = [Note(swara="m", oct=0, start=0.0, dur=2.0)]
    assert coexistence_report(_comp(riff, lead), _arr()).sections[0].chases == ()


def test_repeating_the_same_root_never_chases():
    riff = [Note(swara="S", oct=-2, start=float(i), dur=1.0) for i in range(4)]
    lead = [Note(swara="P", oct=0, start=t / 4, dur=0.25) for t in range(16)]
    assert coexistence_report(_comp(riff, lead), _arr()).sections[0].chases == ()


# --- the report as an arranger pass reads it ----------------------------------

def test_findings_are_attributed_to_their_section():
    """A repair is surgical, so a finding is useless without knowing which section owns it."""
    riff = [Note(swara="S", oct=-2, start=0.0, dur=1.0),      # section 0: clean
            Note(swara="r", oct=-2, start=16.0, dur=1.0)]     # section 1: grinds
    lead = [Note(swara="S", oct=0, start=0.0, dur=32.0)]
    draft = ArrangementDraft(
        raga="bhairavi", subgenre="doom", tala="teentaal", bpm=72, motif=_MOTIF,
        sections=[Section(kind=SectionKind.RIFF, bars=1, layers=["lead", "rhythm"],
                          foreground="rhythm"),
                  Section(kind=SectionKind.SOLO, bars=1, layers=["lead", "rhythm"],
                          foreground="lead")])
    report = coexistence_report(_comp(riff, lead),
                                build_arrangement(draft, CompositionBrief(mood="dark")))
    assert report.sections[0].clean and not report.sections[1].clean
    assert len(report.flagged) == 1 and report.flagged[0].index == 1
    text = render_coexistence(report)
    assert "section 1" in text and "semitone" in text and "section 0" not in text


def test_an_empty_piece_reports_clean_rather_than_crashing():
    comp = Composition(raga="bhairavi", sa=62, bpm=72,
                       tala={"name": "teentaal", "beats_per_bar": 16.0}, layers=[])
    assert coexistence_report(comp, _arr()).clean


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
