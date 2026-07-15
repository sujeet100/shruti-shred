"""
Riff TEXTURE — the metal counterpart to the gat verifier (`crew/gat_verifier.py`).

The diagnosed failure (measured on the 2026-07-15 live render, `out/fusion.json`): the
rhythm guitar wrote a busy low MELODY — a 79% pitch-change rate, almost no repeated-root
chug ground, bright add9/tenth stacks outnumbering power chords, and nothing sustained.
Metal heaviness is articulation, rhythm and SPACE, not note sequences — and those are
CHECKABLE. Same design as the gat cells: the feel is translated into rigid budgets and
enforced with a bounded verify + feedback re-roll (`verified_riff`), never re-prompted
vaguely. The verifier judges structure only (ground share, weight, space, ration); which
pitches and figures — the taste — stays the LLM's.

A section's `RiffMode` is decided by CODE from its gat form_role / kind (the same pattern
as the drums' `GrooveEnergy`): DRIVE is the chugging engine, PADS sustains ringing power
chords under the sitar's movement (Sujit: long chords serve sitar fusion better than busy
riffs), STABS is the sparse low syncopated crush. The mode picks both the prompt brief and
the verifier's budgets — the ask and the enforcement always agree.

Pure: no LLM, no I/O; `verified_riff` takes the generation as an injected callable.
"""

from __future__ import annotations

from collections import Counter
from enum import Enum
from typing import Callable, Final, Optional

from crew.contracts import RiffNote, RiffPattern, Section, SectionKind
from raga import SWARAS

# Bounded repair: extra re-rolls of a cycle that misses its budgets (best-of-N kept —
# a weak riff plays rather than killing a live run). Same bound as the lead's gat cells.
RIFF_REPAIR_TRIES: Final = 1

# --- the budgets (deliberately loose — they flag gross misses, not taste) ---------------
_FILL_LO: Final = 0.7               # durations must roughly fill the cycle...
_FILL_HI: Final = 1.3               # ...gross over/undershoot means the model didn't count
_GROUND_MIN_SHARE: Final = 0.35     # DRIVE: share of sounding notes on the modal (ground) pitch
_CHANGE_MAX_DRIVE: Final = 0.55     # DRIVE: consecutive-note pitch-change ceiling (melody tell)
_CHANGE_MAX_STABS: Final = 0.45     # STABS: hammer one root; movement is the exception
_REST_SHARE_MAX: Final = 0.35       # DRIVE: silence is seasoning, not the dish
_REST_SHARE_STABS: Final = 0.20     # STABS: hit-then-silence IS the texture (floor, not cap)
_WEIGHT_DUR: Final = 1.0            # a note this long counts as weight even unchorded
_COLOR_MAX: Final = 2               # bright stacks (add9/tenth seats) per cycle — a spice
_COLOR_MAX_STABS: Final = 1
_RING_SHARE_MIN: Final = 0.55       # PADS: share of sounding DURATION in notes >= 1 beat
_RING_LONG: Final = 2.0             # PADS: at least one chord held this long...
_BUSY_NOTE: Final = 0.25            # PADS: sixteenths are movement —
_BUSY_SHARE_MAX: Final = 0.25       # ...keep them a small minority
_STAB_WEIGHT_SHARE: Final = 0.5     # STABS: at least half the hits carry weight
_SCRAPE_MAX: Final = 1              # pick scrapes per cycle (an entrance gesture, not a tic)
_LONG_SLIDE_MAX: Final = 2          # long slides per cycle
# Colour = a chord tone that seats ABOVE the octave (add9 / tenth): interval class 1-4
# over the root (see render._seat_chord_tone). Power weight = octave / fourth / fifth.
_COLOR_CLASSES: Final = frozenset({1, 2, 3, 4})


class RiffMode(str, Enum):
    """How a section's rhythm guitar behaves — decided by CODE from the section's role."""
    DRIVE = "drive"      # the chugging engine: ground + earned movement
    PADS = "pads"        # sustained ringing power chords under the sitar's movement
    STABS = "stabs"      # sparse, low, syncopated chorded hits with real silence


