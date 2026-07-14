"""
Knowledge-core test suite — proves the DATA is correct, not just the code.

This is the project's "testable knowledge" convention made real: the raga, tala,
and subgenre libraries each ship a `check_*_consistency` function, and these
tests run them across the whole library plus a few cross-cutting invariants (e.g.
each raga's legal notes really do spell its declared Western mode) and an
end-to-end ornament round-trip through the validator.

Runs two ways:
  * as a script  ->  `uv run python tests/test_knowledge.py`   (no pytest needed)
  * under pytest ->  `pytest` discovers the test_* functions
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from raga import RAGAS, SWARAS, check_raga_consistency, validate_composition  # noqa: E402
from talas import TALAS, check_tala_consistency                              # noqa: E402
from subgenres import SUBGENRES, check_subgenre_consistency                  # noqa: E402
from demo import build_fusion                                                # noqa: E402

# Western mode -> the set of semitone offsets (from Sa) it must contain.
MODES = {
    "Phrygian":                            {0, 1, 3, 5, 7, 8, 10},
    "Dorian":                              {0, 2, 3, 5, 7, 9, 10},
    "Aeolian":                             {0, 2, 3, 5, 7, 8, 10},
    "double harmonic (Byzantine)":         {0, 1, 4, 5, 7, 8, 11},
    "dark/minor pentatonic (no Re, no Pa)": {0, 3, 5, 8, 10},
}


def test_raga_consistency():
    for name in RAGAS:
        assert check_raga_consistency(name) == [], f"{name}: {check_raga_consistency(name)}"


def test_raga_allowed_matches_declared_mode():
    for name, r in RAGAS.items():
        semis = {SWARAS[s] for s in r["allowed"]}
        assert semis == MODES[r["western_mode"]], (
            f"{name}: allowed set {sorted(semis)} != {r['western_mode']} "
            f"{sorted(MODES[r['western_mode']])}")


def test_raga_pakad_and_chalan_are_legal():
    # Every pakad/chalan swara must be inside the raga (redundant with the
    # consistency check, but stated explicitly because it's the seed contract
    # the generators depend on).
    for name, r in RAGAS.items():
        allowed = set(r["allowed"])
        for phrase in r.get("pakad", []) + r.get("chalan", []):
            assert set(phrase) <= allowed, f"{name}: phrase {phrase} leaves the raga"


def test_raga_ornaments_fact_is_a_known_closed_set():
    # `ornaments` names the light decorations a raga idiomatically uses (murki/khatka). Source-
    # verified: of our five, ONLY Bhairavi carries them; the grave/meend ragas use andolan instead.
    for name, r in RAGAS.items():
        assert set(r.get("ornaments", [])) <= {"murki", "khatka"}, f"{name}: unknown ornament"
    assert set(RAGAS["bhairavi"]["ornaments"]) == {"murki", "khatka"}
    assert RAGAS["darbari"]["ornaments"] == [] and RAGAS["malkauns"]["ornaments"] == []


def test_tala_consistency():
    for name in TALAS:
        assert check_tala_consistency(name) == [], f"{name}: {check_tala_consistency(name)}"


def test_subgenre_consistency():
    for name in SUBGENRES:
        assert check_subgenre_consistency(name) == [], f"{name}: {check_subgenre_consistency(name)}"


def test_every_subgenre_has_an_operational_groove_brief():
    # the fix for "a vague brief collapses into sparse whole notes": each subgenre carries a
    # concrete rhythmic directive, and the consistency check refuses a missing/empty one.
    for name, s in SUBGENRES.items():
        assert s.get("groove_brief", "").strip(), f"{name}: missing groove_brief"
    hollow = {**SUBGENRES["doom"], "groove_brief": "  "}
    orig = SUBGENRES["doom"]
    SUBGENRES["doom"] = hollow
    try:
        assert any("groove_brief" in p for p in check_subgenre_consistency("doom"))
    finally:
        SUBGENRES["doom"] = orig


def test_ornaments_are_validated():
    # A legal kan + meend line passes; an illegal grace note and an illegal
    # meend target are both caught (the guardrail sees ornaments, not just notes).
    legal = {"raga": "darbari", "sa": 60, "bpm": 100,
             "tala": {"name": "teentaal", "beats_per_bar": 4},
             "layers": [{"role": "lead", "channel": 2, "notes": [
                 {"swara": "g", "oct": 0, "start": 0.0, "dur": 1.0, "grace": ["R"], "meend_swara": "m"},
             ]}]}
    assert validate_composition(legal) == []

    bad_grace = {"raga": "darbari", "sa": 60, "bpm": 100,
                 "tala": {"name": "teentaal", "beats_per_bar": 4},
                 "layers": [{"role": "lead", "channel": 2, "notes": [
                     {"swara": "R", "oct": 0, "start": 0.0, "dur": 1.0, "grace": ["G"]},
                 ]}]}
    v = validate_composition(bad_grace)
    assert len(v) == 1 and v[0]["kind"] == "grace", v

    bad_meend = {"raga": "malkauns", "sa": 60, "bpm": 100,
                 "tala": {"name": "teentaal", "beats_per_bar": 4},
                 "layers": [{"role": "lead", "channel": 2, "notes": [
                     {"swara": "m", "oct": 0, "start": 0.0, "dur": 1.0, "meend_swara": "P"},
                 ]}]}
    v = validate_composition(bad_meend)
    assert len(v) == 1 and v[0]["kind"] == "meend-target", v


def test_chord_tones_are_validated():
    # A riff power chord faces the grammar like any other pitch: a legal chord passes,
    # an out-of-raga chord tone is caught (kind "chord"), so a power chord can't smuggle
    # an illegal note in past the root. Malkauns: S g m d n legal; P and R are not.
    legal = {"raga": "malkauns", "sa": 60, "bpm": 100,
             "tala": {"name": "teentaal", "beats_per_bar": 4},
             "layers": [{"role": "rhythm", "channel": 3, "notes": [
                 {"swara": "S", "oct": -2, "start": 0.0, "dur": 1.0, "chord": ["S", "m"]},
             ]}]}
    assert validate_composition(legal) == []

    bad_chord = {"raga": "malkauns", "sa": 60, "bpm": 100,
                 "tala": {"name": "teentaal", "beats_per_bar": 4},
                 "layers": [{"role": "rhythm", "channel": 3, "notes": [
                     {"swara": "S", "oct": -2, "start": 0.0, "dur": 1.0, "chord": ["P"]},
                 ]}]}
    v = validate_composition(bad_chord)
    assert len(v) == 1 and v[0]["kind"] == "chord" and v[0]["swara"] == "P", v


def test_phase0_pipeline_still_holds():
    # The proven Phase 0 composition is clean; the deliberately-illegal variant
    # is caught. Guards against a schema/validator change silently regressing.
    assert validate_composition(build_fusion(illegal=False)) == []
    assert len(validate_composition(build_fusion(illegal=True))) > 0


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except Exception as e:  # noqa: BLE001 — test runner wants every failure
            failed += 1
            print(f"FAIL  {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
