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

from crew.contracts import HeadStage, LeadNote, LeadPhrase, PhrasePlan, TaanPhrase  # noqa: E402
from crew.gat_verifier import (
    # noqa: E402,
    check_amad,
    check_antara,
    check_bol_frame,
    check_fill,
    check_head_plan,
    check_head_shape,
    check_intro,
    check_manjha,
    check_mukhada,
    check_outro,
    check_stroke_line,
    check_taan,
    reentry_swara,
    stroke_line_match,
    verify_amad,
    verify_antara,
    verify_bol_frame,
    verify_fill,
    verify_intro,
    verify_manjha,
    verify_mukhada,
    verify_taan,
)

_PLAN = PhrasePlan(seed=["S"], contour="arch", transformations=["repeat", "resolve"],
                   climax_and_sam="lands on Sa")


def _craft(check, *args, **kwargs) -> list[str]:
    """The ADVISORY notes a check reports (craft rules no longer reject a cell — see CellChecks)."""
    return list(check(*args, **kwargs).craft)


def _cell(*notes: LeadNote) -> LeadPhrase:
    return LeadPhrase(phrase_plan=_PLAN, notes=list(notes))


def _n(swara: str, dur: float, **kw) -> LeadNote:
    return LeadNote(swara=swara, dur=dur, **kw)


# --- a clean, one-avartan, landing, varied head passes -------------------------

def test_a_well_formed_mukhada_has_no_violations():
    # malkauns (resting = S, m): fills the 8-beat avartan, moves at a STEADY PULSE with a
    # held nyas to rest on, and cadences to a different swara than it opened with, so the
    # sam is audible when it loops (the 2026-09-14 rule, from the gats Sujit is learning)
    cell = _cell(_n("S", 1.0), _n("g", 1.0), _n("m", 1.0), _n("S", 1.0),
                 _n("g", 1.0), _n("m", 1.0), _n("m", 2.0))
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
    # ends on D — the one swara Yaman must never rest on (Parrikar: "damaging to the raga
    # dharma"). Malkauns' n used to be the example, until the nyas research: every Malkauns
    # swara is apposite for nyas.
    cell = _cell(_n("S", 3.0), _n("G", 3.0), _n("D", 2.0))
    viol = verify_mukhada(cell, cycle_beats=8.0, raga="yaman")
    assert any("resting swara" in v for v in viol)


def test_a_head_landing_on_the_vadi_is_accepted():
    cell = _cell(_n("S", 3.0), _n("d", 2.0), _n("m", 3.0))   # lands on the vadi m
    assert not any("resting swara" in v
                   for v in verify_mukhada(cell, cycle_beats=8.0, raga="malkauns"))


def test_a_chikari_ending_counts_as_landing_on_sa():
    # a chikari sounds taar Sa regardless of its written swara, so it lands on a resting note
    cell = _cell(_n("S", 2.0), _n("m", 2.0), _n("g", 2.0), _n("n", 2.0, bol="chikari"))
    assert not any("resting swara" in v
                   for v in verify_mukhada(cell, cycle_beats=8.0, raga="malkauns"))


# --- not rhythmically flat ------------------------------------------------------

def test_the_heads_note_values_are_the_composers_call():
    # Sujit, 2026-10-12: let the LLM decide matra density — a head mixing quarter, half and
    # whole matras is not flagged for "no steady pulse" (that floor steered every head into
    # one note per matra)
    cell = _cell(_n("S", 1.5), _n("g", 0.5), _n("m", 0.25), _n("g", 0.25),
                 _n("m", 2.0), _n("S", 1.0), _n("m", 2.5))
    viol = _craft(check_mukhada, cell, cycle_beats=8.0, raga="malkauns")
    assert not any("PULSE" in v for v in viol)


def test_an_EVEN_head_is_now_fine_rhythmically():
    """The correction itself: a gat sung one swara per matra is idiomatic, not a metronome."""
    cell = _cell(_n("S", 1.0), _n("g", 1.0), _n("m", 1.0), _n("g", 1.0),
                 _n("S", 1.0), _n("g", 1.0), _n("m", 2.0))
    assert not [v for v in verify_mukhada(cell, cycle_beats=8.0, raga="malkauns")
                if "PULSE" in v]


def test_a_head_that_ends_where_it_began_hides_the_sam():
    """Ending on the opening swara merges the two across the loop — the 2026-09-14 head closed
    on a 2-beat Ma and reopened on a 1.5-beat Ma, so a 3.5-beat Ma straddled the sam and the
    downbeat vanished."""
    cell = _cell(_n("S", 1.0), _n("g", 1.0), _n("m", 1.0), _n("g", 1.0),
                 _n("m", 1.0), _n("S", 3.0))
    viol = verify_mukhada(cell, cycle_beats=8.0, raga="malkauns")
    assert any("SAM DISAPPEARS" in v for v in viol)


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
    # the verified ALAP-VISTAR shape (malkauns): THREE tension-holding phrases developing the
    # ONE motif (d n S) — each ends AWAY from home — separated by real rests with the mandra Sa
    # PLUCKED between them (the drone anchor / jod string); opens on Sa, the melodic line dips
    # into the mandra, STATES the pakad (g m g S), and only the FINAL phrase comes home to the
    # longest held Sa (17.25 beats total).
    return _intro_cell(
        _n("S", 1.0), _n("d", 1.0, oct=-1), _n("n", 1.5, oct=-1),   # phrase 1 — ends away
        _n("S", 1.0, rest=True),
        _n("S", 1.0, oct=-1),                                        # the low Sa pluck (drone)
        _n("S", 1.0, rest=True),
        _n("d", 0.5, oct=-1), _n("n", 0.5, oct=-1), _n("S", 0.5),    # phrase 2 — full motif,
        _n("g", 1.5),                                                #  widens, ends away on g
        _n("m", 1.0, rest=True),
        _n("S", 0.75, oct=-1),                                       # the low Sa pluck again
        _n("g", 1.0, rest=True),
        _n("g", 1.0), _n("m", 1.0), _n("g", 0.5), _n("S", 2.5))      # final: pakad -> held Sa


def test_a_grounded_alap_has_no_violations():
    assert verify_intro(_good_intro(), window_beats=18.0, raga="malkauns") == []


def test_intro_must_open_around_sa():
    cell = _good_intro()
    cell.notes[0] = _n("P", 2.0)               # opens 3 ladder steps from home (darbari, folded)
    viol = _craft(check_intro, cell, window_beats=16.0, raga="darbari")
    assert any("madhya Sa" in v and "opens" in v for v in viol)


def test_intro_must_dip_into_the_mandra():
    cell = _cell(_n("S", 2.0), _n("S", 1.5, rest=True), _n("g", 2.0), _n("m", 3.0),
                 _n("S", 2.0), _n("m", 1.5, rest=True), _n("d", 1.0), _n("S", 3.0))
    viol = _craft(check_intro, cell, window_beats=16.0, raga="malkauns")  # never leaves madhya
    assert any("mandra" in v for v in viol)


def test_intro_needs_several_sa_returns():
    # Sa only at the start and the end (2 returns) — the line never keeps coming home
    cell = _cell(_n("S", 2.0), _n("S", 1.5, rest=True), _n("n", 2.0, oct=-1),
                 _n("d", 3.0, oct=-1), _n("g", 2.0), _n("m", 1.5, rest=True),
                 _n("g", 1.0), _n("S", 5.0))
    viol = _craft(check_intro, cell, window_beats=17.0, raga="malkauns")
    assert any("separate time" in v for v in viol)


def test_intro_must_end_on_sa():
    cell = _cell(_n("S", 4.0), _n("S", 1.5, rest=True), _n("S", 2.0),
                 _n("m", 1.5, rest=True), _n("n", 3.0))          # ends on n, not Sa
    assert any("ends on n" in v for v in _craft(check_intro, cell, window_beats=12.0, raga="malkauns"))


