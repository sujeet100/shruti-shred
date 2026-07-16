"""
Tests for the gat verifier — the TIME-legality of the gat's structured cells.

All pure (no key, no cost): the verifiers are deterministic, so their checks — the mukhada
fills the avartan and cadences; the intro resolves to Sa with real rests; the manjha arrives
at the sam and leads back into the head; a taan fill moves in sixteenths and resolves — are
proven here without the LLM. The generation-time RE-ROLL that consumes these violations is
exercised in `tests/test_lead.py`.

Runs as a script (`uv run python tests/test_gat_verifier.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.contracts import LeadNote, LeadPhrase, PhrasePlan  # noqa: E402
from crew.gat_verifier import (  # noqa: E402
    verify_antara,
    verify_fill,
    verify_intro,
    verify_manjha,
    verify_mukhada,
    verify_taan,
)

_PLAN = PhrasePlan(seed=["S"], contour="arch", transformations=["repeat", "resolve"],
                   climax_and_sam="lands on Sa")


def _cell(*notes: LeadNote) -> LeadPhrase:
    return LeadPhrase(phrase_plan=_PLAN, notes=list(notes))


def _n(swara: str, dur: float, **kw) -> LeadNote:
    return LeadNote(swara=swara, dur=dur, **kw)


# --- a clean, one-avartan, landing, varied head passes -------------------------

def test_a_well_formed_mukhada_has_no_violations():
    # malkauns (resting = S, m): fills the 8-beat avartan, lands on Sa, and mixes note
    # values — an 8th for movement against half/full-note nyas points (the 2026-07-16 rule)
    cell = _cell(_n("S", 2.0), _n("g", 1.0), _n("m", 0.5), _n("m", 2.5), _n("S", 2.0))
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
    # the diagnosed failure: a gat of even notes — no mix, no 8th movement
    cell = _cell(_n("S", 2.0), _n("g", 2.0), _n("m", 2.0), _n("S", 2.0))
    viol = verify_mukhada(cell, cycle_beats=8.0, raga="malkauns")
    assert any("note value" in v for v in viol)
    assert any("short note" in v for v in viol)


def test_two_equal_notes_are_not_called_flat():
    # too few notes to be a "flat" pattern (needs >= 3 sounding notes)
    cell = _cell(_n("S", 4.0), _n("m", 4.0))
    assert not any("flat" in v for v in verify_mukhada(cell, cycle_beats=8.0, raga="malkauns"))


# --- degenerate: no sounding notes ----------------------------------------------

def test_an_all_rest_head_is_flagged():
    cell = _cell(_n("S", 4.0, rest=True), _n("S", 4.0, rest=True))
    viol = verify_mukhada(cell, cycle_beats=8.0, raga="malkauns")
    assert len(viol) == 1 and "no sounding notes" in viol[0]


# --- verify_intro: the alap establishes Sa and resolves to it --------------------

_INTRO_PLAN = PhrasePlan(
    seed=["d", "n", "S"], contour="arch", transformations=["fragment", "repeat", "resolve"],
    climax_and_sam="widens to g-m past the midpoint, settles on a held Sa",
    badhat_plan="phrase 1 states d n S low; phrase 2 completes it and adds g; phrase 3 widens to g m")


def _intro_cell(*notes: LeadNote) -> LeadPhrase:
    return LeadPhrase(phrase_plan=_INTRO_PLAN, notes=list(notes))


def _good_intro() -> LeadPhrase:
    # the verified AOCHAR shape (malkauns): THREE short phrases, each developing the ONE motif
    # (d n S) then landing on Sa, separated by real rests; opens on Sa, dips into the mandra,
    # STATES the pakad (g m g S), Sa-anchored (50% by duration), no continuous-Sa wall, reveals
    # the motif progressively (narrow phrase 1; the widest reach — m — past the midpoint), and
    # ends on the longest held Sa (18 beats total).
    return _intro_cell(
        _n("S", 1.0), _n("d", 1.0, oct=-1), _n("n", 1.0, oct=-1), _n("S", 1.5),  # phrase 1 -> Sa
        _n("S", 1.5, rest=True),                                                  # nyas breath
        _n("d", 1.0, oct=-1), _n("n", 1.0, oct=-1), _n("S", 1.0),                 # phrase 2:
        _n("g", 1.0), _n("S", 1.5),                                               #  motif + g -> Sa
        _n("m", 1.5, rest=True),
        _n("g", 1.0), _n("m", 1.0), _n("g", 0.5), _n("S", 2.5))                   # phrase 3 -> held Sa


def test_a_grounded_alap_has_no_violations():
    assert verify_intro(_good_intro(), window_beats=18.0, raga="malkauns") == []


def test_intro_must_open_around_sa():
    cell = _good_intro()
    cell.notes[0] = _n("P", 2.0)               # opens 3 ladder steps from home (darbari, folded)
    viol = verify_intro(cell, window_beats=16.0, raga="darbari")
    assert any("madhya Sa" in v and "opens" in v for v in viol)


def test_intro_must_dip_into_the_mandra():
    cell = _cell(_n("S", 2.0), _n("S", 1.5, rest=True), _n("g", 2.0), _n("m", 3.0),
                 _n("S", 2.0), _n("m", 1.5, rest=True), _n("d", 1.0), _n("S", 3.0))
    viol = verify_intro(cell, window_beats=16.0, raga="malkauns")  # never leaves madhya
    assert any("mandra" in v for v in viol)


def test_intro_needs_several_sa_returns():
    # Sa only at the start and the end (2 returns) — the line never keeps coming home
    cell = _cell(_n("S", 2.0), _n("S", 1.5, rest=True), _n("n", 2.0, oct=-1),
                 _n("d", 3.0, oct=-1), _n("g", 2.0), _n("m", 1.5, rest=True),
                 _n("g", 1.0), _n("S", 5.0))
    viol = verify_intro(cell, window_beats=17.0, raga="malkauns")
    assert any("separate times" in v for v in viol)


def test_intro_must_end_on_sa():
    cell = _cell(_n("S", 4.0), _n("S", 1.5, rest=True), _n("S", 2.0),
                 _n("m", 1.5, rest=True), _n("n", 3.0))          # ends on n, not Sa
    assert any("ends on n" in v for v in verify_intro(cell, window_beats=12.0, raga="malkauns"))


def test_intro_final_sa_must_be_held():
    cell = _cell(_n("S", 4.0), _n("S", 1.5, rest=True), _n("S", 3.0),
                 _n("m", 1.5, rest=True), _n("S", 0.5))          # final Sa too short
    assert any("HOLD" in v for v in verify_intro(cell, window_beats=12.0, raga="malkauns"))


def test_intro_needs_sa_to_carry_a_third_of_the_time():
    cell = _cell(_n("S", 1.0), _n("S", 1.5, rest=True), _n("g", 4.0), _n("m", 4.0),
                 _n("d", 1.5, rest=True), _n("n", 4.0), _n("S", 2.0))   # Sa only 3/15
    assert any("establish Sa" in v for v in verify_intro(cell, window_beats=18.0, raga="malkauns"))


def test_intro_needs_two_real_rests():
    cell = _cell(_n("S", 3.0), _n("S", 1.5, rest=True), _n("g", 2.0), _n("S", 3.0))
    assert any("rest" in v and "breathes" in v for v in verify_intro(cell, window_beats=10.0, raga="malkauns"))


def test_intro_needs_a_rest_after_a_sa_landing():
    # two rests, but neither follows a Sa — the nyas breath is missing
    cell = _cell(_n("g", 1.0), _n("g", 1.5, rest=True), _n("S", 3.0), _n("m", 1.0),
                 _n("m", 1.5, rest=True), _n("S", 3.0))
    assert any("nyas" in v for v in verify_intro(cell, window_beats=11.0, raga="malkauns"))


def test_intro_must_not_spill_into_the_reserved_silence():
    # a fine alap, but 16 beats into a 12-beat window — it would erase the code-reserved pause
    viol = verify_intro(_good_intro(), window_beats=12.0, raga="malkauns")
    assert any("silence" in v for v in viol)


def test_intro_with_no_sounding_notes_is_flagged():
    viol = verify_intro(_cell(_n("S", 4.0, rest=True)), window_beats=12.0, raga="malkauns")
    assert len(viol) == 1 and "no sounding notes" in viol[0]


# --- verify_intro: the alap is phrases (explore -> Sa -> silence), not a continuous Sa wall ----

def test_intro_must_be_several_phrases_not_one_continuous_line():
    # one unbroken phrase (no rests) — the 'continuous line' failure
    cell = _cell(_n("S", 1.0), _n("n", 1.0, oct=-1), _n("d", 1.0, oct=-1),
                 _n("m", 1.0), _n("g", 1.0), _n("S", 3.0))
    viol = verify_intro(cell, window_beats=16.0, raga="malkauns")
    assert any("INDEPENDENT phrases" in v for v in viol)


def test_intro_every_phrase_must_resolve_to_sa():
    # phrase 2 ends on d, not Sa, before its rest
    cell = _cell(_n("S", 1.0), _n("n", 1.0, oct=-1), _n("S", 1.5),
                 _n("S", 1.5, rest=True),
                 _n("g", 1.0), _n("m", 1.0), _n("d", 2.0),          # phrase 2 -> d (not Sa)
                 _n("m", 1.5, rest=True),
                 _n("g", 1.0), _n("m", 1.0), _n("S", 2.5))
    viol = verify_intro(cell, window_beats=16.0, raga="malkauns")
    assert any("RESOLVE home to Sa" in v for v in viol)


def test_intro_a_phrase_must_explore_not_be_bare_sa():
    # phrase 2 is only Sa — a drone, not a sentence
    cell = _cell(_n("S", 1.0), _n("n", 1.0, oct=-1), _n("S", 1.5),
                 _n("S", 1.5, rest=True),
                 _n("S", 2.0),                                       # phrase 2: bare Sa
                 _n("m", 1.5, rest=True),
                 _n("g", 1.0), _n("m", 1.0), _n("S", 2.5))
    viol = verify_intro(cell, window_beats=16.0, raga="malkauns")
    assert any("bare Sa" in v for v in viol)


def test_intro_must_not_dwell_on_sa_continuously():
    # a phrase repeats Sa for 4.5 continuous beats — the 'Sa played continuously' failure
    cell = _cell(_n("S", 1.0), _n("n", 1.0, oct=-1), _n("S", 1.5),
                 _n("S", 1.5, rest=True),
                 _n("g", 1.0), _n("S", 1.5), _n("S", 1.5), _n("S", 1.5),   # 4.5 beats of Sa
                 _n("m", 1.5, rest=True),
                 _n("g", 1.0), _n("S", 2.5))
    viol = verify_intro(cell, window_beats=18.0, raga="malkauns")
    assert any("continuous beats" in v for v in viol)


def test_intro_must_state_the_pakad():
    # uses only Sa and Ma — grounded and phrased, but never states malkauns's pakad (d n S / g m g)
    cell = _cell(_n("S", 1.0), _n("m", 1.5, oct=-1), _n("S", 1.5),
                 _n("S", 1.5, rest=True),
                 _n("m", 2.0, oct=-1), _n("S", 2.0),
                 _n("m", 1.5, rest=True),
                 _n("m", 1.0), _n("S", 2.5))
    viol = verify_intro(cell, window_beats=16.0, raga="malkauns")
    assert any("PAKAD" in v for v in viol)


# --- verify_intro: ONE motif, progressively revealed (badhat) ---------------------

_GAT_HEAD = LeadPhrase(phrase_plan=_PLAN, notes=[
    _n("d", 1.0), _n("n", 1.0), _n("S", 1.5), _n("m", 1.5),
    _n("g", 1.0), _n("m", 1.0), _n("g", 1.5), _n("S", 1.5)])   # d n S m | g m g S


def test_intro_motif_drawn_from_the_head_passes():
    # the good intro's motif (d n S) IS the head's opening — teasing the gat, no violations
    assert verify_intro(_good_intro(), window_beats=18.0, raga="malkauns",
                        mukhada=_GAT_HEAD) == []


def test_intro_motif_not_in_the_head_is_flagged():
    # m d n never appears in the head (in order) — the intro would tease a DIFFERENT tune
    cell = LeadPhrase(phrase_plan=_INTRO_PLAN.model_copy(update={"seed": ["m", "d", "n"]}),
                      notes=_good_intro().notes)
    viol = verify_intro(cell, window_beats=18.0, raga="malkauns", mukhada=_GAT_HEAD)
    assert any("not drawn from the mukhada head" in v for v in viol)


def test_intro_every_phrase_must_touch_the_motif():
    # phrase 2 develops nothing of the motif (g m S, no d n) — episodic, not ONE thought
    cell = _intro_cell(
        _n("S", 1.0), _n("d", 1.0, oct=-1), _n("n", 1.0, oct=-1), _n("S", 1.5),
        _n("S", 1.5, rest=True),
        _n("g", 1.0), _n("m", 1.0), _n("S", 1.5),                 # phrase 2: a NEW phrase
        _n("m", 1.5, rest=True),
        _n("g", 1.0), _n("m", 1.0), _n("g", 0.5), _n("S", 2.5))
    viol = verify_intro(cell, window_beats=16.0, raga="malkauns")
    assert any("never touches the motif" in v for v in viol)


def test_intro_must_state_the_full_motif():
    # the anchors (d n) recur but the full motif (d n S m) never completes — no reveal
    cell = LeadPhrase(phrase_plan=_INTRO_PLAN.model_copy(update={"seed": ["d", "n", "S", "m"]}),
                      notes=_good_intro().notes)
    viol = verify_intro(cell, window_beats=18.0, raga="malkauns")
    assert any("never stated" in v for v in viol)


def test_intro_opening_phrase_must_stay_narrow():
    # phrase 1 leaps to taar Sa — the two-octaves-in-four-seconds failure heard live
    cell = _good_intro()
    cell.notes[3] = _n("S", 1.5, oct=1)
    viol = verify_intro(cell, window_beats=18.0, raga="malkauns")
    assert any("opening phrase spans" in v for v in viol)


def test_intro_highest_note_must_arrive_late():
    # a fine motif-driven alap whose widest reach (m) lands in phrase 1 — badhat inverted
    cell = LeadPhrase(
        phrase_plan=_INTRO_PLAN.model_copy(update={"seed": ["g", "m"]}),
        notes=[_n("S", 1.0), _n("g", 1.0), _n("m", 1.0), _n("S", 1.5),
               _n("S", 1.5, rest=True),
               _n("d", 1.0, oct=-1), _n("n", 1.0, oct=-1), _n("g", 1.0), _n("m", 1.0), _n("S", 1.5),
               _n("m", 1.5, rest=True),
               _n("g", 1.0), _n("m", 1.0), _n("g", 1.5), _n("S", 2.5)])
    viol = verify_intro(cell, window_beats=19.0, raga="malkauns")
    assert any("arrives too early" in v for v in viol)


def test_intro_must_declare_a_real_motif():
    # a one-swara seed is not a motif — the intro must name the ONE idea it develops
    cell = LeadPhrase(phrase_plan=_PLAN, notes=_good_intro().notes)   # seed = ["S"]
    viol = verify_intro(cell, window_beats=18.0, raga="malkauns")
    assert any("declares no usable motif" in v for v in viol)


# --- verify_intro: the AUDIBLE line (a meend is heard at its TARGET) ---------------

def test_a_meend_spammed_intro_fails_on_its_audible_line():
    # the 2026-07-16 live failure in miniature: WRITTEN as motif phrases, but every note
    # meends to Sa — the ear gets one repeated note. The audible-line checks + the meend
    # rate cap must all see through the written swaras.
    cell = _good_intro()
    cell.notes = [n if n.rest else n.model_copy(update={"meend_swara": "S"})
                  for n in cell.notes]
    viol = verify_intro(cell, window_beats=18.0, raga="malkauns")
    assert any("meend" in v for v in viol)                    # the rate cap names the cause
    assert any("motif" in v or "Sa" in v for v in viol)       # and the audible line collapses


def test_audible_line_reads_the_meend_target_octave():
    # a written-madhya note meending to taar Sa IS a taar reach — the audible peak
    cell = _good_intro()
    cell.notes[2] = _n("n", 1.0, oct=-1, meend_swara="S", meend_oct=1)   # audibly taar Sa, early
    viol = verify_intro(cell, window_beats=18.0, raga="malkauns")
    assert any("opening phrase spans" in v or "too early" in v for v in viol)


def test_a_noop_meend_does_not_trip_the_audible_checks():
    # meend_swara == the written pitch: no glide, nothing changes audibly — still clean
    cell = _good_intro()
    cell.notes[0] = cell.notes[0].model_copy(update={"meend_swara": "S"})   # S -> S
    assert verify_intro(cell, window_beats=18.0, raga="malkauns") == []


# --- verify_manjha: arrive at the sam, lead back into the head -------------------

_HEAD = LeadPhrase(phrase_plan=_PLAN,
                   notes=[LeadNote(swara="S", dur=3.0), LeadNote(swara="m", dur=2.0),
                          LeadNote(swara="g", dur=1.0), LeadNote(swara="S", dur=2.0)])


def _good_manjha() -> LeadPhrase:
    # a LOW bridge: fills a 16-beat window, DIPS into the mandra, stays out of the taar, varied
    # durations, ends a single ladder-step from the head's first swara (n -> S in malkauns)
    return _cell(_n("d", 3.0, oct=-1), _n("n", 2.0, oct=-1), _n("m", 3.0), _n("g", 2.5),
                 _n("m", 2.0), _n("d", 1.5), _n("n", 2.0))


def test_a_returning_manjha_has_no_violations():
    assert verify_manjha(_good_manjha(), mukhada=_HEAD, window_beats=16.0,
                         raga="malkauns") == []


def test_manjha_must_fill_its_window_to_the_sam():
    cell = _cell(_n("d", 3.0), _n("n", 2.0), _n("S", 2.0))       # 7 of 16 beats — dies early
    viol = verify_manjha(cell, mukhada=_HEAD, window_beats=16.0, raga="malkauns")
    assert any("closing sam" in v for v in viol)


def test_manjha_must_lead_back_into_the_heads_first_swara():
    # ends on d — two-plus ladder steps from the head's opening S (S<-n<-d is 2? d..S:
    # ladder S g m d n -> d to S is 2 steps; use g? g to S is 1... pick the far swara m)
    cell = _cell(_n("d", 3.0), _n("n", 2.5), _n("g", 3.0), _n("d", 2.0),
                 _n("n", 3.0), _n("m", 2.5))                     # m -> S: 2 steps down... still ok
    # malkauns ladder is S g m d n: m is 2 steps from S (allowed); pick d? also 2 (folded).
    # The genuinely far swara in a 5-note ladder doesn't exist (max fold = 2), so test the
    # seam with a 7-note raga instead: darbari ladder S R g m P d n — P is 3 steps from S.
    cell = _cell(_n("R", 3.0), _n("g", 2.5), _n("m", 3.0), _n("d", 2.0),
                 _n("n", 3.0), _n("P", 2.5))
    viol = verify_manjha(cell, mukhada=_HEAD, window_beats=16.0, raga="darbari")
    assert any("lead" in v and "fluid" in v for v in viol)


def test_manjha_flags_a_flat_run():
    cell = _cell(*[_n(s, 2.0) for s in ("d", "n", "m", "g", "m", "d", "n", "n")])
    viol = verify_manjha(cell, mukhada=_HEAD, window_beats=16.0, raga="malkauns")
    assert any("flat" in v for v in viol)


def test_manjha_must_dip_into_the_mandra():
    # a manjha that stays at/above home never becomes the LOW bridge (Parikh)
    cell = _cell(_n("m", 3.0), _n("g", 2.5), _n("m", 3.0), _n("g", 2.5),
                 _n("m", 2.0), _n("n", 3.0))                 # all in the madhya octave
    viol = verify_manjha(cell, mukhada=_HEAD, window_beats=16.0, raga="malkauns")
    assert any("mandra" in v for v in viol)


def test_manjha_must_not_climb_into_the_taar():
    # the taar (upper octave) is the ANTARA's job, not the manjha's
    cell = _cell(_n("d", 3.0, oct=-1), _n("n", 2.0), _n("m", 3.0, oct=1),   # m sits in the taar
                 _n("g", 2.5), _n("m", 3.0), _n("n", 2.5))
    viol = verify_manjha(cell, mukhada=_HEAD, window_beats=16.0, raga="malkauns")
    assert any("taar" in v for v in viol)


# --- verify_antara: quote the head, climb, peak late, descend to madhya Sa -------

def _good_antara() -> LeadPhrase:
    # opens by quoting the head's first swaras (S m g S, one passing note allowed), climbs
    # into the taar past the midpoint, peaks once, descends to a held madhya Sa
    return _cell(_n("S", 2.0), _n("m", 1.5), _n("g", 1.0), _n("S", 2.0),      # the quote (madhya)
                 _n("d", 1.0), _n("n", 1.5), _n("S", 1.0, oct=1),             # the climb
                 _n("g", 2.0, oct=1), _n("m", 1.0, oct=1),                    # the taar peak (late)
                 _n("g", 1.0, oct=1), _n("S", 1.0, oct=1), _n("n", 1.0),
                 _n("d", 1.0), _n("m", 1.0), _n("S", 3.0))                    # the descent home


def test_a_well_arced_antara_has_no_violations():
    assert verify_antara(_good_antara(), mukhada=_HEAD, window_beats=21.0,
                         raga="malkauns") == []


def test_antara_must_quote_the_heads_opening():
    # a taar arc that never restates the head — the "new tune" failure
    cell = _cell(_n("d", 2.0), _n("n", 1.5), _n("d", 1.0), _n("n", 2.0),
                 _n("g", 2.0, oct=1), _n("n", 1.0), _n("d", 1.0), _n("S", 3.0))
    viol = verify_antara(cell, mukhada=_HEAD, window_beats=14.0, raga="malkauns")
    assert any("quote" in v for v in viol)


def test_antara_must_not_open_in_the_taar():
    cell = _good_antara()
    cell.notes[0] = _n("S", 2.0, oct=1)                      # opens already at the top
    viol = verify_antara(cell, mukhada=_HEAD, window_beats=21.0, raga="malkauns")
    assert any("opens already" in v for v in viol)


def test_antara_must_reach_the_taar_octave():
    cell = _cell(_n("S", 2.0), _n("m", 1.5), _n("g", 1.0), _n("S", 2.0),
                 _n("d", 1.0), _n("m", 2.0), _n("S", 3.0))   # never leaves madhya
    viol = verify_antara(cell, mukhada=_HEAD, window_beats=13.0, raga="malkauns")
    assert any("taar" in v for v in viol)


def test_antara_peak_must_arrive_late_and_not_be_the_exit():
    # peak in the FIRST notes -> too early
    early = _cell(_n("S", 1.0), _n("m", 0.5), _n("g", 0.5), _n("S", 0.5), _n("m", 1.0, oct=1),
                  _n("g", 2.0), _n("m", 2.0), _n("d", 2.0), _n("m", 2.0), _n("S", 3.0))
    assert any("too early" in v for v in verify_antara(early, mukhada=_HEAD, window_beats=15.0,
                                                       raga="malkauns"))
    # ends ON the peak -> no descent
    ending_high = _cell(_n("S", 2.0), _n("m", 1.5), _n("g", 1.0), _n("S", 2.0),
                        _n("d", 2.0), _n("n", 2.0), _n("m", 2.0, oct=1))
    viol = verify_antara(ending_high, mukhada=_HEAD, window_beats=13.0, raga="malkauns")
    assert any("highest note" in v and "DESCEND" in v for v in viol)


def test_antara_must_rest_on_madhya_sa():
    cell = _good_antara()
    cell.notes[-1] = _n("g", 3.0)                            # ends adrift, not home
    viol = verify_antara(cell, mukhada=_HEAD, window_beats=21.0, raga="malkauns")
    assert any("madhya Sa" in v for v in viol)


# --- verify_taan: motif-grown, arced, lands, bursts against space ----------------

_MOTIF = ["S", "g", "m", "d"]


def _good_taan() -> LeadPhrase:
    # grows from the motif (S g m d opens it), climbs to one late taar peak, has a 16th
    # burst + a held nyas + mixed durations, and lands on Sa
    return _cell(_n("S", 0.5), _n("g", 0.5), _n("m", 0.5), _n("d", 0.5),      # the motif stated
                 _n("m", 2.0),                                                # a held breath
                 _n("g", 0.25), _n("m", 0.25), _n("d", 0.25), _n("n", 0.25),  # burst
                 _n("d", 0.25), _n("n", 0.25), _n("S", 0.25, oct=1), _n("g", 0.25, oct=1),
                 _n("m", 1.0, oct=1),                                         # the late peak
                 _n("g", 0.25, oct=1), _n("S", 0.25, oct=1), _n("n", 0.25), _n("d", 0.25),
                 _n("n", 0.25), _n("d", 0.25), _n("m", 0.25), _n("g", 0.25),  # the cadential run
                 _n("S", 2.0))                                                # ...lands on the sam


def test_a_concert_taan_has_no_violations():
    assert verify_taan(_good_taan(), motif=_MOTIF, window_beats=12.0,
                       raga="malkauns") == []


def test_taan_must_grow_from_the_motif():
    # fast and arced, but never states the motif's shape
    cell = _cell(_n("d", 0.5), _n("n", 0.5), _n("d", 0.25), _n("n", 0.25), _n("d", 0.25),
                 _n("n", 0.25), _n("d", 2.0), _n("g", 0.25, oct=1), _n("n", 0.25),
                 _n("d", 0.5), _n("S", 1.0))
    viol = verify_taan(cell, motif=_MOTIF, window_beats=6.0, raga="malkauns")
    assert any("motif" in v for v in viol)


def test_taan_needs_a_sixteenth_burst():
    cell = _cell(_n("S", 0.5), _n("g", 0.5), _n("m", 0.5), _n("d", 0.5), _n("m", 2.0),
                 _n("S", 0.5, oct=1), _n("n", 0.5), _n("d", 0.5), _n("S", 1.0))
    viol = verify_taan(cell, motif=_MOTIF, window_beats=7.0, raga="malkauns")
    assert any("burst" in v for v in viol)


def test_taan_needs_space_against_the_speed():
    # all motion, no rest, nothing held a beat — it never breathes
    swaras = ["S", "g", "m", "d", "m", "g", "m", "d", "n", "d", "S", "g"]
    cell = _cell(*[_n(s, 0.25, oct=(1 if i in (10, 11) else 0)) for i, s in enumerate(swaras)],
                 _n("m", 0.5, oct=1), _n("g", 0.5), _n("S", 0.5))
    viol = verify_taan(cell, motif=_MOTIF, window_beats=5.0, raga="malkauns")
    assert any("breathes" in v for v in viol)


def test_taan_must_land_on_a_resting_swara():
    cell = _good_taan()
    cell.notes[-1] = _n("n", 2.0)                            # ends adrift
    viol = verify_taan(cell, motif=_MOTIF, window_beats=12.0, raga="malkauns")
    assert any("resting swara" in v for v in viol)


def test_taan_shares_the_earned_arc_rules():
    # never reaches the taar -> the shared arc check fires for the taan too
    cell = _cell(_n("S", 0.5), _n("g", 0.5), _n("m", 0.5), _n("d", 0.5), _n("m", 2.0),
                 _n("g", 0.25), _n("m", 0.25), _n("d", 0.25), _n("n", 0.25), _n("S", 1.0))
    viol = verify_taan(cell, motif=_MOTIF, window_beats=6.0, raga="malkauns")
    assert any("taar" in v for v in viol)


# --- verify_fill: sixteenths, exact length, resolves into the head ---------------

def _good_fill() -> LeadPhrase:
    # 15 sixteenths + a 0.25 landing = exactly 4 beats, ending on the head's first swara
    swaras = (["m", "g", "m", "d", "n", "d", "m", "g"] * 2)[:15] + ["S"]
    return _cell(*[_n(s, 0.25) for s in swaras])


def test_a_clean_taan_fill_has_no_violations():
    assert verify_fill(_good_fill(), mukhada=_HEAD, window_beats=4.0, raga="malkauns") == []


def test_fill_must_move_in_sixteenths():
    cell = _cell(_n("m", 1.0), _n("g", 1.0), _n("m", 1.0), _n("S", 1.0))   # quarters, not a taan
    viol = verify_fill(cell, mukhada=_HEAD, window_beats=4.0, raga="malkauns")
    assert any("SIXTEENTHS" in v for v in viol)


def test_fill_may_land_on_one_longer_note():
    swaras = ["m", "g", "m", "d", "n", "d", "m", "g", "m", "g", "m", "d"]
    cell = _cell(*[_n(s, 0.25) for s in swaras], _n("S", 1.0))   # 3 beats of 16ths + a landing
    assert verify_fill(cell, mukhada=_HEAD, window_beats=4.0, raga="malkauns") == []


def test_fill_must_match_its_cut_length():
    cell = _cell(*[_n(s, 0.25) for s in ("m", "g", "m", "d", "n", "d", "m", "S")])   # 2 of 4 beats
    viol = verify_fill(cell, mukhada=_HEAD, window_beats=4.0, raga="malkauns")
    assert any("almost exactly" in v for v in viol)


def test_fill_must_resolve_into_the_head():
    # darbari ladder: ends on P, 3 steps from the head's opening S -> the seam fails
    swaras = (["R", "g", "m", "P", "d", "P", "m", "g"] * 2)[:15] + ["P"]
    cell = _cell(*[_n(s, 0.25) for s in swaras])
    viol = verify_fill(cell, mukhada=_HEAD, window_beats=4.0, raga="darbari")
    assert any("taan fill" in v and "fluid" in v for v in viol)


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
