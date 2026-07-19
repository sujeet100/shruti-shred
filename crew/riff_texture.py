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

The RING-GATE lesson (2026-07-16, measured on the Malkauns render): a ring is an OPEN
strike, not a written duration — the renderer gates a palm-muted note to a fixed ~70ms
chug whatever its duration, so the taan's "pads" (long PM notes) played as sparse ticks
right where the sitar needed a platform. Every sustain budget is therefore technique-aware
(`_rings`), and DRIVE now owes a minimum of open ringing weight too (Sujit's steer: the
rhythm guitar's melodic ambition stays low, its RESONANCE stays high).

Pure: no LLM, no I/O; `verified_riff` takes the generation as an injected callable.
"""

from __future__ import annotations

from collections import Counter
from enum import Enum
from typing import Callable, Final, Optional

from crew.contracts import RiffNote, RiffPattern, Section, SectionKind
from raga import SWARAS

# Bounded repair: extra re-rolls of a cycle that misses its budgets (best-of-N kept —
# a weak riff plays rather than killing a live run). Raised 1 -> 2 (2026-07-16): the live
# Malkauns run failed the open-ring budget on BOTH takes and best-of-N played an all-muted
# riff; one more targeted retry is one call, spent only when the take is already failing.
RIFF_REPAIR_TRIES: Final = 2

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
_RING_SHARE_MIN: Final = 0.55       # PADS: share of sounding DURATION in OPEN notes >= 1 beat
_RING_SHARE_MIN_DRIVE: Final = 0.2  # DRIVE: even the engine owes this much open ringing weight
_RING_LONG: Final = 2.0             # PADS: at least one chord held this long...
_BUSY_NOTE: Final = 0.25            # PADS: sixteenths are movement —
_BUSY_SHARE_MAX: Final = 0.25       # ...keep them a small minority
_STAB_WEIGHT_SHARE: Final = 0.5     # STABS: at least half the hits carry weight
_SCRAPE_MAX: Final = 1              # pick scrapes per cycle (an entrance gesture, not a tic)
_LONG_SLIDE_MAX: Final = 2          # long slides per cycle

# Chugs (Sujit 2026-07-19 + the external review: the riffs have too FEW palm-muted chugs, and
# the sustained (PADS) sections want chugs BETWEEN the long chords, not one unbroken drone). A
# chug is an ARTICULATION (palm_mute), not just a low pitch — DRIVE now owes a real palm-mute
# floor, and PADS leaves gaps that CODE fills with palm-muted ground chugs (ring -> chug -> ring).
_CHUG_MIN_SHARE_DRIVE: Final = 0.30  # DRIVE: share of sounding notes MARKED palm_mute (real chugs)
_PADS_REST_MIN: Final = 0.10         # PADS: leave this much of the cycle as gaps between rings...
_CHUG_SUBDIV: Final = 0.5            # ...which code fills with palm-muted ground chugs at this rate
_CHUG_FILL_MIN_GAP: Final = 0.5      # only a gap at least this long is chug-filled
_CHUG_FILL_BREATH: Final = 0.5       # leave this much silence before the next ring (when the gap allows)
_CHUG_VEL: Final = 108               # a solid palm-muted chug (never cut — the render sends CC7 full)

# Memorability (GPT review 2026-07-19: the riffs "move move move" instead of "HOOK, variation,
# HOOK" — a new figure every time (A B C D) reads as AI; restating ONE figure (A A' A B) is what
# a listener remembers). A metal riff's hook is its recurring MOVEMENT cell; the chug ground is
# separate. So DRIVE flags a cycle whose movement figures are MANY and ALL distinct — a wandering
# line with no restated hook. The real lift is the prompt; this is the backstop.
_HOOK_MIN_FIGURES: Final = 3         # this many movement figures, all distinct, = a wandering riff

# Rhythmic contrast (GPT: riffs read as straight "8th 8th 8th 8th" — mix quarter/dotted/8th/
# 16th-burst/triplet/rest). Lenient backstop: flag only NEAR-total monotony (one note value
# dominating), so a chug-plus-ring riff passes and the prompt does the real shaping.
_RHYTHM_UNIFORM_MAX: Final = 0.85    # DRIVE: one note value may cover at most this share...
_RHYTHM_MIN_NOTES: Final = 6         # ...checked only once the cycle has enough notes to judge
# Colour = a chord tone that seats ABOVE the octave (add9 / tenth): interval class 1-4
# over the root (see render._seat_chord_tone). Power weight = octave / fourth / fifth.
_COLOR_CLASSES: Final = frozenset({1, 2, 3, 4})


class RiffMode(str, Enum):
    """How a section's rhythm guitar behaves — decided by CODE from the section's role."""
    DRIVE = "drive"      # the chugging engine: ground + earned movement
    PADS = "pads"        # sustained ringing power chords under the sitar's movement
    STABS = "stabs"      # sparse, low, syncopated chorded hits with real silence


# The manjha PADS (changed from DRIVE 2026-07-16): it is the gat's LOW, CALM bridge — the
# Malkauns render put a full chug engine under its six sparse lead notes and it was the
# emptiest-feeling section. A quiet bridge wants a ringing chordal platform, simpler than
# the mukhada, not the same engine.
_MODE_BY_ROLE: Final[dict[str, RiffMode]] = {
    "mukhada": RiffMode.DRIVE, "manjha": RiffMode.PADS,
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
        "melodic movement RETURN to repeated short strokes on ONE low pitch (Sa, or this "
        "riff's root) and MARK them technique 'palm_mute' — the chug is an articulation, not "
        "just a low note. At least a third of your notes sit on that ground AND at least a "
        "third are palm-muted chugs, and no more than about half of consecutive notes may "
        "change pitch (a riff is not a melody). Movement is a HOOK, not novelty: pick ONE "
        "short 2-4 note figure from the pakad and RESTATE it across the cycle — state it, "
        "chug, restate it (verbatim, or varied/answered) — so the shape is A A' A B and a "
        "listener recognizes the riff after two hearings; do NOT introduce a new figure every "
        "time (A B C D is forgettable). Between the figures, back to the chug. Put POWER-CHORD "
        "weight (the root's own swara, or P) on the sam and tali; bright colour stacks "
        "(add9/tenth — R or G over the root) "
        "are a spice, at most 2 per cycle. BREATHE attack-then-resonance: at least ~20% of "
        "your sounding time is OPEN ringing chords a beat or longer — a ring is an open "
        "strike, a palm-muted note can never ring (it gates to a short chug whatever its "
        "duration). Leave at least one true rest; rough space budget: ~40% chug, ~25% ring, "
        "~20% movement, ~15% silence. VARY the note lengths against the chug (16ths, 8ths, a "
        "dotted or held accent, a rest) — never one steady value."),
    RiffMode.PADS: (
        "PADS — the sitar carries ALL movement here; you are texture, not motion. Sustain "
        "wide RINGING power chords: one or two per vibhag, most of your sounding time in "
        "notes a beat or longer, at least one chord held 2+ beats — and every long chord "
        "CARRIES a chord stack (own swara / P) so it blooms. Strike the chords OPEN, never "
        "palm-muted — a palm-muted note gates to a short chug and cannot ring; the ring IS "
        "this section's platform for the sitar. But do NOT let the chords run edge-to-edge: "
        "leave a GAP (a true rest of a beat or so) between the sustained rings — code drops "
        "palm-muted chugs into those gaps, so the section reads ring -> chug-chug -> ring, "
        "not one unbroken drone. No runs (sixteenths stay a small minority), no busy chugging "
        "of your own. Think Tool/Opeth weight under a melody: strike, let it decay, chug the "
        "gap, strike again — the foreground stays empty for the raga line."),
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


def _movement_figures(sounding: list[RiffNote],
                      ground: tuple[str, int]) -> list[tuple[tuple[str, int], ...]]:
    """The riff's melodic FIGURES — maximal runs of consecutive OFF-ground sounding notes,
    each as its (swara, oct) pitch sequence (the chug ground separates them). These are the
    'moves' whose RESTATEMENT (A A' A B) makes a riff memorable rather than wandering (A B C D)."""
    figures: list[tuple[tuple[str, int], ...]] = []
    cur: list[tuple[str, int]] = []
    for n in sounding:
        if (n.swara, n.oct) == ground:
            if cur:
                figures.append(tuple(cur))
                cur = []
        else:
            cur.append((n.swara, n.oct))
    if cur:
        figures.append(tuple(cur))
    return figures


def _is_color(note: RiffNote) -> bool:
    """Does this note's chord stack include a BRIGHT tone (one that seats above the
    octave as an add9/tenth — interval class 1-4 over the root)?"""
    return any((SWARAS[c] - SWARAS[note.swara]) % 12 in _COLOR_CLASSES
               for c in (note.chord or []))


def _rings(note: RiffNote) -> bool:
    """Does the note actually SUSTAIN in the render? Written duration alone is not enough —
    the renderer gates a palm-muted note to a fixed ~70ms chug whatever its duration (the
    Malkauns render's 'pads' were long PM notes that played as sparse ticks), so a ring is
    an OPEN strike of at least a beat."""
    return note.dur >= _WEIGHT_DUR and note.technique != "palm_mute"


def _ring_share(sounding: list[RiffNote]) -> float:
    """Share of the sounding DURATION that actually rings (open notes >= 1 beat)."""
    total = sum(n.dur for n in sounding)
    return sum(n.dur for n in sounding if _rings(n)) / total


def _weighted(note: RiffNote) -> bool:
    """Carries weight on the beat: a chord stack, or a note that genuinely rings — a naked
    palm-muted 'held' note is a thin tick, not weight."""
    return bool(note.chord) or _rings(note)


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
    chug = sum(1 for n in sounding if n.technique == "palm_mute")
    if chug < _CHUG_MIN_SHARE_DRIVE * len(sounding):
        viol.append(f"only {chug / len(sounding):.0%} of the notes are palm-muted CHUGS "
                    f"(need >= {_CHUG_MIN_SHARE_DRIVE:.0%}) — MARK the low ground strokes "
                    f"technique 'palm_mute' so they punch as muted chugs; an unmuted ground "
                    f"note is not a chug")
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
    ring = _ring_share(sounding)
    if ring < _RING_SHARE_MIN_DRIVE:
        viol.append(f"only {ring:.0%} of the sounding time RINGS open (need >= "
                    f"{_RING_SHARE_MIN_DRIVE:.0%}) — a riff breathes attack-then-resonance; "
                    f"between the chug runs strike at least one OPEN chord of a beat or more "
                    f"and let it sustain (a palm-muted note gates short and can never ring)")
    colors = sum(1 for n in sounding if _is_color(n))
    if colors > _COLOR_MAX:
        viol.append(f"{colors} bright colour stacks (add9/tenth seats) in one cycle — that is "
                    f"what makes the riff sound light and happy; keep at most {_COLOR_MAX} and "
                    f"make the rest power weight (the root's own swara, or P)")
    ground = Counter((n.swara, n.oct) for n in sounding).most_common(1)[0][0]
    figures = _movement_figures(sounding, ground)
    if len(figures) >= _HOOK_MIN_FIGURES and len(set(figures)) == len(figures):
        viol.append("the riff introduces a NEW figure every time (A B C D) — build it around "
                    "ONE hook: state a short 2-4 note cell and RESTATE it (A A' A B), repeating "
                    "or answering that figure instead of always moving on, so the riff is "
                    "memorable after two hearings")
    if len(sounding) >= _RHYTHM_MIN_NOTES:
        dur_counts = Counter(round(n.dur, 4) for n in sounding)
        if dur_counts.most_common(1)[0][1] > _RHYTHM_UNIFORM_MAX * len(sounding):
            viol.append("almost every note is the same length (straight 8ths) — VARY the note "
                        "values against the chug: a 16th burst, a dotted or held accent, a "
                        "triplet, a rest, so the riff has rhythmic contrast")
    return viol


def _pads_violations(notes: list[RiffNote], sounding: list[RiffNote],
                     cycle_beats: float) -> list[str]:
    viol: list[str] = []
    ring = _ring_share(sounding)
    if ring < _RING_SHARE_MIN:
        viol.append(f"only {ring:.0%} of the sounding time rings — an OPEN strike of >= "
                    f"{_WEIGHT_DUR:g} beat rings; a palm-muted note gates to a short chug and "
                    f"can NEVER ring, whatever its written duration. Pads SUSTAIN: hold wide "
                    f"open chords and let them bloom while the sitar moves")
    if not any(_rings(n) and n.dur >= _RING_LONG for n in sounding):
        viol.append(f"no OPEN chord is held {_RING_LONG:g}+ beats — a pad section needs at "
                    f"least one long ringing power chord (not palm-muted)")
    naked = [n for n in sounding if n.dur >= _RING_LONG and not n.chord]
    if naked:
        viol.append("a long held note carries no chord stack — give every 2+ beat ring "
                    "power-chord weight (the root's own swara, or P) so it blooms, not thins")
    rest_beats = sum(n.dur for n in notes if n.rest)
    if rest_beats < _PADS_REST_MIN * cycle_beats:
        viol.append(f"the rings run back-to-back with no space ({rest_beats:g} of "
                    f"{cycle_beats:g} beats silent) — leave GAPS between the sustained chords "
                    f"(>= {_PADS_REST_MIN:.0%} of the cycle as rests); code fills them with "
                    f"palm-muted chugs, so the section reads ring -> chug -> ring")
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


def open_the_rings(pattern: RiffPattern, mode: RiffMode) -> RiffPattern:
    """Deterministic texture repair — the GUARANTEE behind the ring budgets: strip
    `palm_mute` from the longest chorded notes (longest first, chorded preferred) until the
    mode's open-ring share is met, so a model that palm-mutes everything (the live Malkauns
    failure: both takes 0% open ring, best-of-N played the mute wall) still renders with
    sustained chords. Articulation-level surgery only — pitches, rhythm and order untouched
    (same license as the meend density guard); notes shorter than a beat stay chugs. Pure;
    a no-op when the budget is already met or the mode has no ring budget (STABS)."""
    target = {RiffMode.DRIVE: _RING_SHARE_MIN_DRIVE, RiffMode.PADS: _RING_SHARE_MIN}.get(mode)
    if target is None:
        return pattern
    notes = list(pattern.notes)
    sounding_idx = [i for i, n in enumerate(notes) if not n.rest]
    total = sum(notes[i].dur for i in sounding_idx)
    if total <= 0:
        return pattern
    ring = sum(notes[i].dur for i in sounding_idx if _rings(notes[i]))
    candidates = sorted((i for i in sounding_idx
                         if notes[i].technique == "palm_mute" and notes[i].dur >= _WEIGHT_DUR),
                        key=lambda i: (bool(notes[i].chord), notes[i].dur), reverse=True)
    for i in candidates:
        if ring >= target * total:
            break
        notes[i] = notes[i].model_copy(update={"technique": None})
        ring += notes[i].dur
    if notes == list(pattern.notes):
        return pattern
    return pattern.model_copy(update={"notes": notes})


def _chug_the_ground(pattern: RiffPattern) -> RiffPattern:
    """Guarantee DRIVE's chug floor: MARK short, unchorded ground-pitch notes `palm_mute`
    (a chug) until `_CHUG_MIN_SHARE_DRIVE` is met — the deterministic backstop behind the
    chug budget (Sujit: chugs were too sparse). Articulation-only surgery (pitches, rhythm,
    order untouched), disjoint from `open_the_rings` (which UN-mutes long chorded notes to
    ring), so the two guarantees never fight. Pure; a no-op when the floor is already met."""
    notes = list(pattern.notes)
    sounding = [i for i, n in enumerate(notes) if not n.rest]
    if not sounding:
        return pattern
    ground = Counter((notes[i].swara, notes[i].oct) for i in sounding).most_common(1)[0][0]
    chug = sum(1 for i in sounding if notes[i].technique == "palm_mute")
    need = _CHUG_MIN_SHARE_DRIVE * len(sounding)
    for i in sounding:
        if chug >= need:
            break
        n = notes[i]
        if ((n.swara, n.oct) == ground and n.technique is None
                and not n.chord and n.dur < _WEIGHT_DUR):
            notes[i] = n.model_copy(update={"technique": "palm_mute"})
            chug += 1
    if notes == list(pattern.notes):
        return pattern
    return pattern.model_copy(update={"notes": notes})


def _chug_run(swara: str, octave: int, gap: float) -> list[RiffNote]:
    """A gap-filling run of palm-muted ground chugs summing EXACTLY to `gap` beats: chugs at
    `_CHUG_SUBDIV`, leaving `_CHUG_FILL_BREATH` of silence before the next ring when the gap
    is long enough for one. Pure."""
    breath = _CHUG_FILL_BREATH if gap - _CHUG_FILL_BREATH >= _CHUG_SUBDIV else 0.0
    play = gap - breath
    run: list[RiffNote] = []
    t = 0.0
    while t + _CHUG_SUBDIV <= play + 1e-9:
        run.append(RiffNote(swara=swara, oct=octave, dur=_CHUG_SUBDIV, vel=_CHUG_VEL,
                            technique="palm_mute"))
        t += _CHUG_SUBDIV
    rem = round(gap - t, 4)
    if rem > 1e-9:
        run.append(RiffNote(swara=swara, oct=octave, dur=rem, rest=True))
    return run


def _chug_fill_pads(pattern: RiffPattern) -> RiffPattern:
    """Fill the SPACE between PADS' sustained rings with palm-muted ground chugs (Sujit: add
    chugs between the long sustained chords). Every rest >= `_CHUG_FILL_MIN_GAP` becomes a
    chug run on the cycle's ground pitch (its most common sounding pitch), leaving a breath
    before the next ring — so the section reads ring -> chug-chug -> ring. Deterministic and
    applied AFTER verification, so it never fights the ring budget (rests are not sounding
    time). Pure; a no-op with no fillable gap."""
    sounding = _sounding(pattern.notes)
    if not sounding:
        return pattern
    ground_sw, ground_oct = Counter((n.swara, n.oct) for n in sounding).most_common(1)[0][0]
    out: list[RiffNote] = []
    changed = False
    for n in pattern.notes:
        if n.rest and n.dur >= _CHUG_FILL_MIN_GAP:
            out.extend(_chug_run(ground_sw, ground_oct, n.dur))
            changed = True
        else:
            out.append(n)
    return pattern.model_copy(update={"notes": out}) if changed else pattern


def _finalize_texture(pattern: RiffPattern, mode: RiffMode) -> RiffPattern:
    """Apply the deterministic texture GUARANTEES to a finished cycle: open enough rings
    (`open_the_rings`), then — per mode — guarantee DRIVE's chug floor or drop PADS'
    between-ring chugs. Pure; each step is a no-op when its budget is already met / off-mode."""
    pattern = open_the_rings(pattern, mode)
    if mode is RiffMode.DRIVE:
        return _chug_the_ground(pattern)
    if mode is RiffMode.PADS:
        return _chug_fill_pads(pattern)
    return pattern


def verified_riff(gen: Callable[[Optional[list[str]]], RiffPattern], section: Section,
                  cycle_beats: float) -> RiffPattern:
    """Generate a VERIFIED riff cycle: call `gen(feedback)` and re-roll a cycle that
    misses its mode's budgets up to `RIFF_REPAIR_TRIES` times, feeding back the EXACT
    violations (a targeted re-roll, not a blind one). Bounded, best-of-N (fewest
    violations) when none come back clean — a weak riff plays; a live run never dies on
    taste. Every returned cycle (clean or best-of-N) passes through `_finalize_texture`,
    the deterministic guarantees: enough open ring, DRIVE's palm-mute chug floor, and PADS'
    between-ring chugs — so those textures are guarantees, not hopes. Pure control flow:
    `gen` is injected, so this tests with no LLM."""
    mode = riff_mode_for(section)
    best: Optional[RiffPattern] = None
    best_viol: Optional[list[str]] = None
    feedback: Optional[list[str]] = None
    for _ in range(RIFF_REPAIR_TRIES + 1):
        pattern = gen(feedback)
        viol = verify_riff(pattern, mode=mode, cycle_beats=cycle_beats)
        if not viol:
            return _finalize_texture(pattern, mode)
        feedback = viol                       # the re-roll sees EXACTLY what failed
        if best_viol is None or len(viol) < len(best_viol):
            best, best_viol = pattern, viol
    assert best is not None                   # the loop ran at least once
    return _finalize_texture(best, mode)