def test_intro_final_sa_must_be_held():
    cell = _cell(_n("S", 4.0), _n("S", 1.5, rest=True), _n("S", 3.0),
                 _n("m", 1.5, rest=True), _n("S", 0.5))          # final Sa too short
    assert any("HOLD" in v for v in _craft(check_intro, cell, window_beats=12.0, raga="malkauns"))


def test_intro_needs_sa_to_keep_ringing():
    cell = _cell(_n("S", 0.5), _n("S", 1.5, rest=True), _n("g", 4.0), _n("m", 4.0),
                 _n("d", 1.5, rest=True), _n("n", 4.0), _n("S", 1.0))   # Sa only 1.5/13.5
    assert any("keep home ringing" in v
               for v in _craft(check_intro, cell, window_beats=18.0, raga="malkauns"))


def test_intro_needs_two_real_rests():
    cell = _cell(_n("S", 3.0), _n("S", 1.5, rest=True), _n("g", 2.0), _n("S", 3.0))
    assert any("rest" in v and "breathes" in v for v in _craft(check_intro, cell, window_beats=10.0, raga="malkauns"))


def test_intro_gaps_need_the_low_sa_pluck():
    # phrases separated by rests, but home is never plucked in the gaps — the drone is missing
    cell = _cell(_n("S", 1.0), _n("g", 1.0), _n("m", 1.5),
                 _n("S", 1.0, rest=True),
                 _n("g", 1.0), _n("m", 1.0), _n("d", 1.0),
                 _n("m", 1.0, rest=True),
                 _n("g", 1.0), _n("S", 2.5))
    viol = _craft(check_intro, cell, window_beats=14.0, raga="malkauns")
    assert any("pluck" in v for v in viol)


def test_intro_phrases_must_hold_tension():
    # phrase 1 resolves onto madhya Sa before its rest — the homecoming arrives too soon
    cell = _good_intro()
    cell.notes[2] = _n("S", 1.5)                     # phrase 1 now ends home instead of away
    viol = _craft(check_intro, cell, window_beats=18.0, raga="malkauns")
    assert any("TENSION" in v for v in viol)


def test_intro_pluck_groups_are_not_phrases():
    # two melodic phrases + three pluck-only groups: the pluck is punctuation, so the
    # phrase count is still short
    cell = _cell(_n("S", 1.0, oct=-1), _n("S", 1.0, rest=True),
                 _n("g", 1.0), _n("m", 1.5),
                 _n("S", 1.0, rest=True), _n("S", 0.75, oct=-1), _n("S", 1.0, rest=True),
                 _n("g", 1.0), _n("S", 2.5),
                 _n("S", 1.0, rest=True), _n("S", 0.75, oct=-1))
    viol = _craft(check_intro, cell, window_beats=18.0, raga="malkauns")   # a roomy window asks for 3
    assert any("INDEPENDENT phrases" in v for v in viol)


# --- verify_intro: the alap keeps time (2026-10-11 render: 0.4/0.12 beats, diri 32nds, all quick)

def test_a_short_window_asks_for_two_phrases_not_three():
    from crew.gat_verifier import intro_min_phrases
    assert intro_min_phrases(10.4) == 2 and intro_min_phrases(18.2) == 3


def test_intro_durations_must_sit_on_the_grid():
    cell = _good_intro()
    cell.notes[0] = _n("S", 0.4)
    assert any("off the beat grid" in v for v in _craft(check_intro, cell, window_beats=18.0,
                                                                raga="malkauns"))


def test_intro_rejects_doubled_strokes():
    cell = _good_intro()
    cell.notes[1] = cell.notes[1].model_copy(update={"bol": "dir"})
    assert any("compound bol" in v for v in _craft(check_intro, cell, window_beats=18.0,
                                                         raga="malkauns"))


def test_intro_quick_steps_stay_a_minority():
    cell = _good_intro()
    quick = [n.model_copy(update={"dur": 0.25}) if not n.rest and n.dur < 2.5 else n
             for n in cell.notes]
    cell = cell.model_copy(update={"notes": quick})
    assert any("quick steps" in v for v in _craft(check_intro, cell, window_beats=18.0,
                                                        raga="malkauns"))


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
    viol = _craft(check_intro, cell, window_beats=16.0, raga="malkauns")
    assert any("INDEPENDENT phrases" in v for v in viol)


def test_intro_a_phrase_must_explore_not_be_bare_sa():
    # phrase 2 is only Sa — a drone, not a sentence
    cell = _cell(_n("S", 1.0), _n("n", 1.0, oct=-1), _n("S", 1.5),
                 _n("S", 1.5, rest=True),
                 _n("S", 2.0),                                       # phrase 2: bare Sa
                 _n("m", 1.5, rest=True),
                 _n("g", 1.0), _n("m", 1.0), _n("S", 2.5))
    viol = _craft(check_intro, cell, window_beats=16.0, raga="malkauns")
    assert any("bare Sa" in v for v in viol)


def test_intro_must_not_dwell_on_sa_continuously():
    # a phrase repeats Sa for 4.5 continuous beats — the 'Sa played continuously' failure
    cell = _cell(_n("S", 1.0), _n("n", 1.0, oct=-1), _n("S", 1.5),
                 _n("S", 1.5, rest=True),
                 _n("g", 1.0), _n("S", 1.5), _n("S", 1.5), _n("S", 1.5),   # 4.5 beats of Sa
                 _n("m", 1.5, rest=True),
                 _n("g", 1.0), _n("S", 2.5))
    viol = _craft(check_intro, cell, window_beats=18.0, raga="malkauns")
    assert any("continuous beats" in v for v in viol)


def test_intro_must_state_the_pakad():
    # uses only Sa and Ma — grounded and phrased, but never states malkauns's pakad (d n S / g m g)
    cell = _cell(_n("S", 1.0), _n("m", 1.5, oct=-1), _n("S", 1.5),
                 _n("S", 1.5, rest=True),
                 _n("m", 2.0, oct=-1), _n("S", 2.0),
                 _n("m", 1.5, rest=True),
                 _n("m", 1.0), _n("S", 2.5))
    viol = _craft(check_intro, cell, window_beats=16.0, raga="malkauns")
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
    viol = _craft(check_intro, cell, window_beats=18.0, raga="malkauns", mukhada=_GAT_HEAD)
    assert any("not drawn from the mukhada head" in v for v in viol)


def test_intro_every_phrase_must_touch_the_motif():
    # phrase 2 develops nothing of the motif (g m S, no d n) — episodic, not ONE thought
    cell = _intro_cell(
        _n("S", 1.0), _n("d", 1.0, oct=-1), _n("n", 1.0, oct=-1), _n("S", 1.5),
        _n("S", 1.5, rest=True),
        _n("g", 1.0), _n("m", 1.0), _n("S", 1.5),                 # phrase 2: a NEW phrase
        _n("m", 1.5, rest=True),
        _n("g", 1.0), _n("m", 1.0), _n("g", 0.5), _n("S", 2.5))
    viol = _craft(check_intro, cell, window_beats=16.0, raga="malkauns")
    assert any("never touches the motif" in v for v in viol)


def test_intro_must_state_the_full_motif():
    # the anchors (d n) recur but the full motif (d n S d) never completes — no reveal
    cell = LeadPhrase(phrase_plan=_INTRO_PLAN.model_copy(update={"seed": ["d", "n", "S", "d"]}),
                      notes=_good_intro().notes)
    viol = _craft(check_intro, cell, window_beats=18.0, raga="malkauns")
    assert any("never stated" in v for v in viol)


def test_intro_opening_phrase_must_stay_narrow():
    # phrase 1 leaps to taar Sa — the two-octaves-in-four-seconds failure heard live
    cell = _good_intro()
    cell.notes[2] = _n("S", 1.5, oct=1)
    viol = _craft(check_intro, cell, window_beats=18.0, raga="malkauns")
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
    viol = _craft(check_intro, cell, window_beats=19.0, raga="malkauns")
    assert any("arrives too early" in v for v in viol)


def test_intro_must_declare_a_real_motif():
    # a one-swara seed is not a motif — the intro must name the ONE idea it develops
    cell = LeadPhrase(phrase_plan=_PLAN, notes=_good_intro().notes)   # seed = ["S"]
    viol = _craft(check_intro, cell, window_beats=18.0, raga="malkauns")
    assert any("declares no usable motif" in v for v in viol)


