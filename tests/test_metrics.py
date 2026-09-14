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
    _riff_form,
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


def test_motif_recurrence_counts_sections_that_restate_the_motif():
    # the motif S R g appears contiguously only in the solo lead (S R g m) -> 1 of 3 sections
    m = composition_metrics(_comp(), _arr())
    assert m.motif_recurrence == round(1 / 3, 3)


def test_section_variety_is_one_when_every_kind_is_distinct():
    m = composition_metrics(_comp(), _arr())          # alaap, solo, outro — all distinct
    assert m.section_variety == 1.0


def test_section_variety_drops_when_a_kind_repeats():
    draft = ArrangementDraft(
        raga="darbari", subgenre="doom", tala="teentaal", bpm=72, motif=_MOTIF,
        sections=[
            Section(kind=SectionKind.RIFF, bars=1, layers=["rhythm", "drone"], foreground="rhythm"),
            Section(kind=SectionKind.SOLO, bars=1, layers=["lead", "drone"], foreground="lead"),
            Section(kind=SectionKind.RIFF, bars=1, layers=["rhythm", "drone"], foreground="rhythm")])
    arr = build_arrangement(draft, CompositionBrief(mood="dark"))
    m = composition_metrics(_comp(), arr)
    assert m.section_variety == round(2 / 3, 3)        # riff recurs -> 2 distinct of 3


def test_bass_riff_overlap_measures_a_bass_that_tracks_the_riff():
    # bass plays {S}; riff distinct {S, g} -> all of the bass's notes are in the riff
    comp = Composition(
        raga="darbari", sa=62, bpm=72, tala={"name": "teentaal", "beats_per_bar": 16.0},
        layers=[Layer(role="rhythm", notes=[Note(swara="S", oct=-2, start=0.0, dur=1.0),
                                            Note(swara="g", oct=-2, start=1.0, dur=1.0)]),
                Layer(role="bass", notes=[Note(swara="S", oct=-3, start=0.0, dur=2.0)])])
    m = composition_metrics(comp, _arr())
    assert m.bass_riff_overlap == 1.0


def test_drums_tabla_overlap_measures_lockstep_percussion():
    from crew.contracts import DrumHit
    comp = Composition(
        raga="darbari", sa=62, bpm=72, tala={"name": "teentaal", "beats_per_bar": 16.0},
        layers=[Layer(role="drums", hits=[DrumHit(drum="kick", start=0.0),
                                          DrumHit(drum="snare", start=1.0),
                                          DrumHit(drum="kick", start=2.0)]),
                Layer(role="tabla", hits=[DrumHit(drum="tabla_lo", start=0.0),
                                          DrumHit(drum="tabla_hi", start=2.0),
                                          DrumHit(drum="tabla_hi", start=4.0)])])
    m = composition_metrics(comp, _arr())
    assert m.drums_tabla_overlap == round(2 / 3, 3)    # tabla at 0 and 2 land on a kit hit


def test_ornament_rate_is_per_section_over_the_pitched_notes():
    arr = _arr()
    drone = [Note(swara="S", oct=-2, start=0.0, dur=48.0)]        # onset only in the alaap
    lead = [Note(swara="S", oct=0, start=16.0, dur=1.0, grace=["R"]),   # ornamented
            Note(swara="g", oct=0, start=17.0, dur=1.0, meend_swara="m"),     # ornamented
            Note(swara="m", oct=0, start=18.0, dur=1.0)]               # plain
    comp = Composition(
        raga="darbari", sa=62, bpm=72, tala={"name": "teentaal", "beats_per_bar": 16.0},
        layers=[Layer(role="drone", notes=drone), Layer(role="lead", notes=lead)])
    m = composition_metrics(comp, arr)
    assert m.energy[0].ornament_rate == 0.0            # alaap: just the plain drone onset
    assert m.energy[1].ornament_rate == round(2 / 3, 3)  # solo: 2 of 3 lead notes ornamented


# --- riff form: the main riff returning (slots) --------------------------------

def _arr_slots(*specs: tuple[SectionKind, str | None]):
    """An arrangement of rhythm-active sections (ALAAP is lead-only), one per (kind, slot)."""
    sections = []
    for kind, slot in specs:
        layers = ["lead", "drone"] if kind == SectionKind.ALAAP else ["rhythm", "drone"]
        fg = "rhythm" if "rhythm" in layers else "lead"
        sections.append(Section(kind=kind, bars=1, layers=layers, foreground=fg, riff_slot=slot))
    draft = ArrangementDraft(raga="darbari", subgenre="doom", tala="teentaal", bpm=72,
                             motif=_MOTIF, sections=sections)
    return build_arrangement(draft, CompositionBrief(mood="dark"))


