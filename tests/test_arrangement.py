"""
Tests for the Arrangement contract and its DETERMINISTIC half.

The composers' output is expanded into the shared chart by pure code:
`build_arrangement` honors whatever the user fixed in the brief and DERIVES the
mechanical detail (accent grid from the tala, motif from the raga's pakad,
register per voice from the subgenre) — none of it trusted to the LLM. That
whole path is pure, so it's fully tested here with no key and no cost. The LLM
dialogue half (Pandit <-> Riffsmith) is exercised live in step 3b, not here.

Runs as a script (`uv run python tests/test_arrangement.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.contracts import (  # noqa: E402
    DEFAULT_SA,
    Arrangement,
    ArrangementDraft,
    CompositionBrief,
    Section,
    SectionKind,
    accent_grid,
    build_arrangement,
    motif_from_pakad,
    voice_registers,
)
from raga import RAGAS  # noqa: E402


def _sections() -> list[Section]:
    return [
        Section(kind=SectionKind.ALAAP, bars=2, layers=["lead", "drone"], foreground="lead"),
        Section(kind=SectionKind.RIFF, bars=4, layers=["rhythm", "drums", "drone"],
                foreground="rhythm"),
    ]


def _draft(**over) -> ArrangementDraft:
    # A composer-written motif, legal in Malkauns/Darbari (the ragas this factory
    # is used with by default): d n S m are in both allowed sets.
    base = dict(raga="malkauns", subgenre="doom", tala="teentaal", bpm=72,
                motif=["d", "n", "S", "m"], sections=_sections())
    base.update(over)
    return ArrangementDraft(**base)


# --- derivations: accent grid, motif, registers --------------------------------

def test_accent_grid_marks_sam_tali_khali():
    grid = accent_grid("teentaal")               # tali=[1,5,13], khali=[9], 16 matras
    assert len(grid) == 16
    assert grid[0].kind == "sam" and grid[0].matra == 1 and grid[0].beat == 0.0
    assert grid[0].bol == "Dha"
    kinds = {a.matra: a.kind for a in grid}
    assert kinds[5] == "tali" and kinds[13] == "tali"
    assert kinds[9] == "khali"
    assert kinds[2] == "beat"


def test_motif_seed_is_the_ragas_first_pakad():
    # A SEED handed to the composer for inspiration — not the motif the chart uses.
    motif = motif_from_pakad("bhairav")
    assert motif == list(RAGAS["bhairav"]["pakad"][0])
    assert set(motif) <= set(RAGAS["bhairav"]["allowed"])   # legal by construction


def test_registers_keep_the_voices_apart():
    r = voice_registers("doom")                  # register [-3, -2]
    assert r["lead"] > r["rhythm"]
    assert r["drone"] <= r["rhythm"]
    assert {"lead", "rhythm", "drone"} <= set(r)


# --- build_arrangement: honor the brief, derive the rest ----------------------

def test_open_dims_come_from_the_draft():
    brief = CompositionBrief(mood="dark")        # user stated only a mood
    arr = build_arrangement(_draft(raga="darbari", subgenre="doom", bpm=80, tala="dadra"), brief)
    assert arr.raga == "darbari" and arr.subgenre == "doom" and arr.bpm == 80
    assert arr.tala == "dadra"
    assert arr.sa == DEFAULT_SA                   # no key stated -> render-time default


def test_brief_fixed_dims_override_the_draft():
    # The user fixed subgenre/key/bpm; a draft that drifted on those must not win.
    # (Raga stays consistent — the composer is given the fixed raga to write for.)
    brief = CompositionBrief(raga="bhairav", subgenre="thrash", key="E", sa=64, bpm=190)
    draft = _draft(raga="bhairav", subgenre="doom", bpm=72, tala="keherwa",
                   motif=["G", "m", "d", "d", "P"])   # a Bhairav phrase, composer-written
    arr = build_arrangement(draft, brief)
    assert arr.subgenre == "thrash"               # brief wins over the draft's doom
    assert arr.bpm == 190 and arr.sa == 64
    assert arr.tala == "keherwa"                  # tala is only ever the composers' call
    assert arr.motif == ["G", "m", "d", "d", "P"]  # the composer's motif carries through


def test_composer_motif_carries_through_unchanged():
    # The whole point: code does NOT overwrite the LLM's motif with a canned pakad.
    draft = _draft(raga="bhairav", motif=["G", "m", "r", "r", "S"])
    arr = build_arrangement(draft, CompositionBrief())
    assert arr.motif == ["G", "m", "r", "r", "S"]


def test_composer_can_voice_the_registers():
    draft = _draft(registers={"lead": 1, "rhythm": -2, "drone": -3})
    arr = build_arrangement(draft, CompositionBrief())
    assert arr.registers == {"lead": 1, "rhythm": -2, "drone": -3}


def test_registers_fall_back_to_subgenre_default_when_omitted():
    arr = build_arrangement(_draft(subgenre="doom"), CompositionBrief())   # no registers given
    assert arr.registers == voice_registers("doom")


def test_draft_treats_empty_registers_as_unspecified():
    # The LLM often fills the optional field with {}; that must parse as "not
    # specified" (so output_pydantic doesn't crash), then fall back to the default.
    draft = _draft(registers={})
    assert draft.registers is None
    arr = build_arrangement(draft, CompositionBrief())
    assert arr.registers == voice_registers(draft.subgenre)


def test_beats_per_bar_and_grid_match_the_tala():
    arr = build_arrangement(_draft(tala="rupak"), CompositionBrief())   # rupak = 7 matras
    assert arr.beats_per_bar == 7.0
    assert len(arr.accent_grid) == 7


# --- boundary validation: bad picks fail at the edge --------------------------

def test_draft_rejects_unknown_raga():
    try:
        _draft(raga="bhoopali")                   # a real raga, but not in our menu
        assert False, "expected ValueError"
    except Exception as e:  # noqa: BLE001
        assert "unknown raga" in str(e).lower()


def test_draft_rejects_carnatic_tala():
    try:
        _draft(tala="adi")                        # Adi is Carnatic — not in our Hindustani set
        assert False, "expected ValueError"
    except Exception as e:  # noqa: BLE001
        assert "unknown tala" in str(e).lower()


def test_draft_validates_shape_not_raga_legality():
    # The draft validates SHAPE (known sargam symbols), NOT raga legality — that
    # domain check lives in the composer's guardrail and the final Arrangement. So a
    # motif of valid-but-out-of-raga swaras parses fine as a draft (output_pydantic
    # must be able to build it; the guardrail then bounces it back for a retry).
    draft = _draft(raga="malkauns", motif=["S", "R", "g"])  # R is shuddha Re — not in Malkauns
    assert draft.motif == ["S", "R", "g"]


def test_draft_rejects_unknown_swara_symbol():
    try:
        _draft(motif=["S", "Z"])   # Z is not a sargam symbol at all
        assert False, "expected ValueError"
    except Exception as e:  # noqa: BLE001
        assert "unknown swara" in str(e).lower()


def test_draft_rejects_registers_that_would_clash():
    try:
        _draft(registers={"lead": -3, "rhythm": 0, "drone": -1})   # lead below rhythm
        assert False, "expected ValueError"
    except Exception as e:  # noqa: BLE001
        assert "lead >= rhythm" in str(e).lower()


def test_section_foreground_must_be_active():
    try:
        Section(kind=SectionKind.RIFF, bars=1, layers=["rhythm"], foreground="lead")
        assert False, "expected ValueError"
    except Exception as e:  # noqa: BLE001
        assert "foreground" in str(e).lower()


def test_section_rejects_unknown_role():
    try:
        Section(kind=SectionKind.RIFF, bars=1, layers=["guitar"], foreground="guitar")
        assert False, "expected ValueError"
    except Exception as e:  # noqa: BLE001
        assert "unknown layer" in str(e).lower()


def test_tabla_and_drums_can_play_together():
    # A core fusion sound: tabla holding the theka under the metal kit.
    section = Section(kind=SectionKind.RIFF, bars=4,
                      layers=["rhythm", "drums", "tabla", "drone"], foreground="rhythm")
    assert {"tabla", "drums"} <= set(section.layers)


def test_tabla_is_a_valid_foreground_layer():
    section = Section(kind=SectionKind.MELODY, bars=2,
                      layers=["tabla", "lead", "drone"], foreground="tabla")
    assert section.foreground == "tabla"


def test_section_carries_intent_and_transition():
    section = Section(kind=SectionKind.RIFF, bars=4, layers=["rhythm", "drums"],
                      foreground="rhythm", intent="crushing groove",
                      transition="a tihai landing on the sam into the taan")
    assert section.intent == "crushing groove"
    assert section.transition == "a tihai landing on the sam into the taan"


# --- the full Arrangement's cross-field guards --------------------------------

def test_arrangement_rejects_wrong_grid_length():
    grid = accent_grid("teentaal")[:-1]           # 15 matras, not 16
    try:
        Arrangement(raga="malkauns", subgenre="doom", tala="teentaal", sa=62, bpm=72,
                    beats_per_bar=16.0, sections=_sections(), accent_grid=grid,
                    motif=motif_from_pakad("malkauns"),
                    registers=voice_registers("doom"))
        assert False, "expected ValueError"
    except Exception as e:  # noqa: BLE001
        assert "matras" in str(e).lower()


def test_arrangement_rejects_illegal_motif():
    try:
        Arrangement(raga="malkauns", subgenre="doom", tala="teentaal", sa=62, bpm=72,
                    beats_per_bar=16.0, sections=_sections(), accent_grid=accent_grid("teentaal"),
                    motif=["R"],                  # shuddha Re — absent from Malkauns
                    registers=voice_registers("doom"))
        assert False, "expected ValueError"
    except Exception as e:  # noqa: BLE001
        assert "illegal" in str(e).lower()


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