# --- verify_intro: the AUDIBLE line (a meend is heard at its TARGET) ---------------

def test_a_meend_spammed_intro_fails_on_its_audible_line():
    # the 2026-07-16 live failure in miniature: WRITTEN as motif phrases, but every note
    # meends to Sa — the ear gets one repeated note. The audible-line checks + the meend
    # rate cap must all see through the written swaras.
    cell = _good_intro()
    cell.notes = [n if n.rest else n.model_copy(update={"meend_swara": "S"})
                  for n in cell.notes]
    viol = _craft(check_intro, cell, window_beats=18.0, raga="malkauns")
    assert any("meend" in v for v in viol)                    # the rate cap names the cause
    assert any("motif" in v or "Sa" in v for v in viol)       # and the audible line collapses


def test_audible_line_reads_the_meend_target_octave():
    # a written-madhya note meending to taar Sa IS a taar reach — the audible peak
    cell = _good_intro()
    cell.notes[2] = _n("n", 1.0, oct=-1, meend_swara="S", meend_oct=1)   # audibly taar Sa, early
    viol = _craft(check_intro, cell, window_beats=18.0, raga="malkauns")
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
    viol = _craft(check_manjha, cell, mukhada=_HEAD, window_beats=16.0, raga="malkauns")
    assert any("flat" in v for v in viol)


def test_manjha_must_dip_into_the_mandra():
    # a manjha that stays at/above home never becomes the LOW bridge (Parikh)
    cell = _cell(_n("m", 3.0), _n("g", 2.5), _n("m", 3.0), _n("g", 2.5),
                 _n("m", 2.0), _n("n", 3.0))                 # all in the madhya octave
    viol = _craft(check_manjha, cell, mukhada=_HEAD, window_beats=16.0, raga="malkauns")
    assert any("mandra" in v for v in viol)


def test_manjha_must_not_climb_into_the_taar():
    # the taar (upper octave) is the ANTARA's job, not the manjha's
    cell = _cell(_n("d", 3.0, oct=-1), _n("n", 2.0), _n("m", 3.0, oct=1),   # m sits in the taar
                 _n("g", 2.5), _n("m", 3.0), _n("n", 2.5))
    viol = _craft(check_manjha, cell, mukhada=_HEAD, window_beats=16.0, raga="malkauns")
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
    viol = _craft(check_antara, cell, mukhada=_HEAD, window_beats=14.0, raga="malkauns")
    assert any("quote" in v for v in viol)


def test_antara_must_not_open_in_the_taar():
    cell = _good_antara()
    cell.notes[0] = _n("S", 2.0, oct=1)                      # opens already at the top
    viol = _craft(check_antara, cell, mukhada=_HEAD, window_beats=21.0, raga="malkauns")
    assert any("opens already" in v for v in viol)


def test_antara_must_reach_the_taar_octave():
    cell = _cell(_n("S", 2.0), _n("m", 1.5), _n("g", 1.0), _n("S", 2.0),
                 _n("d", 1.0), _n("m", 2.0), _n("S", 3.0))   # never leaves madhya
    viol = _craft(check_antara, cell, mukhada=_HEAD, window_beats=13.0, raga="malkauns")
    assert any("taar" in v for v in viol)


def test_antara_peak_must_arrive_late_and_not_be_the_exit():
    # peak in the FIRST notes -> too early
    early = _cell(_n("S", 1.0), _n("m", 0.5), _n("g", 0.5), _n("S", 0.5), _n("m", 1.0, oct=1),
                  _n("g", 2.0), _n("m", 2.0), _n("d", 2.0), _n("m", 2.0), _n("S", 3.0))
    assert any("too early" in v for v in _craft(check_antara, early, mukhada=_HEAD, window_beats=15.0,
                                                       raga="malkauns"))
    # ends ON the peak -> no descent
    ending_high = _cell(_n("S", 2.0), _n("m", 1.5), _n("g", 1.0), _n("S", 2.0),
                        _n("d", 2.0), _n("n", 2.0), _n("m", 2.0, oct=1))
    viol = _craft(check_antara, ending_high, mukhada=_HEAD, window_beats=13.0, raga="malkauns")
    assert any("highest note" in v and "DESCEND" in v for v in viol)


def test_antara_must_rest_on_madhya_sa():
    cell = _good_antara()
    cell.notes[-1] = _n("g", 3.0)                            # ends adrift, not home
    viol = _craft(check_antara, cell, mukhada=_HEAD, window_beats=21.0, raga="malkauns")
    assert any("madhya Sa" in v for v in viol)


# --- verify_taan: motif-grown, arced, lands, FLOWS to its phrase plan ------------

_MOTIF = ["S", "g", "m", "d"]

# all chaugun: statement -> build -> ONE climax from the midpoint -> a short cadence
_TAAN_PHRASES = [("statement", 2, 4), ("build", 4, 4), ("climax", 3, 4), ("cadence", 3, 4)]
_STATEMENT = ["S", "g", "m", "d", "m", "g", "m", "d"]
_BUILD = ["g", "m", "d", "m", "d", "n", "d", "m", "g", "m", "d", "n", "d", "n", "S'", "n"]
_CLIMAX = ["d", "n", "S'", "g'", "S'", "n", "S'", "g'", "m'", "g'", "S'", "n"]
_CADENCE = ["d", "n", "d", "m", "g", "m", "d", "m", "g", "m", "g", "S"]


def _taan_plan(phrases=_TAAN_PHRASES) -> PhrasePlan:
    return _PLAN.model_copy(update={"taan_phrases": [
        TaanPhrase(role=r, beats=b, subdivision=sub) for r, b, sub in phrases]})


def _run(swaras: list[str], dur: float) -> list[LeadNote]:
    return [_n(sw.rstrip("'"), dur, oct=1 if sw.endswith("'") else 0) for sw in swaras]


def _taan(*notes: LeadNote, phrases=_TAAN_PHRASES) -> LeadPhrase:
    return LeadPhrase(phrase_plan=_taan_plan(phrases), notes=list(notes))


def _good_taan() -> LeadPhrase:
    # grows from the motif (S g m d opens it), runs chaugun from its first note, peaks on taar m
    # late in the climax phrase, and keeps chaugun through the cadence onto Sa
    return _taan(*_run(_STATEMENT, 0.25), *_run(_BUILD, 0.25), *_run(_CLIMAX, 0.25),
                 *_run(_CADENCE, 0.25))


def _hard(cell: LeadPhrase, **kw) -> list[str]:
    return list(check_taan(cell, motif=_MOTIF, window_beats=12.0,
                           raga=kw.pop("raga", "malkauns"), **kw).hard)


def test_a_flowing_concert_taan_has_no_violations():
    checks = check_taan(_good_taan(), motif=_MOTIF, window_beats=12.0, raga="malkauns")
    assert checks.hard == () and checks.craft == ()


def test_taan_must_grow_from_the_motif():
    # fast and arced, but never states the motif's shape
    cell = _cell(_n("d", 0.5), _n("n", 0.5), _n("d", 0.25), _n("n", 0.25), _n("d", 0.25),
                 _n("n", 0.25), _n("d", 2.0), _n("g", 0.25, oct=1), _n("n", 0.25),
                 _n("d", 0.5), _n("S", 1.0))
    viol = _craft(check_taan, cell, motif=_MOTIF, window_beats=6.0, raga="malkauns")
    assert any("motif" in v for v in viol)


def test_a_taan_without_a_phrase_plan_is_rejected():
    cell = _cell(*_good_taan().notes)
    assert any("taan_phrases" in v for v in _hard(cell))


def test_a_held_note_inside_a_run_breaks_its_pulse():
    # the 233435 failure: a fast run stalls on a held note mid-phrase, then restarts
    notes = list(_good_taan().notes)
    notes[12:16] = [_n("m", 1.0)]                     # four build sixteenths -> one held beat
    viol = _hard(_taan(*notes))
    assert any("phrase 2" in v and "off its pulse" in v for v in viol)