_MODE_BY_ROLE: Final[dict[str, RiffMode]] = {
    "mukhada": RiffMode.DRIVE, "manjha": RiffMode.DRIVE,
    "antara": RiffMode.PADS, "taan_short": RiffMode.PADS, "taan_long": RiffMode.PADS,
    "intro": RiffMode.PADS, "outro": RiffMode.PADS,
    "breakdown": RiffMode.STABS, "tihai": RiffMode.STABS,
}
_MODE_BY_KIND: Final[dict[SectionKind, RiffMode]] = {
    SectionKind.RIFF: RiffMode.DRIVE, SectionKind.MELODY: RiffMode.DRIVE,
    SectionKind.SOLO: RiffMode.DRIVE, SectionKind.TAAN: RiffMode.PADS,
    SectionKind.ALAAP: RiffMode.PADS, SectionKind.BREAKDOWN: RiffMode.STABS,
    SectionKind.OUTRO: RiffMode.PADS,
}


def riff_mode_for(section: Section) -> RiffMode:
    """The section's texture mode — its gat form_role first, its kind as the fallback."""
    if section.form_role in _MODE_BY_ROLE:
        return _MODE_BY_ROLE[section.form_role]
    return _MODE_BY_KIND.get(section.kind, RiffMode.DRIVE)


# What each mode ASKS for — rendered into the prompt as {mode_brief}. The numbers match
# the verifier's budgets, so the model is told exactly what will be enforced.
MODE_BRIEFS: Final[dict[RiffMode, str]] = {
    RiffMode.DRIVE: (
        "DRIVE — you are the engine. The CHUG GROUND is the default texture: between every "
        "melodic movement RETURN to repeated short palm-muted strokes on ONE low pitch (Sa, "
        "or this riff's root) — at least a third of your notes sit on that ground, and no "
        "more than about half of consecutive notes may change pitch (a riff is not a "
        "melody). Movement is EARNED: a short 2-4 note figure from the pakad, then back to "
        "the chug. Put POWER-CHORD weight (the root's own swara, or P) on the sam and tali; "
        "bright colour stacks (add9/tenth — R or G over the root) are a spice, at most 2 per "
        "cycle. Leave at least one true rest; rough space budget: ~40% chug, ~25% ring, "
        "~20% movement, ~15% silence."),
    RiffMode.PADS: (
        "PADS — the sitar carries ALL movement here; you are texture, not motion. Sustain "
        "wide RINGING power chords: one or two per vibhag, most of your sounding time in "
        "notes a beat or longer, at least one chord held 2+ beats — and every long chord "
        "CARRIES a chord stack (own swara / P) so it blooms. No runs (sixteenths stay a "
        "small minority), no busy chugging. Think Tool/Opeth weight under a melody: strike, "
        "let it decay, leave the foreground empty for the raga line."),
    RiffMode.STABS: (
        "STABS — sparse, low, syncopated POWER-CHORD hits locked to the tala's accents: "
        "hit, then SILENCE (at least a fifth of the cycle is true rest — the silence IS the "
        "heaviness). Stay in the low register (oct 0 or below), give at least half the hits "
        "chord weight, hammer ONE root and move only for the final stab into the sam; a "
        "displaced 16th before an accent gives the lurch."),
}


def _sounding(notes: list[RiffNote]) -> list[RiffNote]:
    return [n for n in notes if not n.rest]


def _pitch_change_rate(sounding: list[RiffNote]) -> float:
    if len(sounding) < 2:
        return 0.0
    changes = sum(1 for a, b in zip(sounding, sounding[1:])
                  if (a.swara, a.oct) != (b.swara, b.oct))
    return changes / (len(sounding) - 1)


def _ground_share(sounding: list[RiffNote]) -> float:
    """Share of sounding notes on the MODAL pitch — the riff's ground."""
    counts = Counter((n.swara, n.oct) for n in sounding)
    return counts.most_common(1)[0][1] / len(sounding)


def _is_color(note: RiffNote) -> bool:
    """Does this note's chord stack include a BRIGHT tone (one that seats above the
    octave as an add9/tenth — interval class 1-4 over the root)?"""
    return any((SWARAS[c] - SWARAS[note.swara]) % 12 in _COLOR_CLASSES
               for c in (note.chord or []))


def _weighted(note: RiffNote) -> bool:
    return bool(note.chord) or note.dur >= _WEIGHT_DUR


