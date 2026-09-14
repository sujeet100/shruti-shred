"""
Tests for the riff TEXTURE layer — all pure (no key, no cost).

The diagnosis this layer answers (measured on a live render): the rhythm guitar wrote a
busy low melody — 79% pitch changes, no chug ground, bright add9/tenth stacks, nothing
sustained. Everything here is provable without the LLM: the mode is decided by CODE from
the section's gat role, each mode's budgets catch the diagnosed failures (melody-not-riff,
no silence, unweighted sam, colour overload, pads that don't ring, stabs without space),
a clean idiomatic cycle passes, and `verified_riff` re-rolls with the exact violations as
feedback, keeping the best of a bounded number of takes.

Runs as a script (`uv run python tests/test_riff_texture.py`) or under pytest.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root

from crew.contracts import RiffNote, RiffPattern, Section, SectionKind  # noqa: E402
from crew.riff_texture import (  # noqa: E402
    MODE_BRIEFS,
    RiffMode,
    _chug_fill_pads,
    _chug_the_ground,
    open_the_rings,
    riff_mode_for,
    verified_riff,
    verify_riff,
)

_CYCLE = 8.0   # a compact 8-beat cycle keeps the fixtures readable


def _section(kind: SectionKind = SectionKind.RIFF, form_role: str | None = None) -> Section:
    return Section(kind=kind, bars=2, layers=["rhythm", "drums", "drone"],
                   foreground="rhythm", form_role=form_role)


def _n(swara: str = "S", dur: float = 0.5, *, oct: int = 0, chord: list[str] | None = None,
       technique: str | None = None, rest: bool = False) -> RiffNote:
    return RiffNote(swara=swara, oct=oct, dur=dur, chord=chord,
                    technique=technique, rest=rest)


def _drive_clean() -> RiffPattern:
    """An idiomatic 8-beat drive cycle: chorded sam, chug ground on Sa, one earned
    figure, a rest, a turnaround — the shape the prompt asks for."""
    return RiffPattern(notes=[
        _n("S", 1.0, chord=["S"]),                       # weighted sam
        _n("S", 0.5, technique="palm_mute"),             # the ground
        _n("S", 0.5, technique="palm_mute"),
        _n("S", 0.5, technique="palm_mute"),
        _n("g", 0.5, technique="hammer_on"),             # a short figure...
        _n("m", 0.5),
        _n("S", 0.5, technique="palm_mute"),             # ...back to the ground
        _n("S", 0.5, technique="palm_mute"),
        _n("S", 1.0, rest=True),                         # a true rest
        _n("S", 0.5, technique="palm_mute"),
        _n("S", 0.5, technique="palm_mute"),
        _n("g", 0.5, technique="slide"),                 # turnaround into the sam
        _n("S", 1.0, chord=["P"]),
    ])


def _pads_clean() -> RiffPattern:
    """Ringing power chords under the sitar: long chorded holds, one connecting stroke."""
    return RiffPattern(notes=[
        _n("S", 3.0, chord=["S"]),
        _n("S", 1.0, rest=True),
        _n("g", 2.0, chord=["g"]),
        _n("S", 2.0, chord=["P"]),
    ])


def _stabs_clean() -> RiffPattern:
    """Hit-then-silence: low chorded stabs with real rests between."""
    return RiffPattern(notes=[
        _n("S", 0.5, chord=["S"], technique="palm_mute"),
        _n("S", 1.0, rest=True),
        _n("S", 0.5, chord=["S"]),
        _n("S", 1.5, rest=True),
        _n("S", 0.5, chord=["S"]),
        _n("S", 0.5, rest=True),
        _n("S", 0.75, chord=["S"]),
        _n("S", 0.25, technique="palm_mute"),
        _n("g", 1.0, chord=["g"]),                        # the one move, into the sam
        _n("S", 1.5, rest=True),
    ])


def _melody() -> RiffPattern:
    """The diagnosed live failure in miniature: wall-to-wall pitch changes, no ground,
    no rest, a naked sam — a lead line an octave down, not a riff."""
    swaras = ["S", "g", "m", "P", "m", "g", "S", "n", "g", "m", "P", "d", "m", "g", "S", "g"]
    return RiffPattern(notes=[_n(s, 0.5) for s in swaras])


# --- the mode is decided by CODE from the section's gat role ---------------------

def test_mode_follows_the_form_role_over_the_kind():
    # an antara MELODY section pads (the sitar owns the movement)...
    assert riff_mode_for(_section(SectionKind.MELODY, "antara")) is RiffMode.PADS
    # ...while a plain MELODY section drives
    assert riff_mode_for(_section(SectionKind.MELODY)) is RiffMode.DRIVE


def test_mukhada_drives_taan_pads_breakdown_stabs():
    assert riff_mode_for(_section(SectionKind.RIFF, "mukhada")) is RiffMode.DRIVE
    assert riff_mode_for(_section(SectionKind.TAAN, "taan_long")) is RiffMode.PADS
    assert riff_mode_for(_section(SectionKind.BREAKDOWN, "breakdown")) is RiffMode.STABS
    assert riff_mode_for(_section(SectionKind.BREAKDOWN)) is RiffMode.STABS


def test_manjha_pads_the_low_bridge():
    # changed from DRIVE (2026-07-16): the calm low bridge wants a ringing chordal
    # platform under the lead's sparse line, not the mukhada's chug engine
    assert riff_mode_for(_section(SectionKind.MELODY, "manjha")) is RiffMode.PADS


def test_every_mode_has_a_prompt_brief():
    for mode in RiffMode:
        assert MODE_BRIEFS[mode].strip(), mode


def test_a_breakdown_with_nothing_ringing_is_rejected():
    """Measured on the 2026-09-14 live render: the breakdown was 14 notes, ALL palm-muted, not
    one open note of a beat or more — so there was no weight to drop away from. A chorded
    palm-mute passes the weight check on paper and is a click in the air."""
    muted = RiffPattern(notes=[_n("S", 0.5, chord=["S"], technique="palm_mute"),
                               _n("S", 1.5, rest=True),
                               _n("S", 0.5, chord=["S"], technique="palm_mute"),
                               _n("S", 1.5, rest=True),
                               _n("S", 0.5, chord=["S"], technique="palm_mute"),
                               _n("S", 3.0, rest=True)])
    text = " ".join(verify_riff(muted, mode=RiffMode.STABS, cycle_beats=_CYCLE))
    assert "RINGS" in text and "OPEN chord" in text


def test_a_breakdown_that_opens_its_downbeat_passes():
    assert not [v for v in verify_riff(_stabs_clean(), mode=RiffMode.STABS, cycle_beats=_CYCLE)
                if "RINGS" in v]


# --- DRIVE: the chug ground is enforced, melody is rejected ----------------------

def test_a_clean_drive_cycle_passes():
    assert verify_riff(_drive_clean(), mode=RiffMode.DRIVE, cycle_beats=_CYCLE) == []


def test_a_chug_written_as_a_sustain_is_rejected():
    """The muting hand damps, so a long palm-muted note is a sustain the articulation cannot
    deliver — measured 2026-09-14, 21% of palm-muted notes were written a beat or longer and
    played as a click followed by dead air."""
    pattern = _drive_clean()
    pattern.notes[1] = _n("S", 2.0, technique="palm_mute")
    text = " ".join(verify_riff(pattern, mode=RiffMode.DRIVE, cycle_beats=_CYCLE))
    assert "cannot sustain" in text and "OPEN" in text


def test_a_quarter_note_chug_is_still_fine():
    """The cap must not outlaw an ordinary doom chug — only the ones asking to ring."""
    pattern = _drive_clean()
    pattern.notes[1] = _n("S", 1.0, technique="palm_mute")
    assert not [v for v in verify_riff(pattern, mode=RiffMode.DRIVE, cycle_beats=_CYCLE)
                if "cannot sustain" in v]


def test_a_pitch_gesture_on_a_chord_is_rejected():
    """The pitch wheel is channel-wide, so bending a chord bends every tone of it; the
    renderer now drops such a gesture, and a dropped gesture the model thinks it wrote is
    worse than one it never wrote."""
    pattern = _drive_clean()
    pattern.notes[11] = _n("g", 0.5, chord=["g"], technique="slide")
    text = " ".join(verify_riff(pattern, mode=RiffMode.DRIVE, cycle_beats=_CYCLE))
    assert "CHORD" in text and "single notes" in text


def test_slides_are_rationed():
    pattern = _drive_clean()
    pattern.notes[5] = _n("m", 0.5, technique="slide")     # a second slide in the cycle
    text = " ".join(verify_riff(pattern, mode=RiffMode.DRIVE, cycle_beats=_CYCLE))
    assert "FRETTED" in text


def test_a_long_wander_off_the_ground_is_rejected():
    """A share alone is not enough: a riff can hit its ground quota and still play one long
    tune followed by a block of chugs."""
    pattern = _drive_clean()
    pattern.notes[4:6] = [_n("g", 0.25), _n("m", 0.25), _n("P", 0.25), _n("d", 0.25)]
    text = " ".join(verify_riff(pattern, mode=RiffMode.DRIVE, cycle_beats=_CYCLE))
    assert "leave the ground pitch" in text


def test_a_run_of_identical_chugs_is_rejected():
    """Six identical eighth-note chugs at one velocity is a drum machine, not a picking hand
    (heard on the 2026-07-20 renders)."""
    pattern = RiffPattern(notes=[_n("S", 1.0, chord=["S"])]
                          + [_n("S", 0.5, technique="palm_mute") for _ in range(6)]
                          + [_n("S", 1.0, rest=True), _n("g", 0.5), _n("S", 1.0, chord=["P"])])
    text = " ".join(verify_riff(pattern, mode=RiffMode.DRIVE, cycle_beats=_CYCLE))
    assert "ACCENTS" in text


def test_an_accented_chug_run_passes():
    pattern = RiffPattern(notes=[_n("S", 1.0, chord=["S"])]
                          + [RiffNote(swara="S", oct=0, dur=0.5, technique="palm_mute", vel=v)
                             for v in (112, 92, 100, 92, 112, 92)]
                          + [_n("S", 1.0, rest=True), _n("g", 0.5), _n("S", 1.0, chord=["P"])])
    assert not [v for v in verify_riff(pattern, mode=RiffMode.DRIVE, cycle_beats=_CYCLE)
                if "ACCENTS" in v]


def test_a_rest_breaks_a_chug_run():
    """Two three-chug figures either side of a rest are two figures, not a run of six — the
    detector reads the full cycle so a dropped rest cannot invent a violation."""
    pattern = RiffPattern(notes=[_n("S", 1.0, chord=["S"])]
                          + [_n("S", 0.5, technique="palm_mute") for _ in range(3)]
                          + [_n("S", 1.0, rest=True)]
                          + [_n("S", 0.5, technique="palm_mute") for _ in range(3)]
                          + [_n("g", 0.5), _n("S", 1.0, chord=["P"])])
    assert not [v for v in verify_riff(pattern, mode=RiffMode.DRIVE, cycle_beats=_CYCLE)
                if "ACCENTS" in v]


def test_the_live_failure_melody_is_rejected():
    viol = verify_riff(_melody(), mode=RiffMode.DRIVE, cycle_beats=_CYCLE)
    text = " ".join(viol)
    assert "melody" in text                       # the pitch-change cap names the crime
    assert "ground" in text                       # and the missing chug ground
    assert "rest" in text                         # and the missing silence


def test_drive_requires_a_weighted_sam():
    pattern = _drive_clean()
    pattern.notes[0] = _n("S", 0.5)               # naked short sam
    viol = verify_riff(pattern, mode=RiffMode.DRIVE, cycle_beats=_CYCLE)
    assert any("sam" in v for v in viol)


def test_drive_rations_the_bright_colour_stacks():
    pattern = _drive_clean()
    # pile bright colour (R over S seats as an add9) onto three ground chugs
    for i in (1, 2, 3):
        pattern.notes[i] = _n("S", 0.5, chord=["R"], technique="palm_mute")
    viol = verify_riff(pattern, mode=RiffMode.DRIVE, cycle_beats=_CYCLE)
    assert any("colour" in v and "light and happy" in v for v in viol)


def test_the_duration_sum_must_roughly_fill_the_cycle():
    tiny = RiffPattern(notes=[_n("S", 0.5, chord=["S"]), _n("S", 0.5, rest=True)])
    viol = verify_riff(tiny, mode=RiffMode.DRIVE, cycle_beats=_CYCLE)
    assert any("sum" in v for v in viol)


def test_fancy_techniques_are_rationed():
    pattern = _drive_clean()
    pattern.notes[1] = _n("S", 0.5, technique="pick_scrape")
    pattern.notes[2] = _n("S", 0.5, technique="pick_scrape")
    viol = verify_riff(pattern, mode=RiffMode.DRIVE, cycle_beats=_CYCLE)
    assert any("scrape" in v for v in viol)


def test_drive_owes_open_ringing_weight():
    # the Malkauns render's mukhada riff in miniature: EVERY note palm-muted (even the
    # chorded ones) — pure attack, zero resonance; the engine must also breathe
    pm = [("d", 0.5), ("d", 0.5), ("S", 0.5), ("S", 0.5), ("S", 1.0), ("S", 0.5), ("S", 0.5)]
    tail = [("m", 0.5), ("g", 0.5), ("S", 0.5), ("S", 1.0)]
    pattern = RiffPattern(notes=(
        [_n(s, d, chord=[s], technique="palm_mute") for s, d in pm]
        + [_n("S", 1.0, rest=True)]
        + [_n(s, d, chord=[s], technique="palm_mute") for s, d in tail]
        + [_n("S", 0.5, rest=True)]))
    viol = verify_riff(pattern, mode=RiffMode.DRIVE, cycle_beats=_CYCLE)
    assert any("RINGS open" in v for v in viol)


def test_a_palm_muted_hold_is_not_sam_weight():
    pattern = _drive_clean()
    pattern.notes[0] = _n("S", 1.0, technique="palm_mute")   # written long, gates to a tick
    viol = verify_riff(pattern, mode=RiffMode.DRIVE, cycle_beats=_CYCLE)
    assert any("sam" in v for v in viol)


# --- PADS: sustained ringing chords, not motion ----------------------------------

def test_a_clean_pads_cycle_passes():
    assert verify_riff(_pads_clean(), mode=RiffMode.PADS, cycle_beats=_CYCLE) == []


def test_pads_reject_a_busy_riff():
    viol = verify_riff(_drive_clean(), mode=RiffMode.PADS, cycle_beats=_CYCLE)
    assert any("SUSTAIN" in v or "rings" in v for v in viol)


def test_pads_require_a_long_chorded_ring():
    pattern = _pads_clean()
    pattern.notes[0] = _n("S", 3.0)               # the long hold loses its chord stack
    viol = verify_riff(pattern, mode=RiffMode.PADS, cycle_beats=_CYCLE)
    assert any("chord" in v for v in viol)


def test_pads_ring_must_be_open_not_palm_muted():
    # the Malkauns render's taan "pads" in miniature: long WRITTEN durations, every note
    # palm-muted — the renderer gates each to ~70ms, so nothing actually rings
    pattern = RiffPattern(notes=[
        _n("S", 3.0, chord=["S"], technique="palm_mute"),
        _n("S", 1.0, rest=True),
        _n("g", 2.0, chord=["g"], technique="palm_mute"),
        _n("S", 2.0, chord=["P"], technique="palm_mute"),
    ])
    viol = verify_riff(pattern, mode=RiffMode.PADS, cycle_beats=_CYCLE)
    assert any("NEVER ring" in v for v in viol)          # the ring share sees through the duration
    assert any("not palm-muted" in v for v in viol)      # and the long-ring check does too


# --- STABS: hit then silence, low, weighted ---------------------------------------

def test_a_clean_stabs_cycle_passes():
    assert verify_riff(_stabs_clean(), mode=RiffMode.STABS, cycle_beats=_CYCLE) == []


def test_stabs_require_real_silence():
    viol = verify_riff(_melody(), mode=RiffMode.STABS, cycle_beats=_CYCLE)
    assert any("silent" in v or "SILENCE" in v for v in viol)


def test_stabs_stay_low():
    pattern = _stabs_clean()
    pattern.notes[2] = _n("S", 0.5, oct=1, chord=["S"])
    viol = verify_riff(pattern, mode=RiffMode.STABS, cycle_beats=_CYCLE)
    assert any("low" in v for v in viol)


# --- verified_riff: the bounded feedback re-roll ----------------------------------

def _gen_sequence(*patterns: RiffPattern):
    """A fake generation fn that records the feedback each attempt received."""
    it = iter(patterns)
    feedbacks: list[list[str] | None] = []

    def gen(feedback):
        feedbacks.append(feedback)
        return next(it)

    gen.feedbacks = feedbacks
    return gen


def test_a_clean_first_take_needs_one_call():
    gen = _gen_sequence(_drive_clean())
    out = verified_riff(gen, _section(), _CYCLE)
    assert out is not None and len(gen.feedbacks) == 1 and gen.feedbacks[0] is None


def test_a_weak_take_is_rerolled_with_the_exact_violations():
    good = _drive_clean()
    gen = _gen_sequence(_melody(), good)
    out = verified_riff(gen, _section(), _CYCLE)
    assert out is good                            # the repaired take is returned
    assert len(gen.feedbacks) == 2                # bounded: one re-roll
    assert gen.feedbacks[1] and any("melody" in v for v in gen.feedbacks[1])


def test_never_clean_keeps_the_best_of_n():
    bad = _melody()                               # many violations
    better = _drive_clean()
    better.notes[0] = _n("S", 1.0)                # exactly one violation (weightless sam)
    gen = _gen_sequence(bad, better)
    out = verified_riff(gen, _section(), _CYCLE)
    assert out is better                          # fewest violations wins; never fatal


def test_the_verifier_respects_the_sections_mode():
    # the same pads cycle FAILS a drive section but PASSES an antara (pads) section
    gen_pads = _gen_sequence(_pads_clean())
    out = verified_riff(gen_pads, _section(SectionKind.MELODY, "antara"), _CYCLE)
    assert out is not None and len(gen_pads.feedbacks) == 1


# --- open_the_rings: the deterministic sustain guarantee ---------------------------

def _mute_wall() -> RiffPattern:
    """The live Malkauns failure in miniature: a legal drive cycle where EVERY note —
    even the long chorded ones — is palm-muted, so nothing rings."""
    return RiffPattern(notes=[
        _n("S", 1.0, chord=["S"], technique="palm_mute"),
        *[_n("S", 0.5, chord=["S"], technique="palm_mute") for _ in range(6)],
        _n("S", 1.0, rest=True),
        *[_n("S", 0.5, chord=["S"], technique="palm_mute") for _ in range(4)],
        _n("S", 1.0, chord=["P"], technique="palm_mute"),
    ])


def test_open_the_rings_demutes_the_longest_chords():
    out = open_the_rings(_mute_wall(), RiffMode.DRIVE)
    opened = [n for n in out.notes if not n.rest and n.technique is None]
    assert opened and all(n.dur >= 1.0 and n.chord for n in opened)   # longest chorded first
    sounding = [n for n in out.notes if not n.rest]
    ring = sum(n.dur for n in opened)
    assert ring >= 0.2 * sum(n.dur for n in sounding)                 # the DRIVE budget is met
    chugs = [n for n in sounding if n.dur < 1.0]
    assert all(n.technique == "palm_mute" for n in chugs)             # the chug ground survives


def test_open_the_rings_is_a_noop_when_the_budget_is_met():
    drive, stabs = _drive_clean(), _stabs_clean()
    assert open_the_rings(drive, RiffMode.DRIVE) == drive             # already rings enough
    assert open_the_rings(stabs, RiffMode.STABS) == stabs             # STABS has no ring budget


def test_a_never_clean_riff_still_comes_back_ringing():
    # both (all three, with the raised retry) takes are mute walls — the fallback repairs
    # the best take, so the rendered riff is GUARANTEED sustained chords
    gen = _gen_sequence(_mute_wall(), _mute_wall(), _mute_wall())
    out = verified_riff(gen, _section(SectionKind.RIFF, "mukhada"), _CYCLE)
    assert len(gen.feedbacks) == 3                                    # tries raised to 2 re-rolls
    assert any(not n.rest and n.dur >= 1.0 and n.technique is None for n in out.notes)


# --- chugs: the DRIVE palm-mute floor + the PADS between-ring chug-fill (2026-07-19) ----

def _drive_unchugged() -> RiffPattern:
    """The clean drive cycle with the palm-mute stripped off the ground — everything else
    (ground share, ring, rest, weighted sam) is identical, so only the chug floor fails."""
    return RiffPattern(notes=[
        n.model_copy(update={"technique": None}) if n.technique == "palm_mute" else n
        for n in _drive_clean().notes])


def test_drive_requires_palm_muted_chugs():
    # the ground can be on one pitch yet un-muted — a chug is an ARTICULATION, so that must
    # be caught (Sujit: chugs too few). It is the ONLY thing wrong with this otherwise-clean cycle.
    viol = verify_riff(_drive_unchugged(), mode=RiffMode.DRIVE, cycle_beats=_CYCLE)
    assert len(viol) == 1 and "palm-muted CHUGS" in viol[0]


def test_chug_the_ground_guarantees_the_floor():
    # the deterministic backstop marks short ground notes palm_mute until the floor is met,
    # and the result is clean (articulation-only surgery, nothing else disturbed)
    repaired = _chug_the_ground(_drive_unchugged())
    sounding = [n for n in repaired.notes if not n.rest]
    chug = sum(1 for n in sounding if n.technique == "palm_mute")
    assert chug / len(sounding) >= 0.30
    assert not verify_riff(repaired, mode=RiffMode.DRIVE, cycle_beats=_CYCLE)


def test_pads_reject_back_to_back_rings():
    # rings edge-to-edge leave no room to chug between them — flagged (only the rest floor)
    no_gap = RiffPattern(notes=[_n("S", 4.0, chord=["S"]), _n("g", 4.0, chord=["g"])])
    viol = verify_riff(no_gap, mode=RiffMode.PADS, cycle_beats=_CYCLE)
    assert len(viol) == 1 and "back-to-back" in viol[0]


def test_pads_chugs_fill_the_gaps_between_rings():
    # code drops palm-muted ground chugs into the gaps; the rings and the total length survive
    pat = RiffPattern(notes=[_n("S", 3.0, chord=["S"]), _n("S", 2.0, rest=True),
                             _n("S", 2.0, chord=["P"]), _n("S", 1.0, rest=True)])
    filled = _chug_fill_pads(pat)
    chugs = [n for n in filled.notes if n.technique == "palm_mute"]
    assert chugs and all(n.swara == "S" and n.oct == 0 for n in chugs)  # on the ground pitch (Sa)
    assert abs(sum(n.dur for n in filled.notes) - sum(n.dur for n in pat.notes)) < 1e-6
    assert any(n.dur == 3.0 and n.chord == ["S"] for n in filled.notes)  # the ring is untouched


def test_verified_pads_returns_chugs_between_the_rings():
    # end-to-end: a clean PADS take (rings + a gap) comes back with chugs in the gap
    result = verified_riff(lambda _fb: _pads_clean(), _section(SectionKind.TAAN), _CYCLE)
    assert any(n.technique == "palm_mute" for n in result.notes)


# --- memorability: the DRIVE riff is built around a restated hook (2026-07-19) ---------

def _drive_wandering() -> RiffPattern:
    """A chug-grounded drive cycle whose MOVEMENT is a new figure every time (A B C D) —
    the wandering, forgettable shape GPT flagged."""
    return RiffPattern(notes=[
        _n("S", 1.0, chord=["S"]), _n("S", 0.5, technique="palm_mute"),
        _n("g", 0.5), _n("m", 0.5),                       # figure A
        _n("S", 0.5, technique="palm_mute"),
        _n("d", 0.5), _n("n", 0.5),                       # figure B (new)
        _n("S", 0.5, technique="palm_mute"),
        _n("m", 0.5), _n("P", 0.5),                       # figure C (new)
        _n("S", 0.5, technique="palm_mute"), _n("S", 1.0, chord=["P"])])


def _drive_hooky() -> RiffPattern:
    """The SAME figure restated (A A' A) between chugs — a hook, not a wandering line."""
    return RiffPattern(notes=[
        _n("S", 1.0, chord=["S"]),
        _n("S", 0.5, technique="palm_mute"), _n("g", 0.5), _n("m", 0.5),   # figure A
        _n("S", 0.5, technique="palm_mute"), _n("g", 0.5), _n("m", 0.5),   # figure A again
        _n("S", 0.5, technique="palm_mute"), _n("g", 0.5), _n("m", 0.5),   # figure A again
        _n("S", 1.0, chord=["P"])])


def test_drive_flags_a_wandering_riff_with_no_hook():
    viol = verify_riff(_drive_wandering(), mode=RiffMode.DRIVE, cycle_beats=_CYCLE)
    assert any("A A' A B" in v for v in viol)             # asked to restate a hook


def test_drive_accepts_a_restated_hook():
    viol = verify_riff(_drive_hooky(), mode=RiffMode.DRIVE, cycle_beats=_CYCLE)
    assert not any("A A' A B" in v for v in viol)         # a repeated figure is not "wandering"


def test_drive_brief_asks_for_a_restated_hook():
    brief = MODE_BRIEFS[RiffMode.DRIVE]
    assert "A A' A B" in brief and "hook" in brief.lower()


def test_drive_flags_straight_eighths():
    # every note the same length -> flagged for rhythmic monotony (GPT's "8th 8th 8th 8th")
    monotone = RiffPattern(notes=[_n("S", 0.5, technique="palm_mute") for _ in range(16)])
    viol = verify_riff(monotone, mode=RiffMode.DRIVE, cycle_beats=_CYCLE)
    assert any("same length" in v for v in viol)


def test_drive_clean_keeps_its_rhythmic_contrast():
    # the clean fixture (chugs + longer rings) is NOT flagged — the check is a lenient backstop
    viol = verify_riff(_drive_clean(), mode=RiffMode.DRIVE, cycle_beats=_CYCLE)
    assert not any("same length" in v for v in viol)


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