def test_a_phrase_may_land_on_a_longer_note_at_its_boundary():
    notes = list(_good_taan().notes)
    notes[20:24] = [_n("S", 1.0, oct=1)]              # the build's last beat rings on taar Sa
    assert not any("off its pulse" in v for v in _hard(_taan(*notes)))


def test_a_gamak_note_keeps_the_run_moving():
    notes = list(_good_taan().notes)
    notes[8:12] = [_n("g", 1.0, gamak_with="m")]      # re-struck by code, so it is not a stall
    assert not any("off its pulse" in v for v in _hard(_taan(*notes)))


def test_a_taan_never_rests():
    notes = list(_good_taan().notes)
    notes[8] = _n("g", 0.25, rest=True)
    assert any("rests mid-flight" in v for v in _hard(_taan(*notes)))


def test_a_plan_that_slows_before_its_climax_is_rejected():
    slowing = [("statement", 2, 6), ("build", 4, 4), ("climax", 3, 4), ("cadence", 3, 4)]
    viol = _hard(_taan(*_good_taan().notes, phrases=slowing))
    assert any("pulse slows" in v for v in viol)


def test_an_early_climax_and_a_long_descent_are_rejected():
    early = [("statement", 2, 4), ("climax", 3, 4), ("cadence", 7, 4)]
    viol = _hard(_taan(*_good_taan().notes, phrases=early))
    assert any("later half" in v for v in viol)
    assert any("follow the climax" in v for v in viol)


def test_a_taan_launches_straight_at_chaugun():
    # Sujit, 2026-10-13: no dugun warm-up — the run is fast from its first note
    dugun_first = [("statement", 2, 2), ("build", 4, 4), ("climax", 3, 4), ("cadence", 3, 4)]
    notes = _run(_STATEMENT[:4], 0.5) + list(_good_taan().notes)[8:]
    assert any("opens at dugun" in v for v in _hard(_taan(*notes, phrases=dugun_first)))


def test_a_cadence_that_slows_down_is_rejected():
    lazy = [("statement", 2, 4), ("build", 4, 4), ("climax", 3, 4), ("cadence", 3, 2)]
    assert any("cadence slows" in v for v in _hard(_taan(*_good_taan().notes, phrases=lazy)))


def test_a_plan_must_fill_the_window_and_end_on_a_cadence():
    short = [("statement", 2, 4), ("build", 4, 4), ("climax", 4, 4)]
    viol = _hard(_taan(*_good_taan().notes, phrases=short))
    assert any("sum to 10" in v for v in viol)
    assert any("last phrase is the cadence" in v for v in viol)


def test_a_note_ringing_across_a_phrase_boundary_is_rejected():
    notes = list(_good_taan().notes)
    notes[7:9] = [_n("d", 0.5)]                       # the statement's last note runs into the build
    assert any("across the boundary" in v for v in _hard(_taan(*notes)))


def test_a_leap_inside_a_phrase_is_rejected():
    notes = list(_good_taan().notes)
    notes[8] = _n("g", 0.25, oct=1)                   # then taar g -> m mid-phrase: a jump, not a run
    assert any("jumps" in v for v in _hard(_taan(*notes)))


def test_the_highest_note_belongs_to_the_climax_phrase():
    notes = list(_good_taan().notes)
    notes[22] = _n("m", 0.25, oct=1)                  # the build already touches taar m...
    notes[23] = _n("g", 0.25, oct=1)
    assert any("not in the climax" in v for v in _hard(_taan(*notes)))


def test_the_top_note_comes_late_in_the_climax():
    # the first live take (2026-10-13) peaked as the climax phrase began, at 52%, then cascaded
    notes = list(_good_taan().notes)
    notes[24] = _n("m", 0.25, oct=1)                  # the climax OPENS on its top note: 50%
    assert any("highest note sounds at 50%" in v for v in _hard(_taan(*notes)))


def test_every_taan_note_is_one_stroke():
    # a dir on a sixteenth splits it into two 32nd strokes: a stutter on top of the pulse
    notes = list(_good_taan().notes)
    notes[8] = _n(notes[8].swara, 0.25, bol="dir")
    assert any("compound stroke" in v for v in _hard(_taan(*notes)))
    notes[8] = _n(notes[8].swara, 0.25, bol="ra")
    assert not any("compound stroke" in v for v in _hard(_taan(*notes)))


def test_a_taan_must_fill_its_window_exactly():
    notes = list(_good_taan().notes)[:-4]             # a beat short of the sam
    assert any("exactly 12" in v for v in _hard(_taan(*notes)))


def test_taan_must_land_on_a_resting_swara():
    cell = _good_taan()
    cell.notes[-1] = _n("n", 2.0)                            # ends adrift
    # judged in Darbari (rests R P S), where n is not a nyas — in Malkauns every swara is
    viol = verify_taan(cell, motif=_MOTIF, window_beats=12.0, raga="darbari")
    assert any("resting swara" in v for v in viol)


# --- the taan's destination (2026-10-12: no forced tihai, climax late, straight into the sam) -----

def test_a_taan_runs_into_the_returning_heads_first_swara():
    cell = _good_taan()                                      # ends on S: one step into R
    assert verify_taan(cell, motif=_MOTIF, window_beats=12.0, raga="darbari",
                       reentry="R") == []
    adrift = _good_taan()
    adrift.notes[-1] = _n("d", 0.25)                         # d is far from R
    viol = verify_taan(adrift, motif=_MOTIF, window_beats=12.0, raga="darbari", reentry="R")
    assert any("returning mukhada" in v for v in viol)


def test_a_taan_that_stops_before_the_sam_is_rejected():
    cell = _good_taan()
    cell.notes[-1] = _n("S", 1.0)
    cell.notes.append(_n("S", 1.0, rest=True))               # a gap before the returning sam
    viol = verify_taan(cell, motif=_MOTIF, window_beats=12.0, raga="darbari", reentry="R")
    assert any("stops before the sam" in v for v in viol)


def test_a_taan_that_peaks_early_is_rejected():
    early = _cell(_n("S", 0.5), _n("g", 0.5), _n("m", 0.5), _n("d", 0.5),
                  _n("g", 0.25, oct=1), _n("m", 0.25, oct=1), _n("g", 0.25, oct=1),   # the peak
                  _n("S", 0.25, oct=1), _n("n", 0.25), _n("d", 0.25), _n("m", 0.25), _n("g", 0.25),
                  _n("m", 2.0), _n("d", 0.5), _n("m", 0.5), _n("g", 0.5), _n("m", 0.5),
                  _n("g", 2.0), _n("S", 2.0))
    viol = verify_taan(early, motif=_MOTIF, window_beats=12.0, raga="malkauns")
    assert any("arrives too early" in v for v in viol)


def test_a_phrase_resting_on_a_non_nyas_before_silence_is_flagged():
    from crew.gat_verifier import nyas_violations
    # Bhairav: G is not a nyas — a phrase pausing on it before a beat of silence is flagged
    flagged = nyas_violations([_n("r", 1.0), _n("G", 2.0), _n("S", 1.0, rest=True),
                               _n("d", 2.0)], "bhairav")
    assert flagged and "'G' is not a nyas" in flagged[0]
    # the same line resting on d is fine, and a SHORT breath does not end a phrase
    assert nyas_violations([_n("P", 1.0), _n("d", 2.0), _n("S", 1.0, rest=True)], "bhairav") == []
    assert nyas_violations([_n("G", 1.0), _n("S", 0.5, rest=True), _n("m", 1.0)], "bhairav") == []


def test_a_descent_only_rest_must_be_reached_from_above():
    from crew.gat_verifier import nyas_violations
    rising = [_n("S", 1.0), _n("r", 2.0), _n("S", 1.0, rest=True)]
    falling = [_n("G", 1.0), _n("r", 2.0), _n("S", 1.0, rest=True)]
    assert any("AVAROHA" in v for v in nyas_violations(rising, "bhairav"))
    assert nyas_violations(falling, "bhairav") == []


