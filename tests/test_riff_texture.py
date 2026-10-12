"""
Tests for the riff TEXTURE layer — all pure (no key, no cost).

Since 2026-10-11 the layer has two halves (the A/B/C experiment — the riff Sujit judged best
failed the old budgets twice). `verify_riff` REJECTS only what is physical: the cycle fills
to the sam, a mute cannot sustain, a chord cannot bend. `texture_notes` REPORTS the mode's
recipe (chugs, rings, silence, weight, rations, hook, rhythmic variety) without ever forcing a
re-roll, and `texture_measures` gives pitch economy as plain numbers with no pass line. The
mode is decided by CODE from the section's gat role, and `verified_riff` re-rolls only on a
hard fault, keeping the best of a bounded number of takes.

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
    riff_severity,
    riff_underfilled,
    texture_measures,
    texture_notes,
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


def _hard(pattern: RiffPattern) -> list[str]:
    """What REJECTS a cycle: physics and the loop, nothing else."""
    return verify_riff(pattern, cycle_beats=_CYCLE)


def _notes(pattern: RiffPattern, mode: RiffMode = RiffMode.DRIVE) -> list[str]:
    """What is only REPORTED: the mode's texture recipe."""
    return texture_notes(pattern, mode=mode, cycle_beats=_CYCLE)


def _shuffle() -> RiffPattern:
    """Song A's riff in miniature (the one Sujit judged best): a half-step SHUFFLE between Sa
    and komal re with gallops — roots change on most strokes and Sa holds under half of them.
    The old budgets rejected this twice (ground share, change rate)."""
    return RiffPattern(notes=[
        _n("S", 0.5), _n("S", 0.25), _n("S", 0.25), _n("r", 0.5), _n("S", 0.5), _n("r", 0.5),
        _n("r", 0.25), _n("S", 0.25), _n("r", 0.5), _n("d", 0.5), _n("P", 0.5), _n("S", 1.0),
        _n("r", 0.5), _n("S", 1.0), _n("S", 1.0, rest=True)])


# --- the mode is decided by CODE from the section's gat role ---------------------

def test_mode_follows_the_form_role_over_the_kind():
    # an antara MELODY section pads (the sitar owns the movement)...
    assert riff_mode_for(_section(SectionKind.MELODY, "antara")) is RiffMode.PADS
    # ...while a plain MELODY section drives
    assert riff_mode_for(_section(SectionKind.MELODY)) is RiffMode.DRIVE


def test_mukhada_and_climax_drive_short_taan_pads_breakdown_stabs():
    assert riff_mode_for(_section(SectionKind.RIFF, "mukhada")) is RiffMode.DRIVE
    assert riff_mode_for(_section(SectionKind.TAAN, "taan_long")) is RiffMode.DRIVE   # the climax
    assert riff_mode_for(_section(SectionKind.TAAN, "taan_short")) is RiffMode.PADS
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
    text = " ".join(_notes(muted, RiffMode.STABS))
    assert "RINGS" in text and "OPEN chord" in text


def test_a_breakdown_that_opens_its_downbeat_passes():
    assert not [v for v in _notes(_stabs_clean(), RiffMode.STABS)
                if "RINGS" in v]


# --- hard faults reject; DRIVE's recipe is reported ------------------------------

def test_a_clean_drive_cycle_passes():
    assert _hard(_drive_clean()) == [] and _notes(_drive_clean()) == []


def test_a_chug_written_as_a_sustain_is_rejected():
    """The muting hand damps, so a long palm-muted note is a sustain the articulation cannot
    deliver — measured 2026-09-14, 21% of palm-muted notes were written a beat or longer and
    played as a click followed by dead air."""
    pattern = _drive_clean()
    pattern.notes[1] = _n("S", 2.0, technique="palm_mute")
    text = " ".join(_hard(pattern))
    assert "cannot sustain" in text and "OPEN" in text


def test_a_quarter_note_chug_is_still_fine():
    """The cap must not outlaw an ordinary doom chug — only the ones asking to ring."""
    pattern = _drive_clean()
    pattern.notes[1] = _n("S", 1.0, technique="palm_mute")
    assert not [v for v in _hard(pattern)
                if "cannot sustain" in v]


