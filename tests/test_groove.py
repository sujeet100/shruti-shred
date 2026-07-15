"""
Tests for the Groove / Drums engine — all pure (no key, no cost).

The groove is deterministic, so everything the user asked about is provable here
without the LLM: the subgenre plays ITS pattern (death blasts, thrash skanks, heavy
gallops), the kick LOCKS to the riff's on-beats, the energy changes per section
kind AND gat form_role (the antara rides half-time; a taan is denser than a riff),
the tala shapes the kit (tali leans in, khali sits back, A-A-A-B turnarounds group
short cycles), fills land mid-section and at every seam (bigger into a climax), a
kit entrance after silence gets a pickup roll / stop hits, ghost notes and bounded
deterministic velocities carry the humanity, and only the subgenre's own kit is used.

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
         subgenre: str = "doom", tala: str = "teentaal",
         form_roles: list[str | None] | None = None) -> Arrangement:
    """A real chart with one drums+rhythm+drone section per kind (teentaal = 16-beat
    cycles). `bars=1` keeps the beat math easy to assert."""
    roles = form_roles or [None] * len(kinds)
    sections = [Section(kind=k, bars=bars, layers=["rhythm", "drums", "drone"],
                        foreground="rhythm", form_role=r)
                for k, r in zip(kinds, roles)]
    draft = ArrangementDraft(raga=raga, subgenre=subgenre, tala=tala, bpm=80,
                             motif=["S", "R", "g", "R", "g", "m", "P"], sections=sections)
    return build_arrangement(draft, CompositionBrief(mood="dark"))


def _riff(*starts: float) -> Layer:
    """A fake riff layer with notes at the given beats (used to test the kick lock)."""
    v = VOICES["rhythm"]
    notes = [Note(swara="S", oct=-2, start=s, dur=0.5, vel=110) for s in starts]
    return Layer(role="rhythm", instrument=v.instrument, program=v.program,
                 channel=v.channel, notes=notes)


def _backbeats(layer: Layer) -> list:
    """The audible snare backbeats (ghosts sit far below 100)."""
    return [h for h in layer.hits if h.drum == "snare" and h.vel >= 100]


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


def test_groove_is_deterministic():
    a = groove_layer(_arr([SectionKind.RIFF, SectionKind.TAAN]), None)
    b = groove_layer(_arr([SectionKind.RIFF, SectionKind.TAAN]), None)
    assert [(h.drum, h.start, h.vel) for h in a.hits] == \
           [(h.drum, h.start, h.vel) for h in b.hits]


def test_velocities_stay_in_midi_range():
    for sub in SUBGENRES:
        layer = groove_layer(_arr([SectionKind.RIFF, SectionKind.TAAN], subgenre=sub), None)
        assert all(1 <= h.vel <= 127 for h in layer.hits), sub


# --- the subgenre plays ITS pattern, not a generic pop beat ---------------------

def test_death_riff_plays_a_blast():
    # the traditional blast: the snare fills the off-16ths BETWEEN the kicks
    layer = groove_layer(_arr([SectionKind.RIFF], subgenre="death"), None)
    snares = {h.start for h in layer.hits if h.drum == "snare"}
    kicks = {h.start for h in layer.hits if h.drum == "kick"}
    assert {0.25, 0.75, 1.25, 1.75} <= snares
    assert {0.0, 0.5, 1.0, 1.5} <= kicks


def test_thrash_riff_plays_a_skank():
    # kick on every quarter, snare on every off-8th — the 2/4 polka at speed
    layer = groove_layer(_arr([SectionKind.RIFF], subgenre="thrash"), None)
    snares = {h.start for h in _backbeats(layer)}
    assert {0.5, 1.5, 2.5, 3.5} <= snares


def test_heavy_riff_plays_a_gallop_kick():
    # the 8th + two-16th kick cell under every beat
    layer = groove_layer(_arr([SectionKind.RIFF], subgenre="heavy"), None)
    kicks = {h.start for h in layer.hits if h.drum == "kick"}
    assert {1.0, 1.5, 1.75, 2.0, 2.5, 2.75} <= kicks


# --- the kick locks to the riff ------------------------------------------------

def test_kick_locks_to_the_riff_onbeats():
    arr = _arr([SectionKind.RIFF])              # doom drive: kick pairs on 1 & 3
    layer = groove_layer(arr, _riff(0.0, 5.0, 5.5))
    kicks = {h.start for h in layer.hits if h.drum == "kick"}
    assert 5.0 in kicks                         # riff-locked kick on the odd ON-beat
    assert 5.5 not in kicks                     # the off-beat riff note is not a kick
    assert {0.0, 2.0}.issubset(kicks)           # pattern downbeats still present


def test_prog_kick_shadows_every_riff_onset():
    # progressive "follow": the kick plays the riff's 16th-grid rhythm too
    arr = _arr([SectionKind.RIFF], subgenre="progressive")
    layer = groove_layer(arr, _riff(0.0, 5.0, 5.5))
    kicks = {h.start for h in layer.hits if h.drum == "kick"}
    assert 5.5 in kicks                         # the off-beat onset IS a kick for prog


# --- energy changes per section kind AND gat form_role --------------------------

def test_breakdown_is_sparser_than_a_straight_riff():
    riff = _backbeats(groove_layer(_arr([SectionKind.RIFF]), None))
    bd = _backbeats(groove_layer(_arr([SectionKind.BREAKDOWN]), None))
    assert len(bd) < len(riff)                  # half-time = fewer audible backbeats


def test_taan_is_denser_than_a_straight_riff():
    riff = groove_layer(_arr([SectionKind.RIFF], subgenre="heavy"), None)
    taan = groove_layer(_arr([SectionKind.TAAN], subgenre="heavy"), None)
    assert len(taan.hits) > len(riff.hits)      # the climax pattern is the busiest


def test_antara_rides_half_time():
    # the user-facing ask: the antara sits back on the RIDE, no crash washing,
    # half the backbeats of a drive section.
    arr = _arr([SectionKind.MELODY], subgenre="heavy", form_roles=["antara"])
    layer = groove_layer(arr, None)
    drums = {h.drum for h in layer.hits}
    assert drums & {"ride", "bell"}             # ride-led timekeeping
    assert "crash" not in drums                 # the sam gets the bell, not a crash
    assert len(_backbeats(layer)) == 4          # one snare per vibhag = half-time


# --- the tala shapes the kit: tali leans in, khali sits back, A-A-A-B -----------

def test_khali_vibhag_sits_back():
    layer = groove_layer(_arr([SectionKind.RIFF], subgenre="thrash"), None)
    cymbals = ("hhat", "ride", "bell")
    tali = max(h.vel for h in layer.hits if h.start == 4.0 and h.drum in cymbals)
    khali = max(h.vel for h in layer.hits if h.start == 8.0 and h.drum in cymbals)
    assert khali < tali                         # teentaal: beat 4 = tali, beat 8 = khali


def test_short_cycles_group_into_one_phrase_turnaround():
    # keherwa (8 beats) groups 2 cycles per phrase: the turnaround kick pair lands
    # only at the PHRASE end (A A A B), not at every cycle end.
    arr = _arr([SectionKind.RIFF], subgenre="thrash", tala="keherwa", bars=2)
    kicks = {h.start for h in groove_layer(arr, None).hits if h.drum == "kick"}
    assert 15.5 in kicks and 15.75 in kicks     # the 16th pair into the phrase's sam
    assert 7.5 not in kicks                     # bar 1 stays clean (it's an "A" bar)


# --- fills: mid-section, at every seam, bigger into a climax --------------------

def test_a_tom_fill_lands_before_a_section_change():
    layer = groove_layer(_arr([SectionKind.RIFF, SectionKind.BREAKDOWN]), None)
    # section 1 is [0,16); its fill zone is the last 2 beats [14,16)
    fill = [h for h in layer.hits if h.drum.startswith("tom") and 14.0 <= h.start < 16.0]
    assert fill                                  # a tom fill rolls into the breakdown
    # the LAST section has nothing after it -> no fill in its last beats [30,32)
    tail = [h for h in layer.hits if h.drum.startswith("tom") and 30.0 <= h.start < 32.0]
    assert not tail


def test_fills_crescendo():
    layer = groove_layer(_arr([SectionKind.RIFF, SectionKind.BREAKDOWN]), None)
    fill = sorted((h for h in layer.hits
                   if h.drum in ("snare", "tom_lo") and 14.0 <= h.start < 16.0),
                  key=lambda h: h.start)
    assert fill[-1].vel > fill[0].vel + 15       # the run swells into the crash


def test_a_bigger_fill_leads_into_the_climax():
    layer = groove_layer(_arr([SectionKind.RIFF, SectionKind.TAAN], subgenre="heavy"), None)
    fill = [h for h in layer.hits if h.drum.startswith("tom") and 12.0 <= h.start < 16.0]
    assert len(fill) >= 6                        # a full-vibhag crescendo run


def test_mid_section_mini_fill():
    # teentaal phrase = 1 cycle -> a mini-fill closes every 2nd cycle mid-section
    layer = groove_layer(_arr([SectionKind.RIFF], bars=4), None)
    toms = [h for h in layer.hits if h.drum.startswith("tom") and 31.0 <= h.start < 32.0]
    assert toms


def test_each_drum_section_opens_on_a_crash():
    layer = groove_layer(_arr([SectionKind.RIFF, SectionKind.BREAKDOWN]), None)
    accents = {h.start for h in layer.hits if h.drum in ("crash", "china", "ride", "bell")}
    assert {0.0, 16.0}.issubset(accents)        # an accent cymbal opens each section


# --- the band entrance: pickup roll, everything-at-127, stop hits ---------------

def test_entrance_gets_a_pickup_roll_and_a_big_downbeat():
    layer = groove_layer(_arr([SectionKind.ALAAP, SectionKind.RIFF]), None)
    pickup = sorted((h for h in layer.hits if h.drum == "snare" and 15.0 <= h.start < 16.0),
                    key=lambda h: h.start)
    assert len(pickup) == 4                     # a 16th roll swells out of the alaap
    assert pickup[-1].vel > pickup[0].vel + 30
    entrance = [h for h in layer.hits
                if h.start == 16.0 and h.drum in ("crash", "china", "ride", "bell")]
    assert entrance and max(h.vel for h in entrance) >= 120   # everything at ~127


def test_stop_hits_match_a_spaced_riff_entrance():
    arr = _arr([SectionKind.ALAAP, SectionKind.RIFF])
    layer = groove_layer(arr, _riff(16.0, 18.0))   # two spaced accents open the riff
    stabs = {h.start for h in layer.hits if h.drum == "crash" and h.vel >= 120}
    assert {16.0, 18.0} <= stabs                # unison crash+kick matches each accent
    cyms = [h for h in layer.hits
            if h.drum in ("hhat", "ride", "bell") and 16.0 <= h.start < 20.0]
    assert not cyms                             # the groove holds back until vibhag 2


# --- humanity: ghost notes ------------------------------------------------------

def test_ghost_notes_in_a_verse_groove():
    layer = groove_layer(_arr([SectionKind.MELODY], subgenre="heavy"), None)
    ghosts = [h for h in layer.hits if h.drum == "snare" and h.vel < 60]
    assert ghosts                               # the pockets between backbeats breathe


# --- kit vocabulary + grammar cleanliness --------------------------------------

def test_only_uses_the_subgenres_kit():
    for sub in SUBGENRES:
        arr = _arr([SectionKind.RIFF, SectionKind.BREAKDOWN, SectionKind.TAAN], subgenre=sub)
        layer = groove_layer(arr, None)
        assert {h.drum for h in layer.hits} <= set(SUBGENRES[sub]["drums"]["voices"]), sub


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