def test_an_avoided_swara_is_never_a_rest():
    from crew.gat_verifier import nyas_violations
    assert any("weak swara" in v for v in nyas_violations(
        [_n("r", 1.0), _n("S", 2.0), _n("S", 1.0, rest=True)], "marwa"))


def test_taan_shares_the_earned_arc_rules():
    # never reaches the taar -> the shared arc check fires for the taan too
    cell = _cell(_n("S", 0.5), _n("g", 0.5), _n("m", 0.5), _n("d", 0.5), _n("m", 2.0),
                 _n("g", 0.25), _n("m", 0.25), _n("d", 0.25), _n("n", 0.25), _n("S", 1.0))
    viol = _craft(check_taan, cell, motif=_MOTIF, window_beats=6.0, raga="malkauns")
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
    viol = _craft(check_fill, cell, mukhada=_HEAD, window_beats=4.0, raga="malkauns")
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
    # the seam targets the head's RE-ENTRY swara (the note it sounds AT the cut — g at beat 4
    # of _HEAD), not its first note: ending on n (3 darbari steps from g) fails the seam
    swaras = (["R", "g", "m", "P", "d", "P", "m", "g"] * 2)[:15] + ["n"]
    cell = _cell(*[_n(s, 0.25) for s in swaras])
    viol = verify_fill(cell, mukhada=_HEAD, window_beats=4.0, raga="darbari")
    assert any("taan fill" in v and "fluid" in v for v in viol)


# --- the sam note is NOT a short list ------------------------------------------

def test_the_head_may_open_on_a_swara_that_is_not_sa_or_the_vadi():
    """This used to require Sa, the vadi or the samvadi on the sam, and Sujit's own repertoire
    refutes it: Vilayat Khan's Yaman gat lands its sam on PA — neither Sa nor Yaman's vadi (G)
    nor its samvadi (N) — a Bageshree bandish he is learning lands on RE, a swara our own data
    marks descent-only, and another Bageshree gat lands on Ma. Any list we write rejects real
    gats, so what the rule protected now lives in the brief and in the bol frame (which still
    requires the sam struck "da")."""
    cell = _cell(_n("d", 2.0), _n("g", 1.0), _n("m", 0.5), _n("g", 2.5), _n("m", 2.0))
    assert not any("opens on" in v for v in verify_mukhada(cell, cycle_beats=8.0, raga="malkauns"))


# --- verify_bol_frame: the stroke pattern is the gat's identity ------------------

def _framed_head(**overrides) -> LeadPhrase:
    # a 16-beat head following the Masitkhani frame: struck "da" on the sam, double attacks
    # in matras 12 (beats 11-12) and 14 (beats 13-14), every note carrying a bol
    notes = [_n("S", 4.0, bol="da"), _n("m", 4.0, bol="da"), _n("g", 2.0, bol="ra"),
             _n("d", 1.0, bol="da"),
             _n("n", 0.5, bol="da"), _n("d", 0.5, bol="ra"),      # matra 12: the dir double
             _n("m", 1.0, bol="da"),
             _n("g", 0.5, bol="da"), _n("m", 0.5, bol="ra"),      # matra 14: the dir double
             _n("S", 2.0, bol="da")]
    return _cell(*notes)


def test_a_frame_following_head_passes_masitkhani():
    assert verify_bol_frame(_framed_head(), cycle_beats=16.0, frame="masitkhani") == []


def test_frame_requires_da_on_the_sam():
    cell = _framed_head()
    cell.notes[0] = _n("S", 4.0, bol="ra")                       # a soft stroke on the sam
    viol = _craft(check_bol_frame, cell, cycle_beats=16.0, frame="masitkhani")
    assert any("first note" in v for v in viol)


def test_masitkhani_pins_the_dir_doublings_to_the_grid():
    # merge matra 12's pair into one plain note -> the approach loses its dir at matra 12
    cell = _cell(_n("S", 4.0, bol="da"), _n("m", 4.0, bol="da"), _n("g", 2.0, bol="ra"),
                 _n("d", 1.0, bol="da"), _n("n", 1.0, bol="da"), _n("m", 1.0, bol="da"),
                 _n("g", 0.5, bol="da"), _n("m", 0.5, bol="ra"), _n("S", 2.0, bol="da"))
    viol = _craft(check_bol_frame, cell, cycle_beats=16.0, frame="masitkhani")
    assert any("matra(s) 12" in v for v in viol)


def test_a_diri_bol_counts_as_the_double_stroke():
    # matra 12's double comes from ONE note with bol "diri" (apply_strokes splits it)
    cell = _cell(_n("S", 4.0, bol="da"), _n("m", 4.0, bol="da"), _n("g", 2.0, bol="ra"),
                 _n("d", 1.0, bol="da"), _n("n", 1.0, bol="diri"), _n("m", 1.0, bol="da"),
                 _n("g", 0.5, bol="da"), _n("m", 0.5, bol="ra"), _n("S", 2.0, bol="da"))
    assert not any("matra" in v for v in verify_bol_frame(cell, cycle_beats=16.0,
                                                          frame="masitkhani"))


def test_dir_and_dir_dir_drive_the_razakhani_head_but_dar_is_not_a_double():
    # dir = two half-matra plucks in ONE matra; dar = da(1) + r(1/2) — its plucks fall in two
    # matras, so it is a figure, not a double attack
    dirs = _cell(_n("S", 1.0, bol="dir"), _n("g", 1.0, bol="dir"), _n("m", 1.5, bol="dar"),
                 _n("d", 1.5, bol="dar"), _n("n", 11.0, bol="da"))
    assert not any("doubling" in v for v in _craft(check_bol_frame, dirs, cycle_beats=16.0,
                                                    frame="razakhani"))
    dars = _cell(_n("S", 1.5, bol="dar"), _n("g", 1.5, bol="dar"), _n("m", 13.0, bol="da"))
    assert any("doubling" in v for v in _craft(check_bol_frame, dars, cycle_beats=16.0,
                                                frame="razakhani"))


def test_a_figure_inside_one_matra_is_its_strokes_and_never_a_wrong_length():
    # a dadir inside ONE matra (1/2 + 1/4 + 1/4) is three plucks in that matra: a double attack
    cell = _cell(_n("S", 1.0, bol="dadir"), _n("g", 0.5, bol="dir"), _n("m", 0.5, bol="dara"),
                 _n("d", 14.0, bol="da"))
    checks = check_bol_frame(cell, cycle_beats=16.0, frame="razakhani")
    assert checks.hard == () and not any("length" in v for v in checks.craft)
    assert not any("doubling" in v for v in checks.craft)        # matras 1 and 2 both double


def test_razakhani_requires_double_density_not_position():
    # the same doubles sit NOWHERE near matras 12/14 — razakhani (flexible) accepts them
    cell = _cell(_n("S", 0.5, bol="da"), _n("g", 0.5, bol="ra"),      # matra 1: a double
                 _n("m", 0.5, bol="da"), _n("d", 0.5, bol="ra"),      # matra 2: a double
                 _n("n", 4.0, bol="da"), _n("d", 4.0, bol="da"), _n("m", 3.0, bol="ra"),
                 _n("S", 3.0, bol="da"))
    assert _craft(check_bol_frame, cell, cycle_beats=16.0, frame="razakhani") == []
    # ...but a head with a single double is under the density floor
    thin = _cell(_n("S", 0.5, bol="da"), _n("g", 0.5, bol="ra"),
                 _n("m", 5.0, bol="da"), _n("d", 4.0, bol="da"), _n("n", 3.0, bol="ra"),
                 _n("S", 3.0, bol="da"))
    assert any("doubling" in v for v in _craft(check_bol_frame, thin, cycle_beats=16.0,
                                                         frame="razakhani"))


def test_frame_requires_bols_on_most_notes():
    cell = _framed_head()
    cell.notes = [n.model_copy(update={"bol": None}) for n in cell.notes[:-1]] + [cell.notes[-1]]
    viol = _craft(check_bol_frame, cell, cycle_beats=16.0, frame="masitkhani")
    assert any("mizrab bol" in v for v in viol)


