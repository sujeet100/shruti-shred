"""
Tests for the TAAN REPORT (2026-10-12) — the Producer's evidence on the climax: where the peak
lands, whether the run gathers speed, any gap before the sam, the arrival on the returning head,
and a tripled closing statement. Pure, no LLM.

Runs as a script (`uv run python tests/test_taan_report.py`) or under pytest.
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
from crew.generators import VOICES  # noqa: E402
from crew.taan_report import render_taan, taan_facts  # noqa: E402

_BAND = ["lead", "rhythm", "drums", "drone"]


def _arr():
    draft = ArrangementDraft(
        raga="darbari", subgenre="doom", tala="teentaal", bpm=120, motif=["g", "m", "R", "S"],
        sections=[Section(kind=SectionKind.TAAN, bars=1, layers=list(_BAND), foreground="lead",
                          riff_slot="main", form_role="taan_long"),
                  Section(kind=SectionKind.MELODY, bars=1, layers=list(_BAND), foreground="lead",
                          riff_slot="main", form_role="mukhada")])
    return build_arrangement(draft, CompositionBrief(sa=62))


def _comp(arr, taan: list[tuple[str, int, float]]) -> Composition:
    v = VOICES["sitar"]
    notes, t = [], 0.0
    for sw, octave, dur in taan:
        notes.append(Note(swara=sw, oct=octave, start=t, dur=dur))
        t += dur
    notes.append(Note(swara="R", oct=0, start=16.0, dur=4.0))       # the returning head on Re
    lead = Layer(role="lead", instrument=v.instrument, program=v.program, channel=v.channel,
                 notes=notes)
    return Composition(raga=arr.raga, sa=arr.sa, bpm=arr.bpm,
                       tala={"name": arr.tala, "beats_per_bar": arr.beats_per_bar}, layers=[lead])


def test_an_early_peak_a_thinning_run_a_gap_and_a_tihai_are_all_reported():
    # the 213455 shape: up to the top early, then down, the closing cell thrice, stopping short
    early = ([("S", 0, 0.25), ("R", 0, 0.25), ("g", 0, 0.25), ("m", 0, 0.25), ("P", 0, 0.25),
              ("n", 0, 0.25), ("S", 1, 0.25), ("R", 1, 0.25)]
             + [(sw, 0, 1.0) for sw in ("n", "P", "m", "g", "m", "g", "R", "S")]
             + [("g", 0, 1.0), ("R", 0, 0.5), ("S", 0, 0.5)] * 3)          # 16 beats
    arr = _arr()
    [facts] = taan_facts(_comp(arr, early[:-1]), arr)            # its last note dropped: a gap
    assert facts.peak == "R'" and facts.peak_at < 0.15
    assert facts.density_second < facts.density_first
    assert facts.gap_beats == 0.5
    [whole] = taan_facts(_comp(arr, early), arr)
    assert whole.tihai and "ENDS ON A TIHAI" in render_taan(_comp(arr, early), arr)


def test_a_late_peak_that_runs_into_the_head_reads_well():
    late = ([(sw, 0, 1.0) for sw in ("S", "R", "g", "m", "R", "S", "n", "S",
                                     "g", "m", "R", "S")]
            + [("d", 0, 0.25), ("n", 0, 0.25), ("S", 1, 0.25), ("R", 1, 0.25)] * 2
            + [("g", 1, 0.25), ("R", 1, 0.25), ("S", 1, 0.25), ("n", 0, 0.25),
               ("P", 0, 0.25), ("m", 0, 0.25), ("g", 0, 0.25), ("S", 0, 0.25)])
    arr = _arr()
    [facts] = taan_facts(_comp(arr, late), arr)
    assert facts.peak == "g'" and facts.peak_at > 0.7
    assert facts.density_second > facts.density_first
    assert facts.gap_beats == 0.0 and facts.arrival_steps == 1 and not facts.tihai


def test_held_notes_that_stall_the_run_are_measured():
    # the 233435 shape: fast clusters joined by held notes (2026-10-13 review)
    stop_start = ([("S", 0, 0.25)] * 4 + [("m", 0, 2.0)] + [("g", 0, 0.25)] * 4 + [("P", 0, 1.0)]
                  + [("d", 0, 0.5)] * 8 + [("S", 1, 2.0)] + [("n", 0, 0.5)] * 4 + [("S", 0, 3.0)])
    arr = _arr()
    [facts] = taan_facts(_comp(arr, stop_start), arr)
    assert facts.stalls == 3                                 # m, P and taar S stop the run
    assert facts.held_share == 0.5                           # 8 of its 16 beats sit on held notes
    assert "3 mid-run hold(s)" in render_taan(_comp(arr, stop_start), arr)
    flowing = [("S", 0, 0.5)] * 8 + [("R", 0, 0.25)] * 48
    [smooth] = taan_facts(_comp(arr, flowing), arr)
    assert smooth.stalls == 0 and smooth.held_share == 0.0


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
