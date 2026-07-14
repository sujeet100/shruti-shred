"""
Tests for the riff FAMILY (crew/riff_family.py) — the deterministic variations that stop a
recurring riff from looping unchanged. All PURE (no LLM, no key, no cost): the four transforms,
the per-bar selection policy, legality-by-construction, and the integration through
`rhythm_layer_from` (development engages only on a real gat chart; a form-less chart is literal).

Runs as a script (`uv run python tests/test_riff_family.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.contracts import (  # noqa: E402
    ArrangementDraft,
    CompositionBrief,
    RiffNote,
    RiffPattern,
    Section,
    SectionKind,
    build_arrangement,
    motif_illegal_in_raga,
)
from crew.riff import rhythm_layer_from  # noqa: E402
from crew.riff_family import apply_variant, develop_section, variant_for_bar  # noqa: E402


def _notes(*swaras: str, dur: float = 0.5) -> list[RiffNote]:
    return [RiffNote(swara=s, dur=dur) for s in swaras]


def _sec(form_role=None, bars: int = 1) -> Section:
    return Section(kind=SectionKind.RIFF, bars=bars, layers=["rhythm", "drone"],
                   foreground="rhythm", riff_slot="main", form_role=form_role)


# --- the four transforms -------------------------------------------------------

def test_base_is_the_cycle_unchanged_but_copied():
    base = _notes("S", "g", "m", "S")
    out = apply_variant(base, "base")
    assert [n.swara for n in out] == ["S", "g", "m", "S"]
    assert all(n.chord is None for n in out)
    assert out[0] is not base[0]                              # a copy, not the original


def test_prime_keeps_pitches_but_chugs_with_a_turnaround():
    base = _notes("S", "g", "m", "d")
    out = apply_variant(base, "prime")
    assert [n.swara for n in out] == ["S", "g", "m", "d"]     # same contour
    assert all(n.technique == "palm_mute" for n in out[:-1])  # chugged
    assert out[-1].technique == "slide"                       # turnaround into the loop


def test_stripped_halves_the_attacks_and_sustains():
    base = _notes("S", "r", "g", "m", "P", "d")               # 6 attacks
    out = apply_variant(base, "stripped")
    assert [n.swara for n in out] == ["S", "g", "P"]          # every other note
    assert all(n.dur == 1.0 for n in out)                     # 0.5 doubled -> sustained
    assert set(n.swara for n in out) <= set(n.swara for n in base)


def test_double_adds_an_octave_power_chord_on_every_note():
    out = apply_variant(_notes("S", "g"), "double")
    assert out[0].chord == ["S"] and out[1].chord == ["g"]    # root + its own octave
    assert all(n.technique == "palm_mute" for n in out)


def test_double_preserves_an_existing_chord_tone():
    out = apply_variant([RiffNote(swara="S", dur=1.0, chord=["P"])], "double")
    assert out[0].chord == ["P", "S"]                         # keeps P, adds the octave


def test_double_leaves_rests_silent():
    out = apply_variant([RiffNote(swara="S", dur=0.5),
                         RiffNote(swara="S", dur=0.5, rest=True)], "double")
    assert out[0].chord == ["S"]                          # the sounding note is doubled
    assert out[1].rest and out[1].chord is None           # the rest keeps its space


def test_prime_turnaround_skips_a_trailing_rest():
    out = apply_variant([RiffNote(swara="S", dur=0.5), RiffNote(swara="g", dur=0.5),
                         RiffNote(swara="S", dur=0.5, rest=True)], "prime")
    assert out[-1].rest and out[-1].technique is None     # the trailing rest stays a rest
    assert out[1].technique == "slide"                    # turnaround on the last SOUNDING note
    assert out[0].technique == "palm_mute"


def test_every_variant_stays_legal_in_the_raga():
    # a legal Malkauns riff; every family member must keep ONLY legal swaras (roots AND chords)
    base = _notes("S", "g", "m", "d", "n")
    for variant in ("base", "prime", "stripped", "double"):
        out = apply_variant(base, variant)
        swaras = [n.swara for n in out] + [c for n in out for c in (n.chord or [])]
        assert motif_illegal_in_raga(swaras, "malkauns") == [], variant


# --- the per-bar policy --------------------------------------------------------

def test_no_form_role_is_always_base():
    sec = _sec(form_role=None, bars=4)
    assert [variant_for_bar(sec, i, 4, is_final_rhythm=True) for i in range(4)] == ["base"] * 4


def test_taan_section_is_stripped():
    sec = _sec(form_role="taan_long", bars=2)
    assert all(variant_for_bar(sec, i, 2, is_final_rhythm=False) == "stripped" for i in range(2))


def test_primes_every_third_bar_of_a_long_section():
    sec = _sec(form_role="mukhada", bars=6)
    got = [variant_for_bar(sec, i, 6, is_final_rhythm=False) for i in range(6)]
    assert got == ["base", "base", "prime", "base", "base", "prime"]


def test_doubles_the_final_bar_of_the_final_rhythm_section():
    sec = _sec(form_role="mukhada", bars=4)
    got = [variant_for_bar(sec, i, 4, is_final_rhythm=True) for i in range(4)]
    assert got == ["base", "base", "prime", "double"]


def test_short_section_stays_base():
    sec = _sec(form_role="mukhada", bars=2)
    assert [variant_for_bar(sec, i, 2, is_final_rhythm=False) for i in range(2)] == ["base", "base"]


def test_develop_section_returns_one_cycle_per_bar():
    cycles = develop_section(_notes("S", "g"), _sec(form_role="mukhada", bars=4),
                             is_final_rhythm=True)
    assert len(cycles) == 4
    assert cycles[0][0].chord is None                         # the statement is unchanged
    assert cycles[3][0].chord == ["S"]                        # the final bar is doubled


# --- integration through rhythm_layer_from -------------------------------------

def _arr_one(form_role, bars: int):
    draft = ArrangementDraft(
        raga="malkauns", subgenre="doom", tala="teentaal", bpm=72, motif=["d", "n", "S", "m"],
        sections=[Section(kind=SectionKind.RIFF, bars=bars, layers=["rhythm", "drone"],
                          foreground="rhythm", riff_slot="main", form_role=form_role)])
    return build_arrangement(draft, CompositionBrief(mood="dark"))


def test_rhythm_layer_develops_a_gat_section():
    arr = _arr_one("mukhada", 3)                              # the only (=final) rhythm section
    layer = rhythm_layer_from({0: RiffPattern(notes=_notes("S", "g", "m", "S"))}, arr)
    cyc = arr.beats_per_bar
    assert all(not n.chord for n in layer.notes if n.start < cyc)          # bar 0 stated plainly
    assert any(n.chord for n in layer.notes if n.start >= 2 * cyc)         # final bar doubled


def test_rhythm_layer_without_a_form_role_is_placed_literally():
    arr = _arr_one(None, 3)
    layer = rhythm_layer_from({0: RiffPattern(notes=_notes("S", "g", "m", "S"))}, arr)
    assert all(not n.chord for n in layer.notes)              # no development without a gat form


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