# --- reentry_swara: what the head sounds at the fill's re-entry beat -------------

def test_reentry_swara_reads_the_note_at_the_cut():
    assert reentry_swara(_HEAD, 4.0) == "g"        # _HEAD: S@0(3) m@3(2) g@5(1) S@6(2)
    assert reentry_swara(_HEAD, 0.0) == "S"
    assert reentry_swara(_HEAD, 99.0) == "S"       # nothing that late -> falls back to the first


# --- verify_antara with an amad: the homecoming is the amad's job ----------------

def test_antara_with_amad_need_not_come_home():
    cell = _good_antara()
    cell.notes[-1] = _n("g", 3.0)                            # ends away from home
    viol = _craft(check_antara, cell, mukhada=_HEAD, window_beats=21.0, raga="malkauns",
                         with_amad=True)
    assert not any("madhya Sa" in v for v in viol)           # the amad owns the descent home
    # the arc itself is still enforced: never reaching the taar still fails
    flat = _cell(_n("S", 7.0), _n("m", 7.0), _n("g", 4.0), _n("S", 3.0))
    assert any("taar" in v for v in _craft(check_antara, flat, mukhada=_HEAD, window_beats=21.0,
                                                  raga="malkauns", with_amad=True))


# --- verify_amad: the composed descent back into the head ------------------------

def _good_amad() -> LeadPhrase:
    # opens on the antara's landing (d), descends with no re-peak, mixes durations, fills its
    # 16-beat window, and ends on S — the head's first swara, at home
    return _cell(_n("d", 2.0), _n("m", 2.0), _n("g", 1.5), _n("m", 1.0), _n("g", 1.5),
                 _n("S", 2.0), _n("d", 1.5, oct=-1), _n("n", 1.5, oct=-1), _n("S", 3.0))


def test_a_good_amad_passes():
    assert verify_amad(_good_amad(), mukhada=_HEAD, window_beats=16.0, raga="malkauns",
                       antara_last="d") == []


def test_amad_must_descend():
    cell = _cell(_n("S", 4.0), _n("g", 4.0), _n("m", 4.0), _n("d", 2.0), _n("n", 2.0))
    viol = _craft(check_amad, cell, mukhada=_HEAD, window_beats=16.0, raga="malkauns")
    assert any("DESCEND" in v for v in viol)


def test_amad_must_not_repeak():
    # rises a fourth above its opening mid-line — the peak belongs to the antara
    cell = _cell(_n("d", 3.0), _n("S", 3.0, oct=1), _n("n", 2.5), _n("m", 2.5),
                 _n("g", 2.0), _n("S", 3.0))
    viol = _craft(check_amad, cell, mukhada=_HEAD, window_beats=16.0, raga="malkauns")
    assert any("climbs above" in v for v in viol)


def test_amad_opens_where_the_antara_landed():
    viol = verify_amad(_good_amad(), mukhada=_HEAD, window_beats=16.0, raga="malkauns",
                       antara_last="S")                      # d is 2 malkauns steps from S — ok
    assert viol == []
    # darbari has a 7-note ladder where a leap is measurable: opening on P against a landing
    # of S is a 3-step jump-cut
    leap = _cell(_n("P", 4.0), _n("m", 3.0), _n("g", 3.5), _n("R", 2.5), _n("S", 3.0))
    viol = verify_amad(leap, mukhada=_HEAD, window_beats=16.0, raga="darbari",
                       antara_last="S")
    assert any("leap from the antara" in v for v in viol)


def test_amad_must_fill_its_window():
    cell = _cell(_n("d", 2.0), _n("m", 1.5), _n("g", 1.0), _n("S", 2.0))   # 6.5 of 16 beats
    viol = verify_amad(cell, mukhada=_HEAD, window_beats=16.0, raga="malkauns")
    assert any("fills only" in v for v in viol)


# --- the raga is a grammar of MOVEMENT, not a permitted pitch set ---------------

def test_a_taan_that_walks_the_ladder_is_rejected():
    """Measured on the 2026-09-14 render: 63% of moves were single steps and the longest
    unbroken stepwise run was NINE notes. The taan brief already calls a straight run "ONE
    dash, never the whole taan" — nothing measured it, so nothing happened."""
    from crew.gat_verifier import _motion_violations
    ladder = [LeadNote(swara=s, dur=0.25) for s in "SRgmPDn"] * 2
    text = " ".join(_motion_violations(ladder, "bageshree", "taan"))
    assert "unbroken stepwise" in text and "SCALE" in text


def test_an_ascending_pa_is_caught_in_a_bageshree_taan():
    """Bageshree drops Pa from the aroha, so `m P D n S'` ascending is generically modal while
    `m D n S'` up and `S' n D P m` down is the raga. The LLM guardrail states this at
    generation time, but a guardrail is a bounded retry — what it cannot fix, it ships. The
    2026-09-14 render proves it: the verified head is clean while the developments and fills
    inside the same sections carried 3, 6 and 9 violations."""
    from crew.gat_verifier import _motion_violations
    climbing = [LeadNote(swara=s, dur=0.25) for s in "SgmPDnS"]
    assert any("P" in v for v in _motion_violations(climbing, "bageshree", "taan"))


def test_pa_on_the_way_DOWN_is_idiomatic():
    from crew.gat_verifier import _motion_violations
    falling = [LeadNote(swara=s, dur=0.25) for s in "SgmDnS"] + \
              [LeadNote(swara=s, dur=0.25) for s in "nDPmgRS"]
    # only the DIRECTION messages matter here (the 7-note descent also trips the scalar cap,
    # whose repair text quotes Bageshree's chalan — Pa included)
    assert not [v for v in _motion_violations(falling, "bageshree", "taan")
                if "P" in v and "(in the taan)" in v]


def test_a_line_that_descends_and_climbs_is_left_alone():
    """The vakra SHARE is measured for Rasik but is not a rule: this phrase reads as
    idiomatic and scores only 25% turns, while the render that prompted all this scored 38% —
    so a floor tight enough to catch the real failure would reject real music."""
    from crew.gat_verifier import _motion_violations
    line = [LeadNote(swara=s, dur=0.25) for s in "mDnDmgRSgmDnDm"]
    assert _motion_violations(line, "bageshree", "taan") == []


def test_a_part_that_states_no_raga_movement_is_flagged():
    """A part built only from legal swaras can belong to any raga sharing the scale — the
    2026-09-14 outro closed on D R S and a held Sa, which resolves the pitch and says nothing
    about Bageshree."""
    from crew.gat_verifier import _ang_violation
    generic = [LeadNote(swara=s, dur=1.0) for s in "DRS"]
    assert _ang_violation(generic, "bageshree", "outro") is not None
    idiomatic = [LeadNote(swara=s, dur=1.0) for s in "mDnDmgRS"]
    assert _ang_violation(idiomatic, "bageshree", "outro") is None


def test_quoting_the_HEAD_counts_as_stating_the_raga():
    """Restating the gat's own phrase is as much the raga as quoting the pakad is."""
    from crew.gat_verifier import _ang_violation
    part = [LeadNote(swara=s, dur=1.0) for s in "DRS"]
    assert _ang_violation(part, "bageshree", "outro", also_accept=list("DRS")) is None


def test_the_outro_must_resolve_the_raga_and_come_home():
    stops = LeadPhrase(phrase_plan=_PLAN,
                       notes=[LeadNote(swara=s, dur=1.0) for s in "DR"]
                       + [LeadNote(swara="g", dur=3.0)])
    text = " ".join(_craft(check_outro, stops, mukhada=None, raga="bageshree"))
    assert "states none of this raga's own movements" in text
    assert "not Sa" in text


def test_an_outro_that_quotes_the_raga_and_holds_sa_passes():
    from crew.gat_verifier import verify_outro
    good = LeadPhrase(phrase_plan=_PLAN,
                      notes=[LeadNote(swara=s, dur=0.5) for s in "mDnDmgR"]
                      + [LeadNote(swara="S", dur=4.0)])
    assert verify_outro(good, mukhada=None, raga="bageshree") == []