def test_a_pitch_gesture_on_a_chord_is_rejected():
    """The pitch wheel is channel-wide, so bending a chord bends every tone of it; the
    renderer now drops such a gesture, and a dropped gesture the model thinks it wrote is
    worse than one it never wrote."""
    pattern = _drive_clean()
    pattern.notes[11] = _n("g", 0.5, chord=["g"], technique="slide")
    text = " ".join(_hard(pattern))
    assert "CHORD" in text and "single notes" in text


def test_slides_are_rationed():
    pattern = _drive_clean()
    pattern.notes[5] = _n("m", 0.5, technique="slide")     # a second slide in the cycle
    text = " ".join(_notes(pattern))
    assert "FRETTED" in text


def test_a_shuffle_between_two_roots_is_a_riff():
    """Song A's half-step shuffle: the roots change on most strokes and Sa holds under half —
    exactly what the old ground/change budgets rejected. Physically fine, nothing in the
    recipe objects to its pitches, and its measures are simply reported."""
    shuffle = _shuffle()
    assert _hard(shuffle) == []
    notes = " ".join(_notes(shuffle))
    assert "change pitch" not in notes and "one ground pitch" not in notes   # the removed rules
    measures = texture_measures(shuffle)
    assert measures["pitch_change"] > 0.55 and measures["ground_share"] < 0.55


def test_no_pitch_statistic_is_a_pass_line():
    """Pitch economy is MEASURED, never judged: a shuffle and a wandering line both get
    numbers, and neither is rejected for them (they overlap on real renders)."""
    for pattern in (_shuffle(), _melody()):
        measures = texture_measures(pattern)
        assert set(measures) == {"pitch_change", "ground_share", "top_two_share",
                                 "distinct_pitches"}
        assert not [v for v in _hard(pattern) if "melody" in v]


def test_a_run_of_identical_chugs_is_rejected():
    """Six identical eighth-note chugs at one velocity is a drum machine, not a picking hand
    (heard on the 2026-07-20 renders)."""
    pattern = RiffPattern(notes=[_n("S", 1.0, chord=["S"])]
                          + [_n("S", 0.5, technique="palm_mute") for _ in range(6)]
                          + [_n("S", 1.0, rest=True), _n("g", 0.5), _n("S", 1.0, chord=["P"])])
    text = " ".join(_notes(pattern))
    assert "ACCENTS" in text


def test_an_accented_chug_run_passes():
    pattern = RiffPattern(notes=[_n("S", 1.0, chord=["S"])]
                          + [RiffNote(swara="S", oct=0, dur=0.5, technique="palm_mute", vel=v)
                             for v in (112, 92, 100, 92, 112, 92)]
                          + [_n("S", 1.0, rest=True), _n("g", 0.5), _n("S", 1.0, chord=["P"])])
    assert not [v for v in _notes(pattern)
                if "ACCENTS" in v]


def test_a_rest_breaks_a_chug_run():
    """Two three-chug figures either side of a rest are two figures, not a run of six — the
    detector reads the full cycle so a dropped rest cannot invent a violation."""
    pattern = RiffPattern(notes=[_n("S", 1.0, chord=["S"])]
                          + [_n("S", 0.5, technique="palm_mute") for _ in range(3)]
                          + [_n("S", 1.0, rest=True)]
                          + [_n("S", 0.5, technique="palm_mute") for _ in range(3)]
                          + [_n("g", 0.5), _n("S", 1.0, chord=["P"])])
    assert not [v for v in _notes(pattern)
                if "ACCENTS" in v]


def test_the_live_failure_melody_is_reported_not_rejected():
    """The July 'melody' riff is physically playable, so code does not reject it — whether it
    grooves is a judgment. What the recipe CAN say about it is reported."""
    assert _hard(_melody()) == []
    text = " ".join(_notes(_melody()))
    assert "rest" in text                         # the missing silence
    assert "sam" in text                          # the weightless downbeat
    assert texture_measures(_melody())["pitch_change"] == 1.0


def test_drive_requires_a_weighted_sam():
    pattern = _drive_clean()
    pattern.notes[0] = _n("S", 0.5)               # naked short sam
    viol = _notes(pattern)
    assert any("sam" in v for v in viol)