def _shared_violations(notes: list[RiffNote], sounding: list[RiffNote],
                       cycle_beats: float) -> list[str]:
    viol: list[str] = []
    total = sum(n.dur for n in notes)
    if not _FILL_LO * cycle_beats <= total <= _FILL_HI * cycle_beats:
        viol.append(f"the cycle's durations (rests included) sum to {total:g} beats but one "
                    f"cycle is {cycle_beats:g} — count the beats so the loop lands on the sam")
    scrapes = sum(1 for n in sounding if n.technique == "pick_scrape")
    if scrapes > _SCRAPE_MAX:
        viol.append(f"{scrapes} pick scrapes in one cycle — a scrape is an entrance/climax "
                    f"gesture, use at most {_SCRAPE_MAX}")
    slides = sum(1 for n in sounding if n.technique == "long_slide")
    if slides > _LONG_SLIDE_MAX:
        viol.append(f"{slides} long slides in one cycle — a long slide marks a seam or a big "
                    f"accent, use at most {_LONG_SLIDE_MAX}")
    return viol


def _drive_violations(notes: list[RiffNote], sounding: list[RiffNote],
                      cycle_beats: float) -> list[str]:
    viol: list[str] = []
    if _ground_share(sounding) < _GROUND_MIN_SHARE:
        viol.append(f"only {_ground_share(sounding):.0%} of the notes sit on one ground pitch "
                    f"(need >= {_GROUND_MIN_SHARE:.0%}) — return to the low palm-muted root "
                    f"between figures; the chug ground is the riff's floor")
    rate = _pitch_change_rate(sounding)
    if rate > _CHANGE_MAX_DRIVE:
        viol.append(f"{rate:.0%} of consecutive notes change pitch (cap {_CHANGE_MAX_DRIVE:.0%})"
                    f" — this is a melody, not a riff; repeat the root between movements")
    rests = [n for n in notes if n.rest and n.dur >= 0.25]
    if not rests:
        viol.append("no true rest in the cycle — leave at least one deliberate silence; the "
                    "gap is where the tabla and the gat answer")
    rest_beats = sum(n.dur for n in notes if n.rest)
    if rest_beats > _REST_SHARE_MAX * cycle_beats:
        viol.append(f"{rest_beats:g} beats of the {cycle_beats:g}-beat cycle are silent — a "
                    f"drive riff grounds the band; keep silence under {_REST_SHARE_MAX:.0%}")
    if notes and not notes[0].rest and not _weighted(notes[0]):
        viol.append("the sam note carries no weight — open the cycle with a chord (the root's "
                    "own swara, or P) or a held note; the downbeat is the anchor")
    colors = sum(1 for n in sounding if _is_color(n))
    if colors > _COLOR_MAX:
        viol.append(f"{colors} bright colour stacks (add9/tenth seats) in one cycle — that is "
                    f"what makes the riff sound light and happy; keep at most {_COLOR_MAX} and "
                    f"make the rest power weight (the root's own swara, or P)")
    return viol


def _pads_violations(notes: list[RiffNote], sounding: list[RiffNote],
                     cycle_beats: float) -> list[str]:
    viol: list[str] = []
    total = sum(n.dur for n in sounding)
    ring = sum(n.dur for n in sounding if n.dur >= _WEIGHT_DUR)
    if ring < _RING_SHARE_MIN * total:
        viol.append(f"only {ring / total:.0%} of the sounding time rings (notes >= "
                    f"{_WEIGHT_DUR:g} beat) — pads SUSTAIN; hold wide chords and let them "
                    f"bloom while the sitar moves")
    if not any(n.dur >= _RING_LONG for n in sounding):
        viol.append(f"no chord is held {_RING_LONG:g}+ beats — a pad section needs at least "
                    f"one long ringing power chord")
    naked = [n for n in sounding if n.dur >= _RING_LONG and not n.chord]
    if naked:
        viol.append("a long held note carries no chord stack — give every 2+ beat ring "
                    "power-chord weight (the root's own swara, or P) so it blooms, not thins")
    busy = sum(1 for n in sounding if n.dur <= _BUSY_NOTE)
    if busy > _BUSY_SHARE_MAX * len(sounding):
        viol.append(f"{busy} of {len(sounding)} notes are sixteenths — pads are texture, not "
                    f"motion; the sitar owns the movement here")
    colors = sum(1 for n in sounding if _is_color(n))
    if colors > _COLOR_MAX:
        viol.append(f"{colors} bright colour stacks — pads want dark power weight (own swara "
                    f"/ P), at most {_COLOR_MAX} colours per cycle")
    return viol