def test_a_manjha_that_never_sounds_the_vadi_is_flagged():
    """The 2026-09-14 manjha contained no Ma at all, in a raga whose vadi is Ma — a whole
    section spent away from the note the raga gravitates to."""
    head = LeadPhrase(phrase_plan=_PLAN,
                      notes=[LeadNote(swara=s, dur=1.0) for s in "mDnDmgRS"])
    no_ma = LeadPhrase(phrase_plan=_PLAN,
                       notes=[LeadNote(swara=s, dur=1.0) for s in "gRRnnSSg"])
    text = " ".join(_craft(check_manjha, no_ma, mukhada=head, window_beats=8.0, raga="bageshree"))
    assert "VADI" in text



# --- HARD vs CRAFT (2026-10-11): only a broken / illegal cell re-rolls -----------------------

def test_a_legal_rest_that_is_not_sa_is_craft_and_a_non_rest_is_hard():
    # Bageshree rests on S g m D. An outro closing on D resolves legally (only "not Sa" — taste);
    # one closing on n does not rest at all (raga grammar — the cell is broken)
    on_dha = _cell(_n("m", 1.0), _n("g", 1.0), _n("D", 4.0))
    on_ni = _cell(_n("m", 1.0), _n("D", 1.0), _n("n", 4.0))
    dha = check_outro(on_dha, mukhada=None, raga="bageshree")
    ni = check_outro(on_ni, mukhada=None, raga="bageshree")
    assert not any("ends on D" in v for v in dha.hard)
    assert any("ends on D" in v for v in dha.craft)
    assert any("ends on n" in v for v in ni.hard)


def test_taan_direction_and_the_scalar_run_cap_are_both_hard():
    # Bageshree's P is descent-only: climbing m P D breaks the grammar (HARD). A long legal
    # stepwise DESCENT is the scale showing through — also HARD since 2026-10-12: as craft it
    # turned a cheap local re-roll into whole-lead Producer revises that came back scalar
    climbing = _cell(_n("m", 0.25), _n("P", 0.25), _n("D", 0.25), _n("n", 0.25), _n("S", 1.0, oct=1))
    descending = _cell(*[_n(sw, 0.25, oct=o) for sw, o in      # past an octave: not one sapat
                         (("R", 1), ("S", 1), ("n", 0), ("D", 0), ("P", 0), ("m", 0), ("g", 0),
                          ("R", 0), ("S", 0))])
    up = check_taan(climbing, motif=[], window_beats=2.0, raga="bageshree")
    down = check_taan(descending, motif=[], window_beats=2.0, raga="bageshree")
    assert any("(in the taan)" in v for v in up.hard)
    assert not any("(in the taan)" in v for v in down.hard)
    assert any("SCALE" in v for v in down.hard)
    assert not any("SCALE" in v for v in down.craft)


def test_the_scalar_run_violation_tells_the_reroll_how_to_repair():
    # the feedback names the raga's own chalan fragments to rebuild from, not just "too scalar"
    ladder = _cell(*[_n(s, 0.25) for s in "SRgmPDn"], _n("S", 0.25, oct=1), _n("R", 1.0, oct=1))
    text = " ".join(verify_taan(ladder, motif=[], window_beats=3.0, raga="bageshree"))
    assert "SCALE" in text and "vakra/chalan fragments" in text
    assert "S g m D" in text or "m D n" in text           # Bageshree's chalan, quoted verbatim


def test_a_scalar_taan_fill_is_rerolled_too():
    # the fill shares the taan's motion check, so a ladder spliced into the head re-rolls
    up = (("S", 0), ("g", 0), ("m", 0), ("d", 0), ("n", 0), ("S", 1), ("g", 1), ("m", 1))
    ladder = _cell(*[_n(sw, 0.25, oct=o) for sw, o in up + tuple(reversed(up))])
    assert any("SCALE" in v for v in verify_fill(ladder, mukhada=_HEAD, window_beats=4.0,
                                                  raga="malkauns"))


def test_one_sapat_dash_is_still_idiomatic():
    # six notes straight is one dash — under the cap, so no scalar complaint
    dash = _cell(*[_n(s, 0.25) for s in "SgmDnS"[:6]], _n("m", 0.25), _n("S", 1.0))
    assert not any("SCALE" in v for v in verify_taan(dash, motif=[], window_beats=3.0,
                                                       raga="malkauns"))


def test_one_octave_dash_passes_but_a_second_run_is_the_scale_marching():
    # 2026-10-12 live A/B: two of five taan takes failed on ONE 7-8 note dash — the sapat the
    # repair message itself calls idiomatic. One dash up to an octave passes; two do not.
    up = [("S", 0), ("g", 0), ("m", 0), ("d", 0), ("n", 0), ("S", 1)]          # malkauns: 6 = octave
    sapat = _cell(*[_n(sw, 0.25, oct=o) for sw, o in up], _n("m", 0.5, oct=1), _n("S", 1.0, oct=1))
    assert not any("SCALE" in v for v in verify_taan(sapat, motif=[], window_beats=3.0,
                                                       raga="malkauns"))
    seven = [("S", 0), ("g", 0), ("m", 0), ("d", 0), ("n", 0), ("S", 1), ("g", 1)]
    twice = _cell(*[_n(sw, 0.25, oct=o) for sw, o in seven], _n("m", 0.5, oct=1),
                  *[_n(sw, 0.25, oct=o) for sw, o in reversed(seven)], _n("S", 1.0))
    text = " ".join(verify_taan(twice, motif=[], window_beats=5.0, raga="malkauns"))
    assert "SCALE" in text and "2 such runs" in text


# --- ORNAMENT DENSITY: ornaments speak by contrast (CRAFT, every lead cell) ---------------

def _ornamented(n: int, *, meends: int = 0, flicks: int = 0) -> LeadPhrase:
    """A plain alternating line of `n` notes, the first `meends` gliding and the first
    `flicks` carrying a murki."""
    notes = []
    for i in range(n):
        sw = "m" if i % 2 else "g"
        notes.append(_n(sw, 1.0, meend_swara=("S" if i < meends else None),
                        ornament=("murki" if i < flicks else None)))
    return _cell(*notes)


def test_a_meend_on_most_notes_is_a_craft_note_never_hard():
    cell = _ornamented(10, meends=8)
    checks = check_manjha(cell, mukhada=_HEAD, window_beats=10.0, raga="malkauns")
    assert any("meend" in v and "CONTRAST" in v for v in checks.craft)
    assert not any("CONTRAST" in v for v in checks.hard)


def test_a_murki_on_every_note_is_flagged():
    from crew.gat_verifier import _ornament_density_notes
    text = " ".join(_ornament_density_notes(_ornamented(8, flicks=8).notes, "alap"))
    assert "murki" in text and "8 of 8" in text


def test_sparing_ornaments_pass():
    from crew.gat_verifier import _ornament_density_notes
    # 4 of 10 meends (40%, at the cap) and 2 of 10 murkis (20%) still stand out
    assert _ornament_density_notes(_ornamented(10, meends=4, flicks=2).notes, "alap") == []


def test_a_short_cell_is_too_small_to_call_a_habit():
    from crew.gat_verifier import _ornament_density_notes
    assert _ornament_density_notes(_ornamented(4, meends=4, flicks=4).notes, "alap") == []


def test_the_alap_reports_ornament_density_with_the_shared_wording():
    cell = _good_intro()
    cell.notes = [n if n.rest or n.bol == "chikari" else n.model_copy(update={"ornament": "murki"})
                  for n in cell.notes]
    checks = check_intro(cell, window_beats=18.0, raga="malkauns")
    assert any("murki" in v and "alap" in v for v in checks.craft)
    assert not any("murki" in v for v in checks.hard)


# --- check_stroke_line: the right hand planned first, then played --------------------

# Parikh's "most durable" Razakhani order, read as one avartan (the cycle in GAT_COMPOSITION.md §2.3)
_LINE = "da - da ra | da ra dir dir | da rda ra dir | da dir da ra"