def test_drive_rations_the_bright_colour_stacks():
    pattern = _drive_clean()
    # pile bright colour (R over S seats as an add9) onto three ground chugs
    for i in (1, 2, 3):
        pattern.notes[i] = _n("S", 0.5, chord=["R"], technique="palm_mute")
    viol = _notes(pattern)
    assert any("colour" in v and "light and happy" in v for v in viol)


def test_the_duration_sum_must_roughly_fill_the_cycle():
    tiny = RiffPattern(notes=[_n("S", 0.5, chord=["S"]), _n("S", 0.5, rest=True)])
    viol = _hard(tiny)
    assert any("sum" in v for v in viol)


def test_fancy_techniques_are_rationed():
    pattern = _drive_clean()
    pattern.notes[1] = _n("S", 0.5, technique="pick_scrape")
    pattern.notes[2] = _n("S", 0.5, technique="pick_scrape")
    viol = _notes(pattern)
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
    viol = _notes(pattern)
    assert any("RINGS open" in v for v in viol)


def test_a_palm_muted_hold_is_not_sam_weight():
    pattern = _drive_clean()
    pattern.notes[0] = _n("S", 1.0, technique="palm_mute")   # written long, gates to a tick
    viol = _notes(pattern)
    assert any("sam" in v for v in viol)


# --- PADS: sustained ringing chords, not motion ----------------------------------

def test_a_clean_pads_cycle_passes():
    assert _notes(_pads_clean(), RiffMode.PADS) == []


def test_pads_reject_a_busy_riff():
    viol = _notes(_drive_clean(), RiffMode.PADS)
    assert any("SUSTAIN" in v or "rings" in v for v in viol)


def test_pads_require_a_long_chorded_ring():
    pattern = _pads_clean()
    pattern.notes[0] = _n("S", 3.0)               # the long hold loses its chord stack
    viol = _notes(pattern, RiffMode.PADS)
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
    viol = _notes(pattern, RiffMode.PADS)
    assert any("NEVER ring" in v for v in viol)          # the ring share sees through the duration
    assert any("not palm-muted" in v for v in viol)      # and the long-ring check does too


# --- STABS: hit then silence, low, weighted ---------------------------------------

def test_a_clean_stabs_cycle_passes():
    assert _notes(_stabs_clean(), RiffMode.STABS) == []


def test_stabs_require_real_silence():
    viol = _notes(_melody(), RiffMode.STABS)
    assert any("silent" in v or "SILENCE" in v for v in viol)


def test_stabs_stay_low():
    pattern = _stabs_clean()
    pattern.notes[2] = _n("S", 0.5, oct=1, chord=["S"])
    viol = _notes(pattern, RiffMode.STABS)
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


def _held_chug() -> RiffPattern:
    """A drive cycle with ONE hard fault: a palm mute written as a 2-beat sustain."""
    pattern = _drive_clean()
    pattern.notes[1] = _n("S", 2.0, technique="palm_mute")
    return pattern


def test_a_weak_take_is_rerolled_with_the_exact_violations():
    good = _drive_clean()
    gen = _gen_sequence(_held_chug(), good)
    out = verified_riff(gen, _section(), _CYCLE)
    assert out is good                            # the repaired take is returned
    assert len(gen.feedbacks) == 2                # bounded: one re-roll
    assert gen.feedbacks[1] and any("cannot sustain" in v for v in gen.feedbacks[1])


def test_texture_alone_never_triggers_a_reroll():
    """The melody and the shuffle both pass on the first take — taste is reported in the
    event, not enforced with a paid re-roll."""
    for take in (_melody(), _shuffle()):
        gen = _gen_sequence(take)
        verified_riff(gen, _section(), _CYCLE)
        assert gen.feedbacks == [None]


def test_never_clean_keeps_the_best_of_n():
    bad = RiffPattern(notes=[_n("S", 2.0, technique="palm_mute"), _n("S", 0.5)])  # short + held
    better = _held_chug()                         # exactly one hard violation
    gen = _gen_sequence(bad, better, bad)
    out = verified_riff(gen, _section(), _CYCLE)
    assert len(gen.feedbacks) == 3                # bounded: two re-rolls, then give up
    assert out.notes[2:] == better.notes[2:]      # fewest violations wins; never fatal


