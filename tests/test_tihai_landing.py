"""
Tests for the TIHAI LANDING — the third statement's final note strikes the next sam, the next
section's lead yields to it (a returning mukhada's head wins instead), and a line with no
tripled statement is left as written. Pure, no LLM.

Runs as a script (`uv run python tests/test_tihai_landing.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.contracts import (  # noqa: E402
    ArrangementDraft,
    CompositionBrief,
    Note,
    Section,
    SectionKind,
    build_arrangement,
)
from crew.tihai_landing import LANDING_MAX_BEATS, land_tihais  # noqa: E402

_STATEMENT = [("g", 0.5), ("m", 0.5), ("R", 0.5), ("S", 0.75)]


def _arr(next_role: str | None = "outro"):
    sections = [Section(kind=SectionKind.MELODY, bars=1, layers=["lead", "drone"],
                        foreground="lead", form_role="tihai")]
    if next_role is not None:
        kind = SectionKind.OUTRO if next_role == "outro" else SectionKind.MELODY
        sections.append(Section(kind=kind, bars=1, layers=["lead", "drone"],
                                foreground="lead", form_role=next_role))
    draft = ArrangementDraft(raga="darbari", subgenre="doom", tala="keherwa", bpm=64,
                             motif=["g", "m", "R", "S"], sections=sections)
    return build_arrangement(draft, CompositionBrief())


def _tihai(last_dur: float = 1.5) -> list[Note]:
    """The 2026-10-12 render's tihai: g m R S thrice, 2.5 beats apart, the last Sa stretched
    to the window's end so it struck on matra 7."""
    notes: list[Note] = []
    for j in range(3):
        t = 2.5 * j
        for i, (sw, dur) in enumerate(_STATEMENT):
            last = j == 2 and i == len(_STATEMENT) - 1
            notes.append(Note(swara=sw, start=t, dur=last_dur if last else dur))
            t += dur
    return notes


def test_the_third_statement_lands_on_the_next_sam():
    arr = _arr()
    landed = land_tihais(_tihai(), arr)
    sas = [n for n in landed if n.swara == "S"]
    assert sas[-1].start == arr.beats_per_bar                  # the sam, not matra 7
    assert sas[-1].dur == LANDING_MAX_BEATS


def test_the_tihai_keeps_its_start_and_widens_its_gaps_equally():
    # the first statement stays on its sam; the gaps grow (0.25 -> 1.0) instead of the
    # whole tihai sliding later and leaving dead air before it
    landed = land_tihais(_tihai(), _arr())
    firsts = [n.start for n in landed if n.swara == "g"]
    assert firsts[0] == 0.0
    assert firsts[1] - firsts[0] == firsts[2] - firsts[1] == 3.25
    assert [n.dur for n in landed[:3]] == [n.dur for n in landed[4:7]]


def test_the_next_sections_lead_yields_to_the_landing():
    arr = _arr()
    sam = arr.beats_per_bar
    outro = [Note(swara="m", start=sam, dur=1.0), Note(swara="g", start=sam + 1, dur=1.5),
             Note(swara="R", start=sam + 2.5, dur=2.0)]
    landed = land_tihais(_tihai() + outro, arr)
    after = [n for n in landed if n.start >= sam]
    assert after[0].swara == "S" and after[0].start == sam    # the landing owns the sam
    assert [n.swara for n in after[1:]] == ["g", "R"]          # the covered Ma gave way
    assert after[1].start == sam + 1


def test_a_returning_mukhada_head_is_the_landing():
    arr = _arr("mukhada")
    sam = arr.beats_per_bar
    head = Note(swara="P", start=sam, dur=1.0)
    landed = land_tihais(_tihai() + [head], arr)
    at_sam = [n for n in landed if n.start == sam]
    assert at_sam == [head]                                    # the hook is never displaced
    assert max(n.start + n.dur for n in landed if n.start < sam) == sam


def test_a_closing_tihai_lands_past_the_last_section():
    arr = _arr(None)
    landed = land_tihais(_tihai(), arr)
    assert landed[-1].swara == "S" and landed[-1].start == arr.beats_per_bar


def test_a_line_with_no_tripled_statement_is_left_as_written():
    line = [Note(swara=sw, start=float(i), dur=1.0) for i, sw in enumerate("SRgmPdnS")]
    assert land_tihais(line, _arr()) == line


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
