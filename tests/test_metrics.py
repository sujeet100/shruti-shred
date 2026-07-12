"""
Tests for crew/metrics.py — the FACTS the Producer reasons over. All pure (no LLM).

These are the "code measures" half of "code measures, the LLM evaluates": every number
the Producer is grounded in is computed here deterministically, so it must be exactly
right. A controlled three-section piece (a quiet intro, a full-band peak, a bare outro)
lets us assert the dynamics curve, the peak/resolution, and the arrangement ratios.

Runs as a script (`uv run python tests/test_metrics.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

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
from crew.metrics import (  # noqa: E402
    composition_metrics,
    render_metrics,
)

# teentaal -> 16-beat cycles, so 3 one-bar sections span [0,16) [16,32) [32,48).
_MOTIF = ["S", "R", "g"]


def _arr():
    draft = ArrangementDraft(
        raga="darbari", subgenre="doom", tala="teentaal", bpm=72, motif=_MOTIF,
        sections=[
            Section(kind=SectionKind.ALAAP, bars=1, layers=["drone"], foreground="drone"),
            Section(kind=SectionKind.SOLO, bars=1, layers=["lead", "rhythm", "drone"],
                    foreground="lead"),
            Section(kind=SectionKind.OUTRO, bars=1, layers=["drone"], foreground="drone")])
    return build_arrangement(draft, CompositionBrief(mood="dark"))


def _comp(*, lead_oct: int = 0):
    """A drone sustaining the whole piece; a rhythm riff and a lead only in the SOLO
    section (beats 16..32) — so the middle section is the energetic peak."""
    drone = [Note(swara="S", oct=-2, start=0.0, dur=48.0)]
    rhythm = [Note(swara=sw, oct=-2, start=16.0 + i, dur=1.0, vel=110)
              for i, sw in enumerate(["S", "g", "S", "g"])]
    lead = [Note(swara=sw, oct=lead_oct, start=16.0 + i, dur=1.0, vel=100)
            for i, sw in enumerate(["S", "R", "g", "m"])]
    return Composition(
        raga="darbari", sa=62, bpm=72, tala={"name": "teentaal", "beats_per_bar": 16.0},
        layers=[Layer(role="drone", notes=drone),
                Layer(role="rhythm", notes=rhythm),
                Layer(role="lead", notes=lead)])


# --- the dynamics curve + arc --------------------------------------------------

def test_energy_curve_has_one_row_per_section_with_the_kinds():
    m = composition_metrics(_comp(), _arr())
    assert [r.kind for r in m.energy] == ["alaap", "solo", "outro"]


def test_sustained_drone_is_active_in_every_section_it_covers():
    # the drone's single note starts at beat 0 but sustains to 48 — active in all 3
    m = composition_metrics(_comp(), _arr())
    assert m.energy[0].active_voices == 1                 # alaap: drone only
    assert m.energy[1].active_voices == 3                 # solo: drone + rhythm + lead
    assert m.energy[2].active_voices == 1                 # outro: drone still sustaining


def test_peak_is_the_solo_and_it_resolves():
    m = composition_metrics(_comp(), _arr())
    assert m.peak_index == 1                              # the full-band solo is the peak
    assert m.resolves is True                             # energy falls into the outro
    assert m.is_flat is False


def test_a_flat_piece_is_flagged():
    # each section identical — one drone attack per section, same voice/velocity -> no arc
    arr = _arr()
    drone = [Note(swara="S", oct=-2, start=float(s), dur=16.0, vel=100) for s in (0, 16, 32)]
    comp = Composition(raga="darbari", sa=62, bpm=72,
                       tala={"name": "teentaal", "beats_per_bar": 16.0},
                       layers=[Layer(role="drone", notes=drone)])
    m = composition_metrics(comp, arr)
    assert [r.energy for r in m.energy] == [m.energy[0].energy] * 3   # identical rows
    assert m.is_flat is True


# --- motif / independence / balance -------------------------------------------

def test_motif_share_is_the_leads_fraction_drawn_from_the_motif():
    # lead swaras S R g m; motif {S,R,g} -> 3 of 4 are motif notes
    m = composition_metrics(_comp(), _arr())
    assert m.motif_share == 0.75


def test_lead_riff_overlap_measures_doubling():
    # lead distinct {S,R,g,m}; riff distinct {S,g} -> 2/4 of the lead's notes are in the riff
    m = composition_metrics(_comp(), _arr())
    assert m.lead_riff_overlap == 0.5


def test_no_register_overlap_when_voices_sit_in_distinct_octaves():
    # lead at oct 0, rhythm at oct -2 -> no shared octave band
    m = composition_metrics(_comp(lead_oct=0), _arr())
    assert m.register_overlaps == []


def test_register_overlap_flagged_when_lead_drops_into_the_riff_octave():
    m = composition_metrics(_comp(lead_oct=-2), _arr())
    assert ("lead", "rhythm") in m.register_overlaps


def test_always_on_fraction_counts_full_sections():
    # only the solo has all three present voices playing -> 1 of 3 sections
    m = composition_metrics(_comp(), _arr())
    assert m.always_on_fraction == round(1 / 3, 3)


# --- rendering -----------------------------------------------------------------

def test_render_metrics_surfaces_the_curve_and_ratios():
    text = render_metrics(composition_metrics(_comp(), _arr()))
    assert "dynamics curve" in text and "solo:" in text
    assert "resolves afterwards" in text
    assert "motif_share" in text and "75%" in text
    assert "lead/riff overlap" in text


def test_render_metrics_handles_an_empty_piece():
    arr = _arr()
    comp = Composition(raga="darbari", sa=62, bpm=72,
                       tala={"name": "teentaal", "beats_per_bar": 16.0},
                       layers=[Layer(role="drone", notes=[])])
    text = render_metrics(composition_metrics(comp, arr))
    assert isinstance(text, str) and "dynamics curve" in text


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
