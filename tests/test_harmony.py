"""
Tests for the HARMONY layer (crew/harmony.py) — all PURE (no LLM, no cost).

What must hold: every voicing tone is legal in its raga BY CONSTRUCTION (built up the
raga's own ladder) and safe to arpeggiate upward (a descent-only swara is re-seated,
never entered from below); each mode produces its per-avartan voicings (drone dyad,
Sa-pedal + rotating colours, a root cycle stretched across the bars); the arpeggio
fills its window and clips at the edge; and `clean_layer` plays exactly where the
chart lists the `clean` role (absent everywhere else — full backward compatibility),
dropping out of the taan's band-drop window like the rest of the band.

Runs as a script (`uv run python tests/test_harmony.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.contracts import (  # noqa: E402
    ArrangementDraft,
    CompositionBrief,
    HarmonyPlan,
    Section,
    SectionKind,
    build_arrangement,
)
from crew.dynamics import apply_taan_exposure  # noqa: E402
from crew.harmony import arpeggio, bar_voicings, clean_layer, voicing  # noqa: E402
from raga import RAGAS  # noqa: E402


def _arr(sections, raga="malkauns"):
    draft = ArrangementDraft(raga=raga, subgenre="doom", tala="teentaal", bpm=72,
                             motif=["d", "n", "S", "m"], sections=sections)
    return build_arrangement(draft, CompositionBrief(mood="dark"))


def _sec(kind=SectionKind.MELODY, bars=1, layers=("lead", "clean", "drone"),
         harmony=None, form_role=None):
    return Section(kind=kind, bars=bars, layers=list(layers), foreground=layers[0],
                   harmony=harmony, form_role=form_role)


# --- voicings: legal by construction, ascendable by construction ------------------

def test_voicings_are_legal_in_every_raga():
    for raga, r in RAGAS.items():
        for root in r["allowed"]:
            for sw, _oct in voicing(root, raga):
                assert sw in r["allowed"], f"{raga}: voicing on {root} sounds {sw}"


def test_voicing_reseats_a_descent_only_third():
    # bageshree: the ladder third above g is P — descent-only — so the voicing lifts it
    # to the next swara enterable from below (D); an arpeggio can rise through it
    tones = [sw for sw, _ in voicing("g", "bageshree")]
    assert "P" not in tones and "D" in tones


# --- bar_voicings: the three modes -------------------------------------------------

def test_drone_mode_breaks_the_tanpura_dyad():
    section = _sec(bars=2, harmony=HarmonyPlan(mode="drone"))
    bars = bar_voicings(section, "malkauns")
    assert len(bars) == 2 and bars[0] == bars[1]                 # no motion
    swaras = {sw for sw, _ in bars[0]}
    assert swaras == {"S", "m"}                                  # malkauns: Sa + ma (no Pa)


def test_modal_pedal_holds_sa_and_rotates_colours():
    section = _sec(bars=2, harmony=HarmonyPlan(mode="modal_pedal", roots=["m", "d"]))
    bars = bar_voicings(section, "malkauns")
    assert all(bar[0] == ("S", 0) for bar in bars)               # the pedal never moves
    assert bars[0][1][0] == "m" and bars[1][1][0] == "d"         # the colour rotates


def test_modal_pedal_defaults_to_vadi_samvadi():
    section = _sec(bars=1)                                       # no harmony -> the default
    bars = bar_voicings(section, "malkauns")
    assert bars[0][0] == ("S", 0)
    assert bars[0][1][0] == RAGAS["malkauns"]["vadi"]


def test_progression_stretches_roots_and_comes_home():
    section = _sec(bars=4, harmony=HarmonyPlan(mode="progression", roots=["m", "d", "S"]))
    bars = bar_voicings(section, "malkauns")
    assert [bar[0][0] for bar in bars] == ["m", "m", "d", "S"]   # stretched; ends on Sa


# --- arpeggio: fills the window, clips the edge ------------------------------------

def test_arpeggio_walks_up_down_and_clips():
    tones = [("S", 0), ("g", 0), ("S", 1)]
    notes = arpeggio(tones, start=4.0, beats=3.25, register=0, subdiv=0.5)
    assert [n.swara for n in notes[:4]] == ["S", "g", "S", "g"]  # up, then back down
    assert notes[0].start == 4.0
    assert notes[-1].start + notes[-1].dur == 7.25               # clipped at the edge
    assert notes[-1].dur == 0.25
    assert all(4.0 <= n.start < 7.25 for n in notes)


def test_arpeggio_seats_in_the_register():
    notes = arpeggio([("S", 0), ("S", 1)], start=0.0, beats=1.0, register=-1, subdiv=0.5)
    assert [n.oct for n in notes] == [-1, 0]


# --- clean_layer: plays where the chart says, silent everywhere else ----------------

def test_clean_layer_absent_when_no_section_lists_it():
    arr = _arr([_sec(layers=("lead", "drone"))])
    assert clean_layer(arr) is None                              # backward compatible


def test_clean_layer_covers_exactly_the_clean_sections():
    arr = _arr([_sec(layers=("lead", "drone")),                  # [0,16) — no clean
                _sec(layers=("lead", "clean", "drone"))])        # [16,32)
    layer = clean_layer(arr)
    assert layer is not None and layer.role == "clean"
    assert all(16.0 <= n.start < 32.0 for n in layer.notes)


def test_clean_layer_tones_are_legal_in_the_raga():
    arr = _arr([_sec(bars=2, harmony=HarmonyPlan(mode="progression", roots=["m", "S"]))])
    layer = clean_layer(arr)
    allowed = set(RAGAS["malkauns"]["allowed"])
    assert layer is not None and all(n.swara in allowed for n in layer.notes)


def test_clean_holds_pads_under_the_long_taan():
    arr = _arr([_sec(kind=SectionKind.TAAN, bars=1, form_role="taan_long")])
    layer = clean_layer(arr)
    assert layer is not None
    assert all(n.dur == 16.0 for n in layer.notes)               # held, not running
    assert len(layer.notes) == 3                                 # one voicing, rung once


def test_clean_drops_out_of_the_taan_exposure_window():
    # the band-drop: the final avartan of a long taan empties the band — clean included
    arr = _arr([_sec(kind=SectionKind.TAAN, bars=2, form_role="taan_long")])
    layer = clean_layer(arr)
    (exposed,) = apply_taan_exposure([layer], arr)
    starts = [n.start for n in exposed.notes]
    assert all(s < 16.0 or s <= 16.0 + 1e-6 for s in starts)     # nothing INSIDE the window
    assert max(starts) <= 16.0                                   # the stop hit at most ON the sam


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
