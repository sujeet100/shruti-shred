"""
Tests for the Groove / Drums engine — all pure (no key, no cost).

The groove is deterministic, so everything the user asked about is provable here
without the LLM: the kick LOCKS to the riff's on-beats, the feel CHANGES per section
kind (a half-time breakdown is sparser than a straight riff, a taan is busier), a tom
FILL lands in the last beats before a section change, each section opens on a crash,
and only the subgenre's own kit is used.

Runs as a script (`uv run python tests/test_groove.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.contracts import (  # noqa: E402
    Arrangement,
    ArrangementDraft,
    CompositionBrief,
    Layer,
    Note,
    Section,
    SectionKind,
    build_arrangement,
)
from crew.generators import (  # noqa: E402
    VOICES,
    assemble_composition,
    bass_layer,
    drone_layer,
)
from crew.groove import groove_layer, tabla_layer  # noqa: E402
from raga import validate_composition  # noqa: E402
from subgenres import SUBGENRES  # noqa: E402


def _arr(kinds: list[SectionKind], *, bars: int = 1, raga: str = "darbari",
         subgenre: str = "doom", tala: str = "teentaal") -> Arrangement:
    """A real chart with one drums+rhythm+drone section per kind (teentaal = 16-beat
    cycles). `bars=1` keeps the beat math easy to assert."""
    sections = [Section(kind=k, bars=bars, layers=["rhythm", "drums", "drone"],
                        foreground="rhythm") for k in kinds]
    draft = ArrangementDraft(raga=raga, subgenre=subgenre, tala=tala, bpm=80,
                             motif=["S", "R", "g", "R", "g", "m", "P"], sections=sections)
    return build_arrangement(draft, CompositionBrief(mood="dark"))


def _riff(*starts: float) -> Layer:
    """A fake riff layer with notes at the given beats (used to test the kick lock)."""
    v = VOICES["rhythm"]
    notes = [Note(swara="S", oct=-2, start=s, dur=0.5, vel=110) for s in starts]
    return Layer(role="rhythm", instrument=v.instrument, program=v.program,
                 channel=v.channel, notes=notes)


# --- a groove is produced, on the drums channel --------------------------------

def test_groove_is_a_drums_layer_with_hits():
    layer = groove_layer(_arr([SectionKind.RIFF]), None)
    assert layer is not None and layer.role == "drums" and layer.channel == 9
    assert layer.hits and layer.notes is None


def test_no_drums_active_means_no_layer():
    sections = [Section(kind=SectionKind.MELODY, bars=1, layers=["lead", "drone"],
                        foreground="lead")]
    draft = ArrangementDraft(raga="darbari", subgenre="doom", tala="teentaal", bpm=80,
                             motif=["S", "R", "g"], sections=sections)
    arr = build_arrangement(draft, CompositionBrief(mood="dark"))
    assert groove_layer(arr, None) is None


def test_alaap_gets_no_kit():
    # even with drums listed, an alaap is tabla territory — no metal kit.
    assert groove_layer(_arr([SectionKind.ALAAP]), None) is None


# --- the kick locks to the riff ------------------------------------------------

def test_kick_locks_to_the_riff_onbeats():
    arr = _arr([SectionKind.RIFF])              # straight -> pattern kicks on even beats
    layer = groove_layer(arr, _riff(0.0, 5.0, 5.5))
    kicks = {h.start for h in layer.hits if h.drum == "kick"}
    assert 5.0 in kicks                         # riff-locked kick on the odd ON-beat
    assert 5.5 not in kicks                     # the off-beat riff note is not a kick
    assert {0.0, 2.0}.issubset(kicks)           # pattern downbeats still present


# --- feel changes per section kind ---------------------------------------------

def test_breakdown_is_sparser_than_a_straight_riff():
    riff = [h for h in groove_layer(_arr([SectionKind.RIFF]), None).hits if h.drum == "snare"]
    bd = [h for h in groove_layer(_arr([SectionKind.BREAKDOWN]), None).hits if h.drum == "snare"]
    assert len(bd) < len(riff)                  # half-time backbeat = fewer snares


def test_taan_has_denser_hats_than_a_straight_riff():
    riff = [h for h in groove_layer(_arr([SectionKind.RIFF]), None).hits if h.drum == "hhat"]
    taan = [h for h in groove_layer(_arr([SectionKind.TAAN]), None).hits if h.drum == "hhat"]
    assert len(taan) > len(riff)                # double-time -> 8th hats


# --- fills at transitions, and a crash opening each section --------------------

def test_a_tom_fill_lands_before_a_section_change():
    layer = groove_layer(_arr([SectionKind.RIFF, SectionKind.BREAKDOWN]), None)
    # section 1 is [0,16); its fill zone is the last 2 beats [14,16)
    fill = [h for h in layer.hits if h.drum.startswith("tom") and 14.0 <= h.start < 16.0]
    assert fill                                  # a tom fill rolls into the breakdown
    # the LAST section has nothing after it -> no fill in its last beats [30,32)
    tail = [h for h in layer.hits if h.drum.startswith("tom") and 30.0 <= h.start < 32.0]
    assert not tail


def test_each_drum_section_opens_on_a_crash():
    layer = groove_layer(_arr([SectionKind.RIFF, SectionKind.BREAKDOWN]), None)
    accents = {h.start for h in layer.hits if h.drum in ("crash", "china", "ride")}
    assert {0.0, 16.0}.issubset(accents)        # a crash opens each section


# --- kit vocabulary + grammar cleanliness --------------------------------------

def test_only_uses_the_subgenres_kit():
    layer = groove_layer(_arr([SectionKind.RIFF], subgenre="doom"), None)
    assert {h.drum for h in layer.hits} <= set(SUBGENRES["doom"]["drums"]["voices"])


def test_full_rhythm_composition_is_grammar_clean():
    arr = _arr([SectionKind.RIFF])
    riff = _riff(0.0, 4.0, 8.0, 12.0)
    groove = groove_layer(arr, riff)
    bass = bass_layer(arr, riff)
    comp = assemble_composition(arr, [drone_layer(arr), riff, bass, groove])
    # drums carry no pitch (skipped by the grammar); the pitched layers stay legal.
    assert validate_composition(comp.model_dump(exclude_none=True)) == []


# --- the tabla theka -----------------------------------------------------------

def _tabla_arr(*kinds: SectionKind, bars: int = 1, tala: str = "teentaal") -> Arrangement:
    """A chart whose sections list tabla (+ drone)."""
    sections = [Section(kind=k, bars=bars, layers=["tabla", "drone"], foreground="tabla")
                for k in kinds]
    draft = ArrangementDraft(raga="darbari", subgenre="doom", tala=tala, bpm=80,
                             motif=["S", "R", "g"], sections=sections)
    return build_arrangement(draft, CompositionBrief(mood="dark"))


def test_tabla_lays_the_theka_one_position_per_matra():
    layer = tabla_layer(_tabla_arr(SectionKind.ALAAP))   # tabla plays regardless of kind
    assert layer is not None and layer.role == "tabla" and layer.channel == 9
    starts = sorted({h.start for h in layer.hits})
    assert starts == [float(m) for m in range(16)]        # teentaal: 16 matras, one stroke each


def test_tabla_maps_bols_to_conga_voices_only():
    layer = tabla_layer(_tabla_arr(SectionKind.RIFF))
    assert {h.drum for h in layer.hits} <= {"tabla_lo", "tabla_hi"}


def test_tabla_accents_the_sam_over_the_khali():
    layer = tabla_layer(_tabla_arr(SectionKind.RIFF))
    sam = max(h.vel for h in layer.hits if h.start == 0.0)     # matra 1 = sam
    khali = max(h.vel for h in layer.hits if h.start == 8.0)   # matra 9 = teentaal's khali
    assert sam > khali


def test_no_tabla_active_means_no_tabla_layer():
    assert tabla_layer(_arr([SectionKind.RIFF])) is None      # _arr lists no tabla


def test_tabla_and_metal_kit_coexist_on_channel_9():
    sections = [Section(kind=SectionKind.RIFF, bars=1,
                        layers=["rhythm", "drums", "tabla", "drone"], foreground="rhythm")]
    draft = ArrangementDraft(raga="darbari", subgenre="doom", tala="teentaal", bpm=80,
                             motif=["S", "R", "g"], sections=sections)
    arr = build_arrangement(draft, CompositionBrief(mood="dark"))
    drums, tabla = groove_layer(arr, None), tabla_layer(arr)
    assert drums is not None and tabla is not None
    assert drums.channel == tabla.channel == 9                # both GM percussion, they mix


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