def test_the_texture_notes_respect_the_sections_mode():
    # the same pads cycle is off-recipe for a drive section and on-recipe for a pads one
    assert _notes(_pads_clean(), RiffMode.DRIVE)
    assert _notes(_pads_clean(), RiffMode.PADS) == []


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


def test_a_mute_wall_still_comes_back_ringing():
    # a mute wall is physically playable, so it is accepted on the first take — and the
    # deterministic guarantee still opens its longest chords, so the riff RINGS
    gen = _gen_sequence(_mute_wall())
    out = verified_riff(gen, _section(SectionKind.RIFF, "mukhada"), _CYCLE)
    assert len(gen.feedbacks) == 1
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
    viol = _notes(_drive_unchugged())
    assert len(viol) == 1 and "palm-muted CHUGS" in viol[0]


def test_chug_the_ground_guarantees_the_floor():
    # the deterministic backstop marks short ground notes palm_mute until the floor is met,
    # and the result is clean (articulation-only surgery, nothing else disturbed)
    repaired = _chug_the_ground(_drive_unchugged())
    sounding = [n for n in repaired.notes if not n.rest]
    chug = sum(1 for n in sounding if n.technique == "palm_mute")
    assert chug / len(sounding) >= 0.30
    assert not _notes(repaired)


def test_pads_reject_back_to_back_rings():
    # rings edge-to-edge leave no room to chug between them — flagged (only the rest floor)
    no_gap = RiffPattern(notes=[_n("S", 4.0, chord=["S"]), _n("g", 4.0, chord=["g"])])
    viol = _notes(no_gap, RiffMode.PADS)
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
    viol = _notes(_drive_wandering())
    assert any("A A' A B" in v for v in viol)             # asked to restate a hook


def test_drive_accepts_a_restated_hook():
    viol = _notes(_drive_hooky())
    assert not any("A A' A B" in v for v in viol)         # a repeated figure is not "wandering"


def test_drive_brief_asks_for_a_restated_hook():
    brief = MODE_BRIEFS[RiffMode.DRIVE]
    assert "A A' A B" in brief and "hook" in brief.lower()


def test_drive_flags_straight_eighths():
    # every note the same length -> flagged for rhythmic monotony (GPT's "8th 8th 8th 8th")
    monotone = RiffPattern(notes=[_n("S", 0.5, technique="palm_mute") for _ in range(16)])
    viol = _notes(monotone)
    assert any("same length" in v for v in viol)


def test_drive_clean_keeps_its_rhythmic_contrast():
    # the clean fixture (chugs + longer rings) is NOT flagged — the check is a lenient backstop
    viol = _notes(_drive_clean())
    assert not any("same length" in v for v in viol)



# --- best-of-N by SEVERITY: a near-empty cycle never wins on violation count ----------

def _near_empty() -> RiffPattern:
    """One stroke and a cycle of rest — it fills the cycle on paper and trips almost nothing."""
    return RiffPattern(notes=[_n("S", 1.0, chord=["S"]), _n("S", _CYCLE - 1.0, rest=True)])


def test_a_cycle_of_almost_nothing_is_underfilled_but_sparse_stabs_are_not():
    assert riff_underfilled(_near_empty(), _CYCLE)
    assert not riff_underfilled(_drive_clean(), _CYCLE)
    stabs = RiffPattern(notes=[_n("S", 0.5, chord=["S"]), _n("S", 3.5, rest=True)] * 4)
    assert not riff_underfilled(stabs, 16.0)                 # four half-beat hits in sixteen
    assert riff_severity(_drive_clean(), _CYCLE, ["a", "b"]) < riff_severity(_near_empty(), _CYCLE, ["a"])


def test_best_of_n_plays_the_fuller_riff_over_an_emptier_one_with_fewer_faults():
    empty, full = _near_empty(), _drive_clean()

    def extra(pattern: RiffPattern) -> list[str]:            # neither take ever comes back clean
        return ["a"] if pattern is empty else ["a", "b"]

    gen = _gen_sequence(empty, full, empty)
    out = verified_riff(gen, _section(), _CYCLE, extra_check=extra)
    assert len(gen.feedbacks) == 3                           # bounded: every re-roll spent
    assert any(n.swara == "g" for n in out.notes)            # the full take's figure plays


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
