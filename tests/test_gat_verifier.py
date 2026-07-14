"""
Tests for the gat verifier (GAT OVERHAUL fix #4) — the TIME-legality of the mukhada head.

All pure (no key, no cost): `verify_mukhada` is deterministic, so its checks — fills the avartan,
cadences to a resting swara, isn't rhythmically flat — are proven here without the LLM. The
generation-time RE-ROLL that consumes these violations is exercised in `tests/test_lead.py`.

Runs as a script (`uv run python tests/test_gat_verifier.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.contracts import LeadNote, LeadPhrase, PhrasePlan  # noqa: E402
from crew.gat_verifier import verify_mukhada  # noqa: E402

_PLAN = PhrasePlan(seed=["S"], contour="arch", transformations=["repeat", "resolve"],
                   climax_and_sam="lands on Sa")


def _cell(*notes: LeadNote) -> LeadPhrase:
    return LeadPhrase(phrase_plan=_PLAN, notes=list(notes))


def _n(swara: str, dur: float, **kw) -> LeadNote:
    return LeadNote(swara=swara, dur=dur, **kw)


# --- a clean, one-avartan, landing, varied head passes -------------------------

def test_a_well_formed_mukhada_has_no_violations():
    # malkauns (resting = S, m): fills the 8-beat avartan, lands on Sa, durations vary
    cell = _cell(_n("S", 2.0), _n("g", 1.0), _n("m", 3.0), _n("S", 2.0))
    assert verify_mukhada(cell, cycle_beats=8.0, raga="malkauns") == []


# --- fills the avartan ----------------------------------------------------------

def test_a_fragment_is_flagged():
    cell = _cell(_n("S", 1.0), _n("m", 1.0))            # 2 of 8 beats -> a fragment
    viol = verify_mukhada(cell, cycle_beats=8.0, raga="malkauns")
    assert any("fragment" in v or "fills only" in v for v in viol)


def test_an_overlong_head_is_flagged():
    cell = _cell(_n("S", 8.0), _n("m", 8.0))            # 16 beats over an 8-beat avartan, lands on m
    viol = verify_mukhada(cell, cycle_beats=8.0, raga="malkauns")
    assert any("over" in v for v in viol)


def test_rests_count_toward_filling_the_avartan():
    # a rest occupies its beats, so a head that rests to the sam still fills the cycle
    cell = _cell(_n("S", 3.0), _n("m", 3.0), _n("S", 1.0, rest=True), _n("S", 1.0))
    assert not any("fragment" in v or "fills only" in v
                   for v in verify_mukhada(cell, cycle_beats=8.0, raga="malkauns"))


# --- cadences to a resting swara ------------------------------------------------

def test_a_head_that_does_not_land_on_a_resting_swara_is_flagged():
    # ends on n (not S/vadi m/samvadi S in malkauns) -> no cadence to the sam
    cell = _cell(_n("S", 3.0), _n("m", 3.0), _n("n", 2.0))
    viol = verify_mukhada(cell, cycle_beats=8.0, raga="malkauns")
    assert any("resting swara" in v for v in viol)


def test_a_head_landing_on_the_vadi_is_accepted():
    cell = _cell(_n("S", 3.0), _n("d", 2.0), _n("m", 3.0))   # lands on the vadi m
    assert not any("resting swara" in v
                   for v in verify_mukhada(cell, cycle_beats=8.0, raga="malkauns"))


def test_a_chikari_ending_counts_as_landing_on_sa():
    # a chikari sounds taar Sa regardless of its written swara, so it lands on a resting note
    cell = _cell(_n("S", 3.0), _n("m", 3.0), _n("n", 2.0, bol="chikari"))
    assert not any("resting swara" in v
                   for v in verify_mukhada(cell, cycle_beats=8.0, raga="malkauns"))


# --- not rhythmically flat ------------------------------------------------------

def test_a_flat_even_note_head_is_flagged():
    # the diagnosed failure: a gat of even quarter notes
    cell = _cell(_n("S", 2.0), _n("g", 2.0), _n("m", 2.0), _n("S", 2.0))
    viol = verify_mukhada(cell, cycle_beats=8.0, raga="malkauns")
    assert any("flat" in v for v in viol)


def test_two_equal_notes_are_not_called_flat():
    # too few notes to be a "flat" pattern (needs >= 3 sounding notes)
    cell = _cell(_n("S", 4.0), _n("m", 4.0))
    assert not any("flat" in v for v in verify_mukhada(cell, cycle_beats=8.0, raga="malkauns"))


# --- degenerate: no sounding notes ----------------------------------------------

def test_an_all_rest_head_is_flagged():
    cell = _cell(_n("S", 4.0, rest=True), _n("S", 4.0, rest=True))
    viol = verify_mukhada(cell, cycle_beats=8.0, raga="malkauns")
    assert len(viol) == 1 and "no sounding notes" in viol[0]


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