def test_riff_form_counts_slots_and_measures_recurrence():
    # main x3, chorus x1, breakdown x1 -> 5 rhythm sections, 3 distinct riffs
    arr = _arr_slots((SectionKind.RIFF, "main"), (SectionKind.MELODY, "chorus"),
                     (SectionKind.RIFF, "main"), (SectionKind.BREAKDOWN, "breakdown"),
                     (SectionKind.RIFF, "main"))
    recurrence, variety, slots = _riff_form(arr)
    assert slots == [("main", 3), ("chorus", 1), ("breakdown", 1)]
    assert recurrence == round(2 / 5, 3)   # 5 sections - 3 distinct riffs = 2 reprises
    assert variety == round(3 / 5, 3)


def test_riff_form_default_slot_is_the_kind():
    # two RIFF sections with no explicit slot share the "riff" slot -> reuse
    arr = _arr_slots((SectionKind.RIFF, None), (SectionKind.RIFF, None))
    recurrence, variety, slots = _riff_form(arr)
    assert slots == [("riff", 2)] and recurrence == 0.5 and variety == 0.5


def test_riff_form_ignores_non_rhythm_sections():
    arr = _arr_slots((SectionKind.ALAAP, None), (SectionKind.RIFF, "main"))
    _, _, slots = _riff_form(arr)
    assert slots == [("main", 1)]          # the lead-only alaap is not a riff section


def test_riff_form_all_distinct_has_no_recurrence():
    arr = _arr_slots((SectionKind.RIFF, "main"), (SectionKind.BREAKDOWN, "breakdown"))
    recurrence, variety, _ = _riff_form(arr)
    assert recurrence == 0.0 and variety == 1.0


def test_composition_metrics_exposes_riff_form():
    arr = _arr_slots((SectionKind.RIFF, "main"), (SectionKind.RIFF, "main"))
    m = composition_metrics(_comp(), arr)
    assert m.riff_recurrence == 0.5 and m.riff_slots == [("main", 2)]


# --- rendering -----------------------------------------------------------------

def test_render_metrics_surfaces_the_curve_and_ratios():
    text = render_metrics(composition_metrics(_comp(), _arr()))
    assert "dynamics curve" in text and "solo:" in text
    assert "resolves afterwards" in text
    assert "motif_share" in text and "75%" in text
    assert "motif_recurrence" in text and "section_variety" in text
    assert "ornament rate per section" in text
    assert "lead/riff overlap" in text and "bass/riff overlap" in text


def test_render_metrics_includes_riff_form():
    arr = _arr_slots((SectionKind.RIFF, "main"), (SectionKind.MELODY, "chorus"),
                     (SectionKind.RIFF, "main"))
    text = render_metrics(composition_metrics(_comp(), arr))
    assert "riff form" in text and "mainx2" in text
    assert "riff_recurrence" in text and "riff_variety" in text


def test_render_metrics_handles_an_empty_piece():
    arr = _arr()
    comp = Composition(raga="darbari", sa=62, bpm=72,
                       tala={"name": "teentaal", "beats_per_bar": 16.0},
                       layers=[Layer(role="drone", notes=[])])
    text = render_metrics(composition_metrics(comp, arr))
    assert isinstance(text, str) and "dynamics curve" in text


# --- performance: what the score DOES, not what it says -----------------------

def test_a_muted_wall_reads_as_no_ring_and_all_chug():
    """The failure nobody could hear: a rhythm guitar that never rings is a string of clicks,
    and no compositional criterion notices."""
    from crew.metrics import _flat_chug_runs, _ring_share
    chugs = [Note(swara="S", oct=-2, start=i * 0.5, dur=0.5, vel=100, technique="palm_mute")
             for i in range(8)]
    assert _ring_share(chugs) == 0.0
    assert _flat_chug_runs(chugs) == 1           # eight chugs at one velocity: a machine


def test_an_accented_chug_run_is_not_flagged():
    from crew.metrics import _flat_chug_runs
    accented = [Note(swara="S", oct=-2, start=i * 0.5, dur=0.5, vel=v, technique="palm_mute")
                for i, v in enumerate((112, 92, 100, 92, 112, 92))]
    assert _flat_chug_runs(accented) == 0


def test_an_open_chord_rings_but_a_long_palm_mute_does_not():
    """A mute damps, so it cannot ring however long it is written — the distinction the
    fixed-gate renderer used to erase."""
    from crew.metrics import _ring_share
    assert _ring_share([Note(swara="S", oct=-2, start=0.0, dur=2.0, vel=100)]) == 1.0
    assert _ring_share([Note(swara="S", oct=-2, start=0.0, dur=2.0, vel=100,
                             technique="palm_mute")]) == 0.0


def test_silence_share_measures_hollowness_without_double_counting_chords():
    """Chord tones sound together, so counting their durations separately would report a
    dense section as fuller than real time allows."""
    from crew.metrics import _silence_share
    chord = [Note(swara="S", oct=-2, start=0.0, dur=1.0, vel=100),
             Note(swara="P", oct=-2, start=0.0, dur=1.0, vel=100),
             Note(swara="S", oct=-2, start=3.0, dur=1.0, vel=100)]
    assert _silence_share(chord) == 0.5          # 2 beats sounding across a 4-beat span


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
