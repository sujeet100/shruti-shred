"""
Tests for src/chalan.py — how a raga MOVES, measured. All pure (no LLM).

The distinction these encode: `raga.py` answers "is this swara allowed?", which is only half
of what a raga is. Bageshree shares its scale with Bhimpalasi, so a line can use nothing but
legal Bageshree notes and stop sounding like Bageshree the moment it walks the ladder. What
must be provable here is that the measures see MOVEMENT — a step of the raga's own ladder, a
turn, a recognisable ang — and not membership.

Runs as a script (`uv run python tests/test_chalan.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from chalan import (  # noqa: E402
    ang_coverage,
    angs,
    direction_change_share,
    ladder,
    longest_scalar_run,
    motion_report,
)
from raga import RAGAS  # noqa: E402


def _line(swaras: str) -> list[tuple[str, int]]:
    return [(s, 0) for s in swaras]


def test_a_step_is_a_step_of_THIS_ragas_ladder():
    """A raga's step is a rung of its own ladder, not a semitone: in a pentatonic raga a minor
    third IS adjacent, and calling it a leap would make every Malkauns phrase look disjunct."""
    assert ladder("malkauns") == ["S", "g", "m", "d", "n"]
    assert longest_scalar_run(_line("Sgmdn"), "malkauns") == 5      # walks the whole ladder
    assert ladder("bageshree") == ["S", "R", "g", "m", "P", "D", "n"]


def test_a_ladder_walk_is_caught_and_a_zigzag_is_not():
    assert longest_scalar_run(_line("SRgmP"), "bageshree") == 5
    assert longest_scalar_run(_line("SgSgS"), "bageshree") == 1     # every move skips a rung
    assert longest_scalar_run(_line("mDnDm"), "bageshree") == 2     # the pakad's own turn


def test_direction_changes_measure_the_vakra_character():
    assert direction_change_share(_line("SRgmP"), "bageshree") == 0.0        # never turns
    # m D n D m rises to n and falls back: one turn in three moves — the pakad's own arch
    assert direction_change_share(_line("mDnDm"), "bageshree") == 0.333
    # ...against a line that reverses on every move
    assert direction_change_share(_line("SgSgS"), "bageshree") == 1.0


def test_angs_are_the_ragas_own_phrases_and_their_fragments():
    """Knowledge, not new facts: the angs come from the pakad and chalan already encoded and
    source-verified — this only reads them as movements."""
    library = angs("bageshree")
    assert ["m", "D", "n", "D"] in library        # a pakad fragment
    assert all(len(a) >= 3 for a in library)
    assert all(sw in RAGAS["bageshree"]["allowed"] for a in library for sw in a)


def test_ang_coverage_measures_ORDER_not_membership():
    """The question "what share of notes came from the pakad?" is answered well by every legal
    line, since the pakad contains nearly every swara. What distinguishes a raga is order."""
    idiomatic = _line("mDnDmgRS")                 # the pakad itself
    scalar = _line("SRgmPDn")                     # every note legal, pure ladder
    assert ang_coverage(idiomatic, "bageshree") == 1.0
    assert ang_coverage(scalar, "bageshree") < ang_coverage(idiomatic, "bageshree")


def test_the_report_gathers_what_a_line_DOES():
    report = motion_report(_line("SRgmPDn"), "bageshree")
    assert report.notes == 7
    assert report.stepwise_share == 1.0 and report.direction_changes == 0.0
    assert report.longest_scalar_run == 7


def test_an_empty_or_single_note_line_reports_nothing_rather_than_crashing():
    assert motion_report([], "bageshree").notes == 0
    assert longest_scalar_run(_line("S"), "bageshree") == 0
    assert ang_coverage([], "bageshree") == 0.0


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
