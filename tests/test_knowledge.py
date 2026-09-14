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
    # menu expansion (2026-07-14)
    "Lydian":                              {0, 2, 4, 6, 7, 9, 11},   # Yaman
    "harmonic minor":                      {0, 2, 3, 5, 7, 8, 11},   # Kirwani
    "Mixolydian b6":                       {0, 2, 4, 5, 7, 8, 10},   # Charukeshi (Aeolian dominant)
    "double harmonic #4":                  {0, 1, 4, 6, 7, 8, 11},   # Puriya Dhanashree (Poorvi + tritone)
    # menu expansion (2026-07-15)
    "dark pentatonic (natural 7)":         {0, 3, 5, 8, 11},         # Chandrakauns (Malkauns + shuddha Ni)
    "both-Ga pentatonic (no Re/Dha, komal Ni)": {0, 3, 4, 5, 7, 10}, # Jog (both gandhars)
    "Marwa (flat-2, sharp-4, no Pa)":      {0, 1, 4, 6, 9, 11},      # Marwa (Pa omitted)
    "Todi thaat (flat-2 flat-3 sharp-4 flat-6 natural-7)": {0, 1, 3, 6, 7, 8, 11},  # Todi (Miyan ki Todi)
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


def test_directional_varjya_is_derived_from_the_ladders():
    # data-derived, no new facts: a swara absent from the aroha is DESCENT-only.
    # Bageshree touches P and R only on the way down; Bhimpalasi skips R and D
    # ascending; Malkauns is symmetric (no rule). (Sujit's catch, 2026-07-16.)
    from raga import directional_varjya
    assert directional_varjya("bageshree") == {"R": "avaroha", "P": "avaroha"}
    assert directional_varjya("bhimpalasi") == {"R": "avaroha", "D": "avaroha"}
    assert directional_varjya("malkauns") == {}


def test_resting_swaras_are_sa_vadi_samvadi_and_legal():
    # the raga's settling points — Sa (always) plus vadi + samvadi — used to snap a trading
    # solo's handoff to a clean landing. Every resting note must be a legal swara of the raga.
    from raga import resting_swaras
    for name, r in RAGAS.items():
        rs = resting_swaras(name)
        assert "S" in rs and r["vadi"] in rs and r["samvadi"] in rs
        assert rs <= set(r["allowed"])                  # every resting note is legal in the raga
    assert resting_swaras("darbari") == {"S", "R", "P"}  # vadi R, samvadi P


def test_ascent_step_skips_descent_only_swaras():
    # the next swara ENTERABLE from below — the seat for any code gesture rising into
    # a pitch (a riff bend's apex): a plain step in a symmetric raga, the skip in a
    # directional one, and octave-aware at the top of the ladder.
    from raga import ascent_step
    assert ascent_step("S", "malkauns") == ("g", 0)     # plain next step
    assert ascent_step("S", "bageshree") == ("g", 0)    # R is descent-only -> skipped
    assert ascent_step("m", "bageshree") == ("D", 0)    # P skipped, lands on D
    assert ascent_step("n", "malkauns") == ("S", 1)     # wraps into the next octave


def test_direction_violations_flag_a_wrong_side_entry():
    from raga import direction_violations
    # m -> P ascends into Bageshree's descent-only P: flagged with the rule named
    assert any("DESCENT-only" in v for v in direction_violations([("m", 0), ("P", 0)], "bageshree"))
    # D -> P is the raga's own descent — clean; a re-struck P (same pitch) is free too
    assert direction_violations([("D", 0), ("P", 0), ("P", 0), ("m", 0)], "bageshree") == []
    # the rule is octave-aware: taar m down to madhya P is an entry from ABOVE — clean
    assert direction_violations([("m", 1), ("P", 0)], "bageshree") == []


def test_phase0_pipeline_still_holds():
    # The proven Phase 0 composition is clean; the deliberately-illegal variant
    # is caught. Guards against a schema/validator change silently regressing.
    assert validate_composition(build_fusion(illegal=False)) == []
    assert len(validate_composition(build_fusion(illegal=True))) > 0


def test_chikari_strings_are_always_legal_in_their_raga():
    """The chikari strings ring under every stroke, so a mistuned one would sound a swara
    outside the grammar on every hit."""
    from raga import chikari_swaras
    for name, r in RAGAS.items():
        allowed = set(r["allowed"])
        for swara in chikari_swaras(name):
            assert swara in allowed, f"{name}: chikari string on {swara}, not in the raga"


def test_the_first_two_chikari_strings_are_sa():
    """Strings 1-2 carry the stroke; 3-4 are colour."""
    from raga import chikari_swaras
    for name in RAGAS:
        assert chikari_swaras(name)[:2] == ["S", "S"], name


def test_bageshree_tunes_to_dha_and_ma_not_pa_and_ga():
    """Bageshree HAS a Pa, so the 'absent Pa' convention does not reach it — yet it is tuned
    Sa Sa Dha Ma, because its Pa is vakra and avaroha-only while Ma is its vadi and Dha its
    strong nyas. Source: Sujit's guruji (oral tradition), recorded as a practitioner source."""
    from raga import chikari_swaras
    assert chikari_swaras("bageshree") == ["S", "S", "D", "m"]


def test_a_raga_without_pa_takes_the_madhyam_string():
    """The sourced convention: where Pa is absent the string is retuned to ma."""
    from raga import chikari_swaras
    assert "P" not in chikari_swaras("malkauns")
    assert "m" in chikari_swaras("malkauns")


def test_the_drone_never_sounds_a_swara_the_raga_drops_in_ASCENT():
    """A swara the raga omits on the way up is not a resting tone, whatever the tanpura
    convention says. Bageshree exposed this: its Pancham is present but vakra and
    avaroha-only, yet a Pa-first preference list droned it continuously — measured on the
    2026-09-14 render, the tanpura held Sa+Pa for the whole piece while the clean guitar
    spent 34 of 72 notes on Pa, in the raga whose identity IS the weakened Pa."""
    from raga import directional_varjya, drone_swaras
    for name in RAGAS:
        descent_only = {sw for sw, d in directional_varjya(name).items() if d == "avaroha"}
        for swara in drone_swaras(name):
            assert swara not in descent_only, f"{name}: drone sounds descent-only {swara}"


def test_bageshree_and_todi_take_the_madhyam_drone():
    """Both drop Pa from the aroha (encoded, source-verified), so both tune to Ma — the same
    substitution a player makes for a raga whose Pancham is weak."""
    from raga import drone_swaras
    assert drone_swaras("bageshree") == ["S", "m"]
    assert drone_swaras("todi") == ["S", "M"]      # Todi's Ma is tivra


def test_a_raga_with_a_free_pa_keeps_it():
    from raga import drone_swaras
    assert drone_swaras("darbari") == ["S", "P"]   # no directional varjya — Pa is a real rest


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