def _lined_head(line: str | None = _LINE) -> LeadPhrase:
    """A 16-matra head whose notes play `_LINE`: a da held two matras, then one note per matra
    carrying that matra's word (a compound on one note repeats its swara)."""
    plan = _PLAN.model_copy(update={"stroke_line": PhrasePlan.model_validate(
        {**_PLAN.model_dump(), "stroke_line": line}).stroke_line})
    words = "da ra da ra dir dir da rda ra dir da dir da ra".split()
    notes = [_n("S", 2.0, bol="da")] + [_n("m" if i % 2 else "g", 1.0, bol=w) for i, w in enumerate(words)]
    return LeadPhrase(phrase_plan=plan, notes=notes)


def test_the_plan_reads_a_written_stroke_line():
    plan = PhrasePlan.model_validate({**_PLAN.model_dump(), "stroke_line": "Da – diri | ra"})
    assert plan.stroke_line == ["da", "-", "dir", "ra"]          # bars dropped, dash unified, diri = dir
    assert PhrasePlan.model_validate({**_PLAN.model_dump(), "stroke_line": 7}).stroke_line is None


def test_notes_that_play_their_stroke_line_are_clean():
    head = _lined_head()
    assert stroke_line_match(head, cycle_beats=16.0) == ([], 16)
    assert check_stroke_line(head, cycle_beats=16.0).craft == ()


def test_a_head_with_no_stroke_line_is_asked_to_plan_one():
    craft = _craft(check_stroke_line, _lined_head(None), cycle_beats=16.0)
    assert any("no stroke_line planned" in v for v in craft)


def test_a_stroke_line_must_hold_strokes_and_one_token_per_matra():
    assert any("no strokes" in v for v in _craft(check_stroke_line, _lined_head("da dha " * 8), cycle_beats=16.0))
    assert any("12 tokens" in v for v in _craft(check_stroke_line, _lined_head("da ra dir " * 4), cycle_beats=16.0))


def test_notes_that_leave_their_line_are_reported_never_rejected():
    head = _lined_head("dir " * 16)                               # planned doubles everywhere
    off, matras = stroke_line_match(head, cycle_beats=16.0)
    assert matras == 16 and 1 in off and 2 in off                 # the held da: one pluck, then none
    checks = check_stroke_line(head, cycle_beats=16.0)
    assert checks.hard == () and any("of 16 matras" in v for v in checks.craft)



# --- the head is ONE idea (Sujit, 2026-10-12) -------------------------------------------------

def test_a_head_broken_by_rests_or_chikari_is_rejected():
    # fusion_20261012_152048: `da ra dir chikari` x4 — a hole on every fourth matra
    chikari = _n("S", 1.0, oct=1, bol="chikari")
    head = _cell(_n("S", 1.0), _n("R", 1.0), _n("g", 1.0), chikari,
                 _n("m", 1.0), _n("P", 1.0), _n("P", 1.0), _n("S", 1.0, rest=True),
                 _n("d", 2.0), _n("n", 2.0), _n("g", 1.0), _n("m", 1.0), _n("R", 2.0))
    hard = check_head_shape(head, raga="darbari").hard
    assert len(hard) == 1 and "4 8" in hard[0] and "ONE idea" in hard[0]


def test_a_continuous_head_with_a_held_breather_passes():
    # a quick (m)g m R S figure, a held andolit g as the breather, then the approach
    head = _cell(_n("m", 0.5), _n("g", 0.5), _n("m", 0.5), _n("R", 0.5), _n("S", 1.0),
                 _n("R", 1.0), _n("g", 3.0, andolan=True), _n("R", 1.0), _n("S", 1.0),
                 _n("m", 1.0), _n("P", 1.0), _n("d", 1.0), _n("n", 1.0), _n("P", 1.0),
                 _n("g", 1.0), _n("m", 1.0))
    assert check_head_shape(head, raga="darbari").hard == ()
    assert check_head_shape(head, raga="darbari").craft == ()


def test_a_head_that_walks_the_scale_is_reported():
    # the same head's opening, repeated strokes merged: S R g m P d n — the scale, not Darbari
    head = _cell(*[_n(sw, 1.0) for sw in ["S", "S", "R", "g", "g", "m", "P", "P", "d", "n"]],
                 _n("P", 2.0), _n("g", 1.0), _n("m", 1.0), _n("R", 2.0))
    assert any("straight along the scale" in c for c in check_head_shape(head, raga="darbari").craft)


def test_gamak_in_a_head_is_counted_as_the_ear_hears_it():
    def g(sw: str, partner: str) -> LeadNote:
        return _n(sw, 0.5, gamak_with=partner)
    two = _cell(g("S", "R"), g("S", "R"), _n("R", 1.0), g("g", "m"), g("g", "m"), _n("m", 13.0))
    assert check_head_shape(two, raga="darbari").craft == ()          # a dir doubling is ONE gamak
    three = _cell(g("S", "R"), _n("R", 1.0), g("g", "m"), _n("m", 1.0), g("P", "m"), _n("R", 12.5))
    assert any("gamak on 3 notes" in c for c in check_head_shape(three, raga="darbari").craft)


# --- the breather: a held note, planned and heard ----------------------------------------------

def _darbari_head() -> LeadPhrase:
    # figure (4) -> breather on g (4) -> response (4) -> approach (4)
    return _cell(_n("m", 0.5), _n("g", 0.5), _n("m", 0.5), _n("R", 0.5), _n("S", 1.0),
                 _n("R", 1.0), _n("g", 3.0, andolan=True), _n("R", 1.0), _n("S", 1.0),
                 _n("m", 1.0), _n("P", 1.0), _n("d", 1.0), _n("n", 1.0), _n("P", 1.0),
                 _n("g", 1.0), _n("m", 1.0))


def _shaped(cell: LeadPhrase, *stages: tuple) -> LeadPhrase:
    shape = [HeadStage(stage=st, beats=b, target=tg) for st, b, tg in stages]
    return cell.model_copy(update={"phrase_plan": cell.phrase_plan.model_copy(
        update={"head_shape": shape})})


def test_a_head_that_never_holds_a_note_is_rejected():
    # fusion_20261012_152048's longest note was ONE beat; its "breath" was four rests
    head = _cell(*[_n(sw, 1.0) for sw in ["S", "R", "g", "R", "m", "P", "d", "n",
                                          "P", "m", "g", "m", "R", "S", "n", "R"]])
    assert any("BREATHER" in h for h in check_head_shape(head, raga="darbari").hard)


def test_a_restruck_long_note_is_no_breather():
    # a gamak re-strikes about every quarter second; a compound bol divides the note
    for long in (_n("g", 4.0, gamak_with="m"), _n("g", 4.0, bol="dara")):
        head = _cell(*[_n(sw, 1.0) for sw in ["S", "R", "m", "R", "S", "n", "d", "n",
                                              "P", "m", "R", "S"]], long)
        assert any("BREATHER" in h for h in check_head_shape(head, raga="darbari").hard)


def test_a_planned_shape_the_notes_keep_reports_nothing():
    head = _shaped(_darbari_head(), ("figure", 4.0, None), ("breather", 4.0, "g"),
                   ("response", 4.0, None), ("approach", 4.0, "S"))
    assert check_head_plan(head, cycle_beats=16.0).craft == ()


def test_the_plan_is_measured_against_the_notes():
    missing = check_head_plan(_darbari_head(), cycle_beats=16.0).craft
    assert any("no head_shape" in c for c in missing)
    wrong = _shaped(_darbari_head(), ("figure", 4.0, None), ("breather", 4.0, "d"),
                    ("approach", 6.0, "S"))
    craft = check_head_plan(wrong, cycle_beats=16.0).craft
    assert any("spans 14" in c for c in craft)
    assert any("to hold d, but it holds g" in c for c in craft)
    late = _shaped(_darbari_head(), ("figure", 8.0, None), ("breather", 4.0, None),
                   ("approach", 4.0, "S"))
    assert any("holds no note" in c for c in check_head_plan(late, cycle_beats=16.0).craft)

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
