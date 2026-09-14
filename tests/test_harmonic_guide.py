"""
Tests for crew/harmonic_guide.py — the ONE answer to "what is the melody doing here?", read
by every accompanying voice. All pure (no LLM).

The failure this prevents is assembled entirely out of correct decisions: the clean guitar,
the orchestra and the riff each pick a LEGAL sustained tone, independently, and the piece
ends up holding a cluster nobody designed. So what must be proven is that the guide reads the
melody honestly, that it only ever speaks about sustained tones, and above all that it can
never silence a voice — a pad that drops out is a worse answer than a pad with one colour.

Runs as a script (`uv run python tests/test_harmonic_guide.py`) or under pytest.
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
    HarmonyPlan,
    Section,
    SectionKind,
    build_arrangement,
)
from crew.harmonic_guide import (  # noqa: E402
    avoided_at,
    harmonic_guide,
    supported,
)
from crew.harmony import bar_voicings  # noqa: E402
from raga import SWARAS  # noqa: E402


def _arr(sections: int = 1):
    draft = ArrangementDraft(
        raga="kirwani", subgenre="doom", tala="teentaal", bpm=72, motif=["S", "g"],
        sections=[Section(kind=SectionKind.MELODY, bars=1, layers=["lead", "clean"],
                          foreground="lead") for _ in range(sections)])
    return build_arrangement(draft, CompositionBrief(mood="dark"))


def _lead(notes: list[Note]) -> list[Layer]:
    return [Layer(role="lead", notes=notes)]


def test_the_guide_reads_what_the_melody_SETTLES_on():
    guide = harmonic_guide(_lead([Note(swara="g", oct=0, start=0.0, dur=4.0)]), _arr())
    assert guide[0].focus == ("g",)
    # a semitone, a tritone and a major seventh from komal ga must not sustain under it
    for swara in guide[0].avoid:
        assert (SWARAS[swara] - SWARAS["g"]) % 12 in (1, 6, 11)


def test_passing_notes_do_not_set_the_harmony():
    """A fast line is movement, not a harmonic instruction — letting every eighth note steer
    the floor is how accompaniment starts chasing the tune."""
    runs = [Note(swara=s, oct=0, start=i * 0.25, dur=0.25)
            for i, s in enumerate(["S", "g", "m", "P", "d", "N", "S", "g"])]
    assert harmonic_guide(_lead(runs), _arr())[0].focus == ()


def test_a_meend_counts_where_it_LANDS():
    glide = [Note(swara="S", oct=0, start=0.0, dur=4.0, meend_swara="m", meend_oct=0)]
    assert harmonic_guide(_lead(glide), _arr())[0].focus == ("m",)


def test_the_most_sustained_note_leads_the_focus():
    notes = [Note(swara="P", oct=0, start=0.0, dur=1.0),
             Note(swara="g", oct=0, start=1.0, dur=3.0)]
    assert harmonic_guide(_lead(notes), _arr())[0].focus[0] == "g"


def test_each_section_gets_its_own_window():
    arr = _arr(2)
    notes = [Note(swara="g", oct=0, start=0.0, dur=8.0),
             Note(swara="P", oct=0, start=16.0, dur=8.0)]
    guide = harmonic_guide(_lead(notes), arr)
    assert [w.focus for w in guide] == [("g",), ("P",)]
    assert avoided_at(guide, 0.0) != avoided_at(guide, 16.0)


# --- the filter: it removes colours, it never removes a voice ------------------

def test_filtering_drops_only_the_tones_that_fight():
    assert supported(["S", "P", "g"], frozenset({"g"})) == ["S", "P"]


def test_filtering_never_empties_a_voice():
    """A pad that drops out is a worse answer than a pad holding one tone, so when every
    choice grinds the ground survives."""
    assert supported(["S", "g"], frozenset({"S", "g"})) == ["S"]
    assert supported(["g", "m"], frozenset({"g", "m"})) == ["g"]


def test_filtering_preserves_order():
    """This removes colours; it does not re-voice the part."""
    assert supported(["P", "S", "m"], frozenset({"S"})) == ["P", "m"]


def test_no_guide_means_no_opinion():
    """An absent guide must never silence a voice — every caller without a lead to read
    behaves exactly as it did before."""
    assert avoided_at((), 4.0) == frozenset()
    assert supported(["S", "g"], avoided_at((), 4.0)) == ["S", "g"]


# --- the voices actually read it ----------------------------------------------

def test_the_clean_guitar_drops_a_colour_that_grinds():
    """The composers pick these colours before the lead exists, so they cannot know what the
    melody will settle on — the guide is what lets the choice survive contact with it."""
    section = Section(kind=SectionKind.MELODY, bars=1, layers=["lead", "clean"],
                      foreground="lead",
                      harmony=HarmonyPlan(mode="modal_pedal", roots=["g", "P"]))
    plain = {sw for bar in bar_voicings(section, "kirwani") for sw, _ in bar}
    filtered = {sw for bar in bar_voicings(section, "kirwani", avoid=frozenset({"g"}))
                for sw, _ in bar}
    assert "g" in plain and "g" not in filtered
    assert filtered, "a filtered voicing is never empty"


def test_the_clean_guitar_still_plays_when_every_colour_grinds():
    section = Section(kind=SectionKind.MELODY, bars=1, layers=["lead", "clean"],
                      foreground="lead",
                      harmony=HarmonyPlan(mode="modal_pedal", roots=["g"]))
    assert all(bar for bar in bar_voicings(section, "kirwani", avoid=frozenset({"g"})))


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
