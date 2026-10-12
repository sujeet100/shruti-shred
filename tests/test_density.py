"""
Tests for DENSITY CONTRAST — swara changes per beat (kan, gestures and meends count; a sway does
not), bursts and whether they breathe, and the report the judges read. Pure, no LLM.

Runs as a script (`uv run python tests/test_density.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))

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
from crew.density import moves_per_beat, profile, render_density  # noqa: E402


def _arr():
    sections = [Section(kind=SectionKind.MELODY, bars=1, layers=["lead", "drone"],
                        foreground="lead", form_role="mukhada")]
    draft = ArrangementDraft(raga="darbari", subgenre="doom", tala="keherwa", bpm=64,
                             motif=["S"], sections=sections)
    return build_arrangement(draft, CompositionBrief())


def _comp(notes: list[Note]) -> Composition:
    lead = Layer(role="lead", instrument="sitar", program=104, channel=2, notes=notes)
    return Composition(raga="darbari", sa=62, bpm=64, layers=[lead],
                       tala={"name": "keherwa", "beats_per_bar": 8.0})


def test_one_stroke_can_carry_several_swara_changes():
    # guruji's bursts are left-hand: kan touches, a gesture out and back, a meend's arrival
    notes = [Note(swara="S", start=0, dur=1),
             Note(swara="g", start=1, dur=1, grace=["R", "m"]),          # R, m, then g
             Note(swara="g", start=2, dur=1, pitch_path=[[0, 0], [100, 2], [300, 0]]),
             Note(swara="R", start=3, dur=1, meend_swara="S")]
    assert moves_per_beat(notes, 4) == [1, 3, 2, 2]


def test_a_sway_is_not_a_swara_change():
    notes = [Note(swara="S", start=0, dur=1), Note(swara="g", start=1, dur=2, andolan=True)]
    assert moves_per_beat(notes, 3) == [1, 1, 0]


def test_a_burst_breathes_when_a_still_beat_follows():
    moves = [1, 4, 3, 0, 2, 2, 5, 2, 2]                       # burst, breath ... burst, no breath
    p = profile(moves, 0, len(moves))
    assert p.bursts == 2 and p.breathed == 1 and p.longest_burst == 2
    assert p.busy_share == round(3 / 9, 3) and p.still_share == round(2 / 9, 3)


def test_an_even_line_has_no_burst():
    p = profile([2, 2, 2, 2, 2, 2, 2, 2], 0, 8)
    assert p.bursts == 0 and p.still_share == 0.0


def test_the_judges_read_each_sections_breathing_against_the_reference():
    notes = [Note(swara="S", start=float(b), dur=1) if b % 2 else
             Note(swara="R", start=float(b), dur=1) for b in range(8)]
    text = render_density(_comp(notes), _arr())
    assert "section 0 (mukhada): 1111 1111" in text and "no burst" in text
    assert "guruji's Darbari gat" in text


def test_rasik_and_the_producer_both_see_it():
    from crew.producer import judge_inputs as producer_inputs
    from crew.rasik import judge_inputs as rasik_inputs
    comp, arr = _comp([Note(swara="S", start=0, dur=8)]), _arr()
    assert "how the lead BREATHES" in rasik_inputs(comp, "", arr)["motion"]
    assert "how the lead BREATHES" in producer_inputs(comp, arr)["metrics"]


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
