"""
Tests for the energy arc + layer-by-function mix pass (crew/dynamics.py). All PURE (no LLM,
no cost): the per-form-role energy, the final-section floor, and the two jobs of `apply_dynamics`
— the piece BUILDS across the arc, and the section foreground dominates (the rhythm guitar ducks
under a lead-foreground section). A chart with no gat form comes back untouched (the gate that
keeps the rest of the suite green). The drone is exempt.

Runs as a script (`uv run python tests/test_dynamics.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.contracts import (  # noqa: E402
    ArrangementDraft,
    CompositionBrief,
    DrumHit,
    Layer,
    Note,
    Section,
    SectionKind,
    build_arrangement,
)
from crew.dynamics import apply_dynamics, section_energy  # noqa: E402
from render import DRUMS  # noqa: E402

_DRUM = sorted(DRUMS)[0]


def _sec(form_role, foreground, layers, bars=1):
    return Section(kind=SectionKind.RIFF, bars=bars, layers=layers, foreground=foreground,
                   riff_slot="main" if "rhythm" in layers else None, form_role=form_role)


def _arr(sections):
    draft = ArrangementDraft(raga="malkauns", subgenre="doom", tala="teentaal", bpm=72,
                             motif=["d", "n", "S", "m"], sections=sections)
    return build_arrangement(draft, CompositionBrief(mood="dark"))


def _vel_at(layer: Layer, start: float) -> int:
    return next(n.vel for n in layer.notes if n.start == start)


# --- section_energy: the arc spine ---------------------------------------------

def test_energy_is_none_without_a_form_role():
    assert section_energy(_sec(None, "rhythm", ["rhythm", "drone"]), is_final=False) is None


def test_energy_rises_intro_to_peak():
    e = lambda r: section_energy(_sec(r, "lead", ["lead", "drone"]), is_final=False)
    assert e("intro") < e("mukhada") < e("antara") < e("taan_long")


def test_final_non_outro_section_is_floored_high():
    mid = section_energy(_sec("mukhada", "rhythm", ["rhythm", "drone"]), is_final=False)
    fin = section_energy(_sec("mukhada", "rhythm", ["rhythm", "drone"]), is_final=True)
    assert fin > mid and fin >= 0.85


def test_final_outro_is_not_floored():
    assert section_energy(_sec("outro", "lead", ["lead", "drone"]), is_final=True) < 0.5


# --- apply_dynamics: build + balance -------------------------------------------

def _band():
    """A 4-section gat with a soft intro, a riff-led mukhada, a lead-led taan (rhythm present),
    and a final mukhada — plus layers whose note starts land in each 16-beat section."""
    arr = _arr([
        _sec("intro", "lead", ["lead", "drone"]),                       # [0,16)
        _sec("mukhada", "rhythm", ["rhythm", "drums", "drone"]),         # [16,32)
        _sec("taan_long", "lead", ["lead", "rhythm", "drone"]),         # [32,48)
        _sec("mukhada", "rhythm", ["rhythm", "drums", "drone"]),        # [48,64) final
    ])
    drone = Layer(role="drone", notes=[Note(swara="S", oct=-3, start=0.0, dur=64.0, vel=55)])
    lead = Layer(role="lead", notes=[Note(swara="S", start=0.0, dur=1, vel=90),     # intro
                                     Note(swara="P", start=32.0, dur=1, vel=90)])   # taan
    rhythm = Layer(role="rhythm", notes=[Note(swara="S", start=16.0, dur=1, vel=110),   # mukhada
                                         Note(swara="S", start=32.0, dur=1, vel=110)])  # under the taan
    drums = Layer(role="drums", hits=[DrumHit(drum=_DRUM, start=16.0, vel=100)])
    return arr, apply_dynamics([drone, lead, rhythm, drums], arr)


def test_drone_is_left_untouched():
    _arr_, (drone, *_rest) = _band()
    assert drone.notes[0].vel == 55                              # the anchor never swells


def test_piece_builds_soft_intro_to_loud_taan():
    _arr_, (_drone, lead, _rhythm, _drums) = _band()
    assert _vel_at(lead, 0.0) < _vel_at(lead, 32.0)             # intro lead softer than the taan lead


def test_rhythm_ducks_under_a_lead_foreground_section():
    _arr_, (_drone, lead, rhythm, _drums) = _band()
    ducked = _vel_at(rhythm, 32.0)                              # rhythm inside the lead-led taan
    assert ducked < 110                                         # below its authored velocity
    assert ducked < _vel_at(lead, 32.0)                        # and below the lead it must not bury


def test_riff_led_section_keeps_the_rhythm_up():
    _arr_, (_drone, _lead, rhythm, _drums) = _band()
    # in the riff-led mukhada the rhythm is the foreground — not ducked below the taan's ducked riff
    assert _vel_at(rhythm, 16.0) > _vel_at(rhythm, 32.0)


def test_drum_hits_are_scaled_too():
    _arr_, (_drone, _lead, _rhythm, drums) = _band()
    assert drums.hits[0].vel != 100                             # the kit rides the energy arc


def test_a_formless_chart_is_unchanged():
    arr = _arr([_sec(None, "rhythm", ["rhythm", "drone"]), _sec(None, "lead", ["lead", "drone"])])
    rhythm = Layer(role="rhythm", notes=[Note(swara="S", start=0.0, dur=1, vel=110)])
    lead = Layer(role="lead", notes=[Note(swara="S", start=16.0, dur=1, vel=90)])
    out = apply_dynamics([rhythm, lead], arr)
    assert out[0].notes[0].vel == 110 and out[1].notes[0].vel == 90


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