def _stabs_violations(notes: list[RiffNote], sounding: list[RiffNote],
                      cycle_beats: float) -> list[str]:
    viol: list[str] = []
    rest_beats = sum(n.dur for n in notes if n.rest)
    if rest_beats < _REST_SHARE_STABS * cycle_beats:
        viol.append(f"only {rest_beats:g} beats of the {cycle_beats:g}-beat cycle are silent — "
                    f"stabs are hit-then-SILENCE; make at least {_REST_SHARE_STABS:.0%} of the "
                    f"cycle true rests")
    high = [n for n in sounding if n.oct > 0]
    if high:
        viol.append("the stabs leave the low register (oct above 0) — a breakdown lives on "
                    "the low string; stay at oct 0 or below")
    weighted = sum(1 for n in sounding if _weighted(n))
    if weighted < _STAB_WEIGHT_SHARE * len(sounding):
        viol.append(f"only {weighted} of {len(sounding)} hits carry weight — chord the stabs "
                    f"(own swara / P) or hold them; a naked short stab is a poke, not a crush")
    rate = _pitch_change_rate(sounding)
    if rate > _CHANGE_MAX_STABS:
        viol.append(f"{rate:.0%} of consecutive stabs change pitch — hammer ONE root and move "
                    f"only for the final stab into the sam")
    colors = sum(1 for n in sounding if _is_color(n))
    if colors > _COLOR_MAX_STABS:
        viol.append(f"{colors} bright colour stacks in a breakdown — stabs are the darkest "
                    f"texture; at most {_COLOR_MAX_STABS}")
    return viol


_MODE_CHECKS: Final[dict[RiffMode, Callable[[list[RiffNote], list[RiffNote], float],
                                            list[str]]]] = {
    RiffMode.DRIVE: _drive_violations,
    RiffMode.PADS: _pads_violations,
    RiffMode.STABS: _stabs_violations,
}


def verify_riff(pattern: RiffPattern, *, mode: RiffMode, cycle_beats: float) -> list[str]:
    """Return the riff cycle's TEXTURE violations against its mode's budgets (empty ==
    an idiomatic metal cycle). Pure.

    Checks structure only — ground share, pitch-change rate, weight on the sam, ring/
    sustain shares, real silence, the colour and fancy-technique rations, and that the
    durations actually fill the cycle. Which pitches, which figures, which pakad fragment
    — the taste — is never judged here (that stays with Rasik/Producer)."""
    sounding = _sounding(pattern.notes)
    if not sounding:
        return ["the riff has no sounding notes — even the sparsest mode strikes something"]
    viol = _shared_violations(pattern.notes, sounding, cycle_beats)
    viol += _MODE_CHECKS[mode](pattern.notes, sounding, cycle_beats)
    return viol


def verified_riff(gen: Callable[[Optional[list[str]]], RiffPattern], section: Section,
                  cycle_beats: float) -> RiffPattern:
    """Generate a VERIFIED riff cycle: call `gen(feedback)` and re-roll a cycle that
    misses its mode's budgets up to `RIFF_REPAIR_TRIES` times, feeding back the EXACT
    violations (a targeted re-roll, not a blind one). Bounded, best-of-N (fewest
    violations) when none come back clean — a weak riff plays; a live run never dies on
    taste. Pure control flow: `gen` is injected, so this tests with no LLM."""
    mode = riff_mode_for(section)
    best: Optional[RiffPattern] = None
    best_viol: Optional[list[str]] = None
    feedback: Optional[list[str]] = None
    for _ in range(RIFF_REPAIR_TRIES + 1):
        pattern = gen(feedback)
        viol = verify_riff(pattern, mode=mode, cycle_beats=cycle_beats)
        if not viol:
            return pattern
        feedback = viol                       # the re-roll sees EXACTLY what failed
        if best_viol is None or len(viol) < len(best_viol):
            best, best_viol = pattern, viol
    assert best is not None                   # the loop ran at least once
    return best
