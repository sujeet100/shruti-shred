"""
The gat verifier — TIME-legality for the gat's STRUCTURED CELLS.

The talk point this makes concrete: **legality has two grammars — pitch AND time.** Ustad's
`validate_composition` owns PITCH legality (is every swara in the raga?). This is the TIME
counterpart for the gat's structured cells: is the mukhada a real, loopable, landing hook; does
the intro/alap establish and resolve to Sa with real silence; does the manjha arrive at the sam
and lead back into the head; does a taan fill move in sixteenths and resolve into the head?
Those are checkable structural invariants the composer's pitch guardrail simply cannot see.

Why it exists at all: the aesthetic critics (Rasik/Producer) run LATE — after the whole piece is
assembled — so there would be no repair for a bad cell; a weak hook (or a wandering alap/manjha)
poisons the entire song and the loop only notices at the end. These verifiers run EARLY, right
after each cell is generated, so a weak cell can be RE-ROLLED before it is placed (see
`crew/lead.py` `_generate_verified_cell`). Deterministic and pure — no LLM, free, unit-tested.

The design lesson behind the newer checks (Sujit's live feedback + a converging Gemini review):
an LLM can't invent SILENCE or CYCLICAL TENSION from "be spacious / develop the head" — the feel
must be translated into rigid, checkable constraints and enforced with the verify + feedback
re-roll pattern, not re-prompted vaguely.

Scope discipline: these check TIME/structure, which is CHECKABLE — never gat/taan taste (that
stays with Rasik/Producer). They never judge whether a cell is *good*, only whether it satisfies
the structural grammar of its role.

HARD vs CRAFT (2026-10-11, DESIGN.md "THE REDESIGN"). The "rigid constraints" lesson above held
for a weaker model; the same experiment that showed our riff verifier rejecting the best riff
showed these rules acting as ceilings. Each `check_*` now returns a `CellChecks`: HARD faults
(the cell does not fill its window or land its seam, breaks the raga's direction/nyas grammar,
walks a taan up or down the bare scale, asks a held chikari, misses the riff_first quote) drive
the bounded re-roll; CRAFT notes (pulse, rests and silence shares, phrase counts, register arcs,
motif discipline, density, ornament density, pakad statement) are REPORTED on the cell's event
for the judges. `verify_*` returns the HARD list only.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Final

from crew.anchor import RiffAccent, render_accents
from crew.contracts import (HEAD_STAGES, TAAN_PHRASE_ROLES, TAAN_SUBDIVISIONS, HeadIdea, LeadNote,
                            LeadPhrase, TaanPhrase)
from gats import BOL_WORDS, GAT_FRAMES, STROKE_HOLD, bol_onsets, is_compound, stroke_line_attacks
from chalan import ang_matches, octave_span, scalar_runs
from raga import NYAS, REGISTER, RAGAS, SWARAS, direction_violations, nyas_problem, resting_swaras

@dataclass(frozen=True)
class CellChecks:
    """A cell's verdict, split the way the riff verifier is (DESIGN.md "THE REDESIGN").

    `hard` = what makes the cell BROKEN — it does not fill its window or land its seam, it breaks
    the raga's grammar (direction, a sourced nyas), it asks an articulation to do what it cannot
    (a held chikari), or it misses the riff_first quote it owes. Only these drive a paid re-roll.
    `craft` = the taste recipe (pulse, rests, phrase counts, register arcs, motif discipline,
    density...) — calibrated against an older model's failures, so REPORTED on the cell's event
    for the judges, never re-rolled."""
    hard: tuple[str, ...] = ()
    craft: tuple[str, ...] = ()

    def __add__(self, other: CellChecks) -> CellChecks:
        return CellChecks(self.hard + other.hard, self.craft + other.craft)


def hard_only(violations: list[str]) -> CellChecks:
    """Lift a plain violation list (a check that is HARD by nature) into a `CellChecks`."""
    return CellChecks(hard=tuple(violations))


def _cadence_bucket(swara: str, raga: str, hard: list[str], craft: list[str]) -> list[str]:
    """Where a "should end on Sa" complaint belongs: HARD when the final note is not one of the
    raga's sourced resting notes (grammar), CRAFT when it rests legally but not on Sa (taste)."""
    return hard if swara not in _resting_swaras(raga) else craft


# A mukhada should fill about ONE avartan so it loops as a cycle. Too short == a fragment; well
# over the cycle == a phrase code has to truncate (cutting off its own cadence). Bounds are
# fractions of the avartan, deliberately loose — this flags the gross misses, not tight musical taste.
_FILL_MIN: Final = 0.6
_FILL_MAX: Final = 1.6
# Calling a head "flat" needs enough notes to judge — two notes of equal length is not a pattern.
_MIN_NOTES_FLAT: Final = 3
# The head's RHYTHMIC MIX (Sujit, 2026-07-16: a good mukhada mixes 8ths and quarters with half/
# full notes — the long note IS the nyas/rest point, the 8ths are the movement between them; the
# render's quarters-and-halves head read as a metronome): at least this many distinct note
# values, including one long resting value and one short moving value.
# RHYTHM — REVERSED TWICE, now the composer's (Sujit, 2026-10-12: "let the LLM decide matra
# density ... saying 1 note per matra will oversteer it"). The steady-pulse floor below was
# removed: with the prompt's "ONE note value / one swara per matra is idiomatic", 30 of 31
# generated heads opened on four one-beat notes and the Darbari gat crawled at one note per
# second. Only the held nyas (`_MUKHADA_LONG`) remains. The history, for the record:
# SINGABILITY, and the rule that was BACKWARDS (Sujit, 2026-09-14, with the gats he is
# learning and Vilayat Khan's notated Bageshree gat). A gat head's memorability comes from
# rhythmic REGULARITY, not variety: `m m g g R R S S | n D n n S g m —` moves one swara per
# matra with paired strokes (the mizrab's "dara") as its only subdivision — two note values,
# one covering 95% of the notes. You could clap that rhythm on a single pitch and still
# recognise the gat. The generated head used FIVE values with the commonest covering 31%,
# which is three rhythmic languages inside ten beats and nothing for the ear to hold. The old
# rule demanded >= 3 distinct values and rejected "a head of even values" as a metronome —
# precisely the shape a real gat has.
# 0.35 rather than something tighter: this is a floor for a GROSS miss, not a target. The
# generated head that prompted the rule sat at 31%; a real gat sits near 95%; and a head that
# must also carry the bol frame's dir doublings (two fast notes in specific matras) lands
# around 36-40%, so a tighter floor would reject heads that are doing everything else right.
_MUKHADA_LONG: Final = 2.0          # ...and it still RESTS somewhere: one half-note+ nyas
# A riff_first head must sound the riff's swara on at least this share of its accented beats.
_QUOTE_SHARE: Final = 0.5

# Intro/alap — the diagnosed failure: random wandering that never resolves to Sa, with no space.
# Structure research-verified (2026-07-15, the AOCHAR — the short pre-gat alap; sources in
# DESIGN.md), REVISED to the alap-VISTAR shape (Sujit's ear, 2026-07-16): the phrases hold
# TENSION — they explore the motif up OR down and do NOT come home each time; instead the
# MANDRA Sa is PLUCKED between phrases as a drone anchor (the guitarist's low open string /
# the sitar's jod string), and the ONE real resolution — the long held Sa that finally feels
# like home — is saved for the close, after which the gat's mukhada brings the tala in.
_INTRO_SA_SHARE: Final = 0.20       # Sa (the low plucks + the close) still anchors by duration
_INTRO_MIN_SA_RETURNS: Final = 3    # ...and Sa is re-sounded at least this many separate times
_INTRO_HELD_SA: Final = 2.0         # the closing Sa is HELD at least this long (beats)
_INTRO_MIN_RESTS: Final = 2         # at least this many true rests...
_INTRO_MIN_REST_BEATS: Final = 1.0  # ...each at least this long
# A COUNT became a TARGET. Measured on the 2026-07-20 renders, every intro carried exactly
# three gaps — the floor, treated as the goal — and in two of them the silence totalled 6 of
# 64 beats (9%): an alap that is nearly wall-to-wall sound. Silence is a PROPORTION of an
# alap, not a quota of rests, so the share is what is checked.
_INTRO_REST_SHARE: Final = 0.18     # ...and silence is this much of the alap overall
# One note must not BE the alap. The same renders closed on single notes of 17.5, 21 and 11.5
# beats — 27%, 33% and 18% of the whole intro in one hold, which is a model running out of
# phrase, not a resolution. (The old brief asked for "the longest of the intro" with no cap,
# over a window it was told to fill.)
_INTRO_MAX_NOTE_SHARE: Final = 0.15
_INTRO_MAX_NOTE_BEATS: Final = 4.0  # ...but never below this, so a SHORT alap can still hold
                                    # its closing Sa (which `_INTRO_HELD_SA` requires) — a
                                    # share alone would outlaw the resolution it demands
_INTRO_OPEN_MAX_STEPS: Final = 2    # the opening note sits within this many ladder steps of Sa
_INTRO_PLUCK_MAX_OCT: Final = -1    # the between-phrase Sa pluck sits in the mandra (or lower)
# The alap's MICRO-structure (Sujit's live note + GPT's alap spec, 2026-07-15): the diagnosed
# failure was "Sa played repeatedly, continuously" — the model met the Sa-share/returns checks by
# CLUSTERING Sa instead of composing phrase -> Sa -> silence. So the sentence structure is now
# checkable: the alap is several SHORT INDEPENDENT phrases (rest-separated), each exploring then
# landing on Sa, and Sa is a LANDING between phrases — never a sustained/repeated wall.
_INTRO_MIN_PHRASES: Final = 3       # at least this many rest-separated phrases (musical sentences)...
_INTRO_MIN_PHRASES_SHORT: Final = 2  # ...but a SHORT window holds two: asking three of a ~10-beat
_INTRO_ROOMY_WINDOW: Final = 16.0    # alap is what crammed a taan into it (2026-10-11 render)
# The alap's RHYTHM (2026-10-11 render, Sujit: "messed up in spacing and rhythm"): durations of
# 0.4 and 0.12 beats knocked every later note off the grid the arpeggio keeps, compound strokes split
# notes into 32nds, and quick steps made most of the line. Quick steps stay legal — the brief asks
# for rhythmic contrast — but as a minority, on the grid, one stroke per note.
_INTRO_GRID: Final = 0.25            # every alap duration is a whole number of sixteenths
_INTRO_QUICK: Final = 0.5            # a sounding note shorter than this is a QUICK step...
_INTRO_QUICK_SHARE_MAX: Final = 0.35 # ...and quick steps are at most this share of the notes
_INTRO_COMPOUND_BOLS: Final = frozenset(w for w in BOL_WORDS if is_compound(w))  # gat figures
_INTRO_MAX_SA_RUN: Final = 3.0      # no mid-alap run of consecutive Sa longer than this (the held close is exempt)
# A CHIKARI IS A STROKE. The chikari strings are struck to fill an empty matra — played in
# time like any other note, then gone (Sujit, 2026-09-14). Written long it stops being
# punctuation and becomes a second drone on top of the tanpura and the jod; measured on the
# 2026-07-20 renders, each intro held exactly ONE chikari, written 1.5-3.0 beats, so the
# device that should supply the alap's rhythmic punctuation was instead another sustain.
_CHIKARI_MAX_DUR: Final = 0.5
# ONE MOTIF, PROGRESSIVELY REVEALED (Sujit's steer + a converging GPT note, 2026-07-16): the
# diagnosed failure of the first Malkauns render — the prompt's badhat rules were PROSE and the
# model ignored them (taar Sa four seconds in; episodic phrases quoting different pakad material).
# So the aochar's remembered-because-one-idea shape is now checkable: the declared `seed` IS the
# intro's recurring motif (from the raga's pakad/chalan since 2026-10-19; the head is prepared, not quoted),
# every phrase but the final settle carries its opening, the full motif is stated somewhere, the
# opening phrase stays a narrow fragment, and the intro's widest reach arrives past the midpoint.
_INTRO_MOTIF_MIN: Final = 2         # the declared motif is at least this many swaras...
_INTRO_MOTIF_MAX: Final = 5         # ...and at most this many (a kernel, not a whole line)
_INTRO_ANCHOR_LEN: Final = 2        # each phrase carries at least this opening fragment of the motif
_INTRO_OPEN_SPAN: Final = 7         # semitones: the FIRST phrase stays a narrow fragment around home
_INTRO_PEAK_MIN_POS: Final = 0.5    # the intro's highest note arrives past this fraction (badhat)
_INTRO_HEAD_QUOTE: Final = 4        # the head's opening this many swaras, heard in the alap, is a QUOTE
# ALAP, THEN JOD (2026-10-19, Sujit's "ours is more of an intro than an alap" + ALAP_RESEARCH.md).
# The day's jod pulse covered the whole alap: every phrase on a vibhag, nothing held past two
# beats — at a doom 120 bpm two beats is one second, and the measured Darbari alap played 30 notes
# in ~26 s with only 39% of its sound on notes held a second or longer. Every source describes an
# alap as unmetred and mostly held (Clarke, *Rags Around the Clock* ch. 3; Deepak Raja). So the
# pulse moves to a JOD at the end (the order of a sitar performance) and the alap part is measured
# in SECONDS. One strong source, so these are CRAFT notes, never rejections.
_ALAP_HELD_S: Final = 1.0            # a note held this many seconds or more is a HELD note...
_ALAP_HELD_SHARE: Final = 0.5        # ...and held notes carry at least this share of the alap's sound
_ALAP_MAX_NEW_SWARAS: Final = 2      # a phrase opens at most this many swaras beyond the ground so far
_ALAP_MAX_NOTE_S: Final = 4.0        # a hold of up to this many seconds is never "one note being the alap"
# ORNAMENT DENSITY — ornaments speak by CONTRAST against plain notes. A meend is an ornament,
# and the render anchors it on its TARGET, so a meend note is HEARD at the target, not the
# written swara: the 2026-07-16 render put a meend on ~100% of alap notes (all toward Sa) and
# the exposition collapsed onto one repeated note; the 2026-10-11 alap again glided on nearly
# every note and flicked a murki on every one. Measured over the MELODY notes of any lead cell
# (chikari and the Sa pluck cannot carry either). CRAFT, never hard: how much to ornament is
# the player's taste, and the audible-line checks already catch the collapse it causes.
#   * meend <= 40%: a glide marks an arrival or a nyas approach — one or two in a 4-6 note
#     phrase is the idiom; past ~2 in 5 the glide is the default articulation, not an event;
#   * murki/khatka <= 25%: a flick is an ACCENT on an important note (light-classical when it
#     is everywhere) — at most about one note in four, so the flicked notes still stand out.
_MEEND_MAX_SHARE: Final = 0.4
_FLICK_MAX_SHARE: Final = 0.25
_ORNAMENT_MIN_NOTES: Final = 5      # below this many melody notes a share is noise, not a habit


def _real_meend(note: LeadNote) -> bool:
    """A meend that actually GLIDES — its target differs from the written pitch (the LLM
    sometimes stamps `meend_swara == swara`, a no-op the placement strips anyway)."""
    if note.rest or note.meend_swara is None:
        return False
    target_oct = note.meend_oct if note.meend_oct is not None else note.oct
    return (note.meend_swara, target_oct) != (note.swara, note.oct)


def _ornament_density_notes(notes: list[LeadNote], cell: str) -> list[str]:
    """CRAFT notes when a cell ornaments so many notes that ornament stops being an event
    (empty == the ornaments still stand out against plain notes). Pure."""
    melody = _melodic(notes)
    if len(melody) < _ORNAMENT_MIN_NOTES:
        return []
    notes_out: list[str] = []
    meends = sum(_real_meend(n) for n in melody)
    if meends > _MEEND_MAX_SHARE * len(melody):
        notes_out.append(
            f"{meends} of {len(melody)} notes in the {cell} carry a meend — ornaments speak by "
            f"CONTRAST, and a meend note is HEARD at its target, so over-meending collapses the "
            f"line onto the targets. Keep meend to at most {_MEEND_MAX_SHARE:.0%} of the notes "
            f"(a glide INTO an arrival or a nyas) and let the rest sound their own swara plainly")
    flicks = sum(n.ornament is not None for n in melody)
    if flicks > _FLICK_MAX_SHARE * len(melody):
        notes_out.append(
            f"{flicks} of {len(melody)} notes in the {cell} carry a murki/khatka — ornaments "
            f"speak by CONTRAST: a flick on every note is a texture, not an accent. Keep them to "
            f"at most {_FLICK_MAX_SHARE:.0%} of the notes, on the ones the phrase leans on")
    return notes_out

# Manjha / taan-fill seam — "fluid" made checkable: the cell's last note sits within this many
# scale-degrees of the mukhada's first swara, so the head re-enters as a step, not a leap.
_SEAM_MAX_STEPS: Final = 2

# Bol frame (2026-07-20 gat research — see src/gats.py for the sourced facts): the stroke
# pattern is the gat's rhythmic IDENTITY, checkable without dictating melody. Three tolerant
# rules: the sam is struck STRONG (da), the dir doublings are present (position-pinned to the
# verified Masitkhani grid on a 16-matra cycle; density-only for the flexible Razakhani), and
# most notes carry an explicit stroke at all. Coverage is deliberately lenient (a hold is one
# stroke): the goal is an identity, not a transcription exam.
_BOL_MIN_COVERAGE: Final = 0.5     # at least this share of sounding notes carry a bol
_FRAME_MIN_DOUBLES: Final = 2      # (razakhani) at least this many dir double-attack matras
_LINE_MIN_MATCH: Final = 0.75      # below this share of matched matras, the notes left the planned stroke line

# Amad (Parikh's FOURTH line): the composed descent that "brings you down to the point where
# the composition started". Checkable: net descent, no re-peak (a descent may eddy, never
# re-climb past its opening), lands at/below home, and seams into the returning head.
_AMAD_RISE_MAX: Final = 2          # semitones the line may eddy above its opening note

# Antara — the second movement of the SAME gat, whose arc is checkable: opens in the middle
# octave QUOTING the head, climbs, peaks ONCE in the taar past the midpoint, then descends to
# rest on madhya Sa (the diagnosed failure: "another melody" of random high notes).
_ANTARA_QUOTE_LEN: Final = 4        # how many of the head's opening swaras the antara must quote
_QUOTE_MAX_GAP: Final = 2           # fuzzy quote: up to this many interleaved notes between quote tones
_PEAK_MIN_POS: Final = 0.4          # the highest note arrives past this fraction of the phrase

# Taan (the developed solo/climax) — "fast notes" is not a taan; the checkable core of a
# concert taan: it grows from the MOTIF, climbs to ONE late peak, resolves to a resting swara.
_TAAN_QUOTE_LEN: Final = 4          # how much of the motif the taan must audibly grow from
_TAAN_MIN_DURATIONS: Final = 3      # (the antara's) distinct note values — not one even wall
# THE TAAN FLOWS (Sujit + the review of `excerpt_233435_taan_revised`, 2026-10-13): the old rule
# here was "burst and space" — a sixteenth burst, then a held nyas or a rest, then a bigger burst —
# and the model wrote exactly that: 29 eighths, 18 sixteenths and ten 1-2 beat holds scattered
# through the run, half the taan's time on notes of a beat or more. It read as disconnected
# phrases. A taan runs at ONE pulse per phrase and launches STRAIGHT at chaugun (4 notes a matra —
# Sujit, 2026-10-13: no dugun warm-up first), may quicken to chhagun at a phrase boundary, never
# slows, builds into ONE late climax and keeps its momentum through the cadence into the sam. The phrase plan (`TaanPhrase`) states
# that structure; the notes are held to it. Longer notes are allowed where they are a choice:
# the LAST note of a phrase (an arrival at its boundary), and a gamak note (re-struck by code,
# so it keeps moving). Never a rest — the run does not stop.
_TAAN_ROLES: Final = TAAN_PHRASE_ROLES
_TAAN_PULSES: Final = TAAN_SUBDIVISIONS
_TAAN_PHRASE_END_MAX: Final = 1.0   # a phrase's final note may ring up to a matra
_TAAN_GAMAK_MAX: Final = 1.0        # a gamak note (re-struck every ~quarter second) up to a matra
_TAAN_FINAL_INTO_SAM_MAX: Final = 0.5  # the note that runs into the returning head stays in flight
# THE TAAN'S BASE PULSE FOLLOWS THE TEMPO (Sujit, 2026-10-20: "chaugun at 64 bpm sounds like dugun"; 8 a
# beat at 64 bpm sounded right, and chaugun at 120 always had). The run aims at ~8 notes a second:
# chaugun (4 a matra) at 120 bpm, chhagun (6) around 80-90, athgun (8) at a slow 64. It launches at that
# pulse from the first note (no warm-up — Sujit, 2026-10-13) and may quicken one step near the climax.
TAAN_NOTE_RATE: Final = 8.0        # notes per second the taan's base pulse aims at
_TAAN_BASE_PULSES: Final = (4, 6, 8)


def taan_pulse(bpm: float) -> int:
    """The taan's base pulse at `bpm`, in notes per matra: the one of chaugun / chhagun / athgun whose
    note rate sits nearest `TAAN_NOTE_RATE`. Pure."""
    return min(_TAAN_BASE_PULSES, key=lambda sub: abs(sub * bpm / 60.0 - TAAN_NOTE_RATE))


_TAAN_CLIMAX_FROM: Final = 0.5      # the climax phrase starts in the later half...
_TAAN_PEAK_FROM: Final = 0.6        # ...and its top note sounds past this share of the taan (the
                                    # first live take peaked at 52%, then cascaded 15 beats down)
_TAAN_AFTER_CLIMAX_MAX: Final = 0.25  # ...and what follows it is at most a quarter (no long descent)
_TAAN_LEAP_MAX: Final = 7           # semitones inside a phrase — wider is a jump, not a run
_TAAN_EPS: Final = 1e-3
# END-ANCHORED cells (manjha / antara / taan — their cadence IS the last note) must fill their
# window without overrunning it: placement TRUNCATES at the window edge, so any overrun cuts off
# the very cadence the verifier approved. (Caught live: an antara passed "ends on Sa", overran
# its window, and placement clipped the final Sa — the piece heard it end on Re.) The ceiling is
# therefore essentially 1.0 (a hair of rounding slack); the floor keeps the cell from dying early.
_CELL_FILL_MIN: Final = 0.85
_CELL_FILL_MAX: Final = 1.02
# A taan fill is a precise splice into a cut avartan: tighter floor, same hard ceiling.
_TAAN_FILL_MIN: Final = 0.9
# A raga is a grammar of MOVEMENT, not a permitted pitch set — Bageshree shares its scale
# with Bhimpalasi, so a line can be perfectly legal and stop sounding like the raga the moment
# it walks the ladder. Measured on the 2026-09-14 render: 63% of moves were single steps, the
# longest unbroken stepwise run was NINE notes, and only 35% of moves turned. The taan brief
# already asks for koot (vakra) as its default style and calls a straight run "ONE dash, never
# the whole taan" — nothing measured it, so nothing happened. These budgets are what make that
# instruction enforceable. Deliberately loose: one sapat dash is idiomatic, a ladder is not.
_TAAN_SCALAR_MAX: Final = 6         # notes in one unbroken stepwise direction (one dash's worth)
_TAAN_NOTE_MAX: Final = 0.25        # a short taan moves in sixteenths...
_TAAN_LANDING_MAX: Final = 1.0      # ...but may land on one longer resolving note


def _resting_swaras(raga: str) -> set[str]:
    """The swaras a cell may cadence onto — the raga's researched NYAS set (`raga.NYAS`).
    Landing here is how the head resolves to the sam and loops cleanly."""
    return resting_swaras(raga)


# NYAS ENDINGS (2026-10-11). A phrase that comes to REST — its last melody note followed by a
# real silence — must rest on one of the raga's nyas swaras, honouring the direction-only rests
# (Bhairav's re and Bageshree's ga rest only coming down). What is NOT checked, deliberately:
# the note on the sam (a Bageshree bandish Sujit is learning lands its sam on Re, not a nyas)
# and a long hold mid-phrase (Parrikar: elongation is not resting — Darbari's andolit ga).
_NYAS_REST_BEATS: Final = 1.0       # a silence this long ends a phrase; shorter is a breath inside it
_NYAS_MAX_REPORTED: Final = 3


def _resting_phrase_endings(notes: list[LeadNote]) -> list[tuple[LeadNote, LeadNote | None]]:
    """(ending note, the melody note before it) for every phrase followed by a real silence.
    Punctuation (chikari, the mandra-Sa pluck) never ends a phrase; the cell's final note is
    not followed by silence here, so the cell's own cadence rules own it."""
    out: list[tuple[LeadNote, LeadNote | None]] = []
    melody: list[LeadNote] = []
    for n in notes:
        if n.rest:
            if n.dur >= _NYAS_REST_BEATS and melody:
                out.append((melody[-1], melody[-2] if len(melody) > 1 else None))
            continue
        if n.bol != "chikari" and not _is_sa_pluck(n):
            melody.append(n)
    return out


def nyas_violations(notes: list[LeadNote], raga: str) -> list[str]:
    """Phrase endings that rest somewhere this raga does not rest. Pure."""
    found: list[str] = []
    for end, before in _resting_phrase_endings(notes):
        from_below = (None if before is None or _landing_pitch(before) == _landing_pitch(end)
                      else _landing_pitch(before) < _landing_pitch(end))
        problem = nyas_problem(raga, _landing_swara(end), from_below)
        if problem:
            found.append(problem)
    if not found:
        return []
    shown = "; ".join(list(dict.fromkeys(found))[:_NYAS_MAX_REPORTED])
    return [f"{len(found)} phrase(s) come to rest on the wrong swara before a silence — {shown}. "
            f"End each phrase that pauses on a nyas of the raga"]


def _sounding(notes: list[LeadNote]) -> list[LeadNote]:
    return [n for n in notes if not n.rest]


def _landing_swara(note: LeadNote) -> str:
    """The swara a note actually SOUNDS. Two renderer facts the written swara hides: a
    chikari stroke rings taar Sa whatever it wrote, and a MEEND is anchored on its TARGET —
    the written swara is only the brief pre-bend flick, the target is what sustains. Every
    pitch check reads THIS. (The 2026-07-16 Malkauns alap was WRITTEN as perfect pakad
    phrases, but every note meended to Sa — the ear got one repeated high note while the
    written line passed every check. Verify what SOUNDS, not what is written.)"""
    if note.bol == "chikari":
        return "S"
    return note.meend_swara if note.meend_swara is not None else note.swara


def _landing_oct(note: LeadNote) -> int:
    """The octave a note actually sounds in — the meend target's frame when it glides
    across octaves (`meend_oct` None = the note's own octave). Chikari keeps the written
    octave here: it is punctuation, and letting it count as a taar reach would let a
    stray accent pass the register-arc checks."""
    if note.bol != "chikari" and note.meend_swara is not None and note.meend_oct is not None:
        return note.meend_oct
    return note.oct


def _landing_pitch(note: LeadNote) -> int:
    """The pitch a note actually sounds, in semitones relative to madhya Sa."""
    return _landing_oct(note) * 12 + SWARAS[_landing_swara(note)]


def _rhythmically_flat(sounding: list[LeadNote]) -> bool:
    """Every sounding note the same length — a run, not a phrase (needs >= 3 notes to judge)."""
    return len(sounding) >= _MIN_NOTES_FLAT and len({round(n.dur, 4) for n in sounding}) == 1


def _scale_steps_between(a: str, b: str, raga: str) -> int:
    """Fewest scale-degree steps between two swaras on the raga's ladder, octave-folded.
    A swara outside the raga (never expected past the legality guardrail) counts as far."""
    allowed = RAGAS[raga]["allowed"]
    if a not in allowed or b not in allowed:
        return len(allowed)
    d = abs(allowed.index(a) - allowed.index(b))
    return min(d, len(allowed) - d)


def _first_swara(cell: LeadPhrase) -> str | None:
    """The first SOUNDING swara of a cell (None for an all-rest cell)."""
    sounding = _sounding(cell.notes)
    return _landing_swara(sounding[0]) if sounding else None


def _seam_violation_to(last: LeadNote, target: str | None, raga: str, cell_name: str,
                       target_desc: str) -> str | None:
    """The shared RETURN-SEAM rule against an explicit target swara: the cell's last note must
    lead fluidly into it (within `_SEAM_MAX_STEPS` on the raga's ladder — same note or a
    stepwise pull), so the head re-enters as a resolution, not a jump-cut."""
    if target is None:
        return None                       # a degenerate head is the mukhada verifier's problem
    landing = _landing_swara(last)
    if _scale_steps_between(landing, target, raga) <= _SEAM_MAX_STEPS:
        return None
    return (f"the {cell_name} ends on {landing}, which does not lead into {target_desc} "
            f"({target}) — end on {target} itself or within a step or two of it "
            f"(a stepwise lead-in), so the head re-enters fluidly")


def _seam_violation(last: LeadNote, mukhada: LeadPhrase, raga: str, cell_name: str) -> str | None:
    """The return seam against the mukhada's FIRST swara — the head statement that follows."""
    return _seam_violation_to(last, _first_swara(mukhada), raga, cell_name,
                              "the mukhada's first swara")


def reentry_swara(mukhada: LeadPhrase, from_beat: float) -> str | None:
    """The first swara the head SOUNDS at or after `from_beat` of its avartan — the note the
    head's APPROACH re-enters on after a front-spliced taan fill (cumulative time over the
    cell's notes, rests included). Falls back to the head's first swara when nothing starts
    that late (a degenerate head)."""
    t = 0.0
    for n in mukhada.notes:
        if not n.rest and t >= from_beat - 1e-6:
            return _landing_swara(n)
        t += n.dur
    return _first_swara(mukhada)


def check_mukhada(cell: LeadPhrase, *, cycle_beats: float, raga: str) -> CellChecks:
    """Return the mukhada head's TIME-legality violations (empty == a clean hook). Pure.

    Four checks the pitch guardrail can't make, each targeting a diagnosed failure of the first
    live gat (the fourth from the 2026-07-20 gat research):
      * FILLS THE AVARTAN — the head's total duration is about one cycle, so looping it re-lands on
        the sam instead of repeating a fragment (or being truncated mid-cadence);
      * CADENCES TO A RESTING SWARA — the last sounding note is Sa, the vadi, or the samvadi, so the
        head resolves to the sam and the loop seam lands rather than restarts;
      * NOT RHYTHMICALLY FLAT — the durations vary (the diagnosed failure was a gat of even quarter
        notes; a hook needs a rhythmic shape).
    HARD (re-rolled): the fill, the resting cadence, the loop seam (a head ending on its opening
    note blurs the sam code loops it onto), the sourced nyas. CRAFT (reported): the pulse share
    and the long-note rest — taste tuned on an older model (see `CellChecks`).
    """
    notes = cell.notes
    sounding = _sounding(notes)
    if not sounding:
        return CellChecks(hard=("the mukhada has no sounding notes — it must state a melodic head",))

    hard: list[str] = []
    craft: list[str] = []
    # THE SAM NOTE IS NOT A SHORT LIST. This used to require Sa, the vadi or the samvadi, and
    # Sujit's own repertoire refutes it: Vilayat Khan's Yaman gat lands its sam on PA (neither
    # Sa nor Yaman's vadi G nor its samvadi N), a Bageshree bandish he is learning lands on
    # RE — a swara our own data marks descent-only — and another Bageshree gat lands on Ma.
    # Any list we write rejects real gats, so this is not a rule. What it protected (the sam
    # must carry a deliberate, structurally strong swara rather than a stray passing note)
    # lives in the brief and in the bol frame, which still requires the sam struck "da".
    resting = _resting_swaras(raga)
    total = sum(n.dur for n in notes)
    if total < _FILL_MIN * cycle_beats:
        hard.append(f"the mukhada fills only {total:g} of {cycle_beats:g} beats — a fragment, not a "
                    f"one-avartan head; fill about one full cycle so it loops on the sam")
    elif total > _FILL_MAX * cycle_beats:
        hard.append(f"the mukhada runs {total:g} beats, well over the {cycle_beats:g}-beat avartan — "
                    f"keep the head to about one cycle or it gets truncated mid-phrase")

    last = sounding[-1]
    landing = _landing_swara(last)   # a chikari sounds taar Sa (a resting note)
    if landing not in resting:
        hard.append(f"the mukhada ends on {last.swara}, not a resting swara "
                    f"({' '.join(sorted(resting))}) — cadence to the sam so the head lands and loops")

    durations = [round(n.dur, 4) for n in sounding]
    if not any(d >= _MUKHADA_LONG for d in durations):
        craft.append(f"the mukhada has no long note (>= {_MUKHADA_LONG:g} beats) — the head "
                    f"RESTS somewhere (a nyas on a half/full note) before it moves again")
    # The loop is judged on the MELODIC cadence: a chikari is a stroke struck after the phrase
    # has landed, so it neither hides nor supplies the return.
    melodic = _melodic(sounding)
    if melodic and len(melodic) > 1 and (
            (_landing_swara(melodic[-1]), _landing_oct(melodic[-1]))
            == (_landing_swara(melodic[0]), _landing_oct(melodic[0]))):
        hard.append(f"the head ends on the same note it opens with "
                    f"({_landing_swara(melodic[-1])}), "
                    f"so the two merge across the loop and the SAM DISAPPEARS — the returning "
                    f"cycle must be audible. Cadence to a different resting swara and let the "
                    f"opening note re-enter (…m g R S | m m g g…)")

    hard += nyas_violations(cell.notes, raga)
    craft += _ornament_density_notes(cell.notes, "mukhada")
    return CellChecks(tuple(hard), tuple(craft))


def verify_mukhada(cell: LeadPhrase, *, cycle_beats: float, raga: str) -> list[str]:
    """The mukhada's HARD faults only — what drives a re-roll. `check_mukhada` adds the
    reported craft notes."""
    return list(check_mukhada(cell, cycle_beats=cycle_beats, raga=raga).hard)


def _sounding_swara_at(notes: list[LeadNote], beat: float) -> str | None:
    """The swara the head SOUNDS at `beat` of its avartan (its landing swara), None in a rest."""
    t = 0.0
    for note in notes:
        if t <= beat < t + note.dur:
            return None if note.rest else _landing_swara(note)
        t += note.dur
    return None


def riff_quote_share(cell: LeadPhrase, accents: list[RiffAccent]) -> float:
    """The share of the riff's accented roots the head SOUNDS on their beats (1.0 with no accents)
    — the measure behind `verify_riff_quote`, reported for any anchor. Pure."""
    if not accents:
        return 1.0
    return sum(_sounding_swara_at(cell.notes, a.beat) == a.swara for a in accents) / len(accents)


def verify_riff_quote(cell: LeadPhrase, accents: list[RiffAccent]) -> list[str]:
    """Return the violation when a `riff_first` mukhada fails to QUOTE the riff (empty == it
    does). Pure.

    The head must sound the riff's swara on at least half of the riff's accented beats (the
    sam and talis where the riff plays). Half, not all: the sitar sings a melody over the
    riff's skeleton, and a head forced onto every accent would be the riff transcribed, not
    sung. An accent the head rests through counts as a miss — the listener hears no quote."""
    if not accents:
        return []
    quoted = sum(_sounding_swara_at(cell.notes, a.beat) == a.swara for a in accents)
    needed = ceil(len(accents) * _QUOTE_SHARE)
    if quoted >= needed:
        return []
    return [f"the piece is riff_first, but the mukhada quotes only {quoted} of the riff's "
            f"{len(accents)} accented roots ({render_accents(accents)}) — sound those swaras on "
            f"those beats (at least {needed}, the sam above all) so the head is heard as the "
            f"riff sung"]


def stroke_onsets(notes: list[LeadNote]) -> list[float]:
    """Every pluck's start, in matras from the cell's start: a note is one pluck, a compound bol
    as many as its stroke figure (`gats.bol_onsets` — the same timing the renderer plays)."""
    onsets: list[float] = []
    t = 0.0
    for n in notes:
        if not n.rest:
            figure = bol_onsets(n.bol, n.dur) if n.bol in BOL_WORDS else [(0.0, n.dur, "da")]
            onsets.extend(t + offset for offset, _, _ in figure)
        t += n.dur
    return onsets


def _double_attack_matras(notes: list[LeadNote]) -> set[int]:
    """The 1-indexed matras (1 matra == 1 beat) carrying a DOUBLE attack — a 'dir': two or more
    plucks starting within the matra, whether two fast notes or one note's compound bol."""
    starts: dict[int, int] = {}
    for onset in stroke_onsets(notes):
        matra = int(onset + 1e-6) + 1
        starts[matra] = starts.get(matra, 0) + 1
    return {m for m, count in starts.items() if count >= 2}


def check_bol_frame(cell: LeadPhrase, *, cycle_beats: float, frame: str) -> CellChecks:
    """Return the mukhada head's STROKE-FRAME violations (empty == it has a bol identity). Pure.

    The 2026-07-20 gat research finding: the stroke pattern is what makes a gat a gat (Parikh:
    a gat without the bol pattern "is just a vilambit gat"), and our heads had none — bols were
    optional colour. The frame facts live in `src/gats.py`; this checks the tolerant core:
      * STRUCK ON THE SAM — the first note (which sounds ON every sam) carries the strong 'da';
      * THE DIR DOUBLINGS — masitkhani on a 16-matra cycle pins them to the verified grid's
        approach positions (matras 12 and 14, the dir-da-dir-da-ra surge into the next sam);
        razakhani (or any other cycle) requires only their DENSITY (>= 2 double-attack matras)
        because flexibility is the sourced fact — position would be a guess;
      * A STROKE IDENTITY AT ALL — at least half the sounding notes carry an explicit bol.
    Melody is never judged here — the frame is rhythm; which swaras ride it stays the LLM's.
    """
    sounding = _sounding(cell.notes)
    if not sounding:
        return CellChecks()             # check_mukhada owns the degenerate-cell complaint

    hard: list[str] = []
    craft: list[str] = []
    if sounding[0].bol != "da":
        craft.append("the head's first note is not struck 'da' — it sounds ON every sam, and "
                    "the gat frame lands its arrival stroke there strong; set bol \"da\" on it")

    doubles = _double_attack_matras(cell.notes)
    grid_matras = GAT_FRAMES[frame].get("bols") is not None and cycle_beats == GAT_FRAMES[frame]["matras"]
    if grid_matras:
        approach = [m for m in GAT_FRAMES[frame]["double_stroke_matras"]
                    if m > GAT_FRAMES[frame]["mukhda_start"] - 1]      # the dir's in the mukhda span
        missing = [m for m in approach if m not in doubles]
        if missing:
            craft.append(f"the {GAT_FRAMES[frame]['display']} approach needs a dir DOUBLE stroke "
                        f"on matra(s) {' '.join(map(str, missing))} (the dir-da-dir-da-ra surge "
                        f"into the next sam) — put a note with bol \"dir\" (or two fast notes) "
                        f"in each of those matras")
    elif len(doubles) < _FRAME_MIN_DOUBLES:
        craft.append(f"the head has {len(doubles)} dir doubling(s) — a "
                    f"{GAT_FRAMES[frame]['display']} gat drives on double strokes: at least "
                    f"{_FRAME_MIN_DOUBLES} matras with a \"dir\" (or two fast notes)")

    with_bol = sum(1 for n in sounding if n.bol is not None)
    if with_bol < _BOL_MIN_COVERAGE * len(sounding):
        craft.append(f"only {with_bol} of {len(sounding)} notes carry a mizrab bol — the stroke "
                    f"pattern is the gat's identity: give most notes their da/ra (dir doublings "
                    f"where the frame asks), so the head has a rhythm signature, not just pitches")

    return CellChecks(tuple(hard), tuple(craft))


def _attacks_per_matra(notes: list[LeadNote], matras: int) -> list[int]:
    """How many plucks the notes start in each matra of the avartan (1 matra == 1 beat). Pure."""
    counts = [0] * matras
    for onset in stroke_onsets(notes):
        matra = int(onset + 1e-6)
        if 0 <= matra < matras:
            counts[matra] += 1
    return counts


def stroke_line_match(cell: LeadPhrase, *, cycle_beats: float) -> tuple[list[int], int] | None:
    """Where the notes leave the head's planned stroke line: (the 1-indexed matras whose pluck count
    differs from the line's, the matra count). None when there is no line to compare — absent,
    holding a token that is no stroke, or not one token per matra. Pure."""
    line = cell.phrase_plan.stroke_line
    matras = round(cycle_beats)
    if not line or len(line) != matras:
        return None
    planned = [stroke_line_attacks(t) for t in line]
    if None in planned:
        return None
    played = _attacks_per_matra(cell.notes, matras)
    return [i + 1 for i, (p, a) in enumerate(zip(planned, played)) if p != a], matras


def check_stroke_line(cell: LeadPhrase, *, cycle_beats: float) -> CellChecks:
    """The head's RIGHT HAND, measured: did it plan a stroke line, and do its notes play it? CRAFT
    only — the plan is the composer's own and the judges read how far the notes kept to it. Pure.

    The 2026-10-12 trace finding: bols were decoration sprinkled on notes (93% carried one, almost
    all a bare da/ra), so no head had a stroke PATTERN. The line is planned first, one token per
    matra (`PhrasePlan.stroke_line`); here each matra's planned pluck count meets the plucks the
    notes start there (`stroke_onsets` — the renderer's own timing)."""
    line = cell.phrase_plan.stroke_line
    matras = round(cycle_beats)
    if not line:
        return CellChecks(craft=(f"no stroke_line planned — write the right hand first: one bol per "
                                 f"matra ({matras} tokens, \"{STROKE_HOLD}\" for a matra with no new "
                                 f"stroke), then notes that play it",))
    unknown = sorted({t for t in line if stroke_line_attacks(t) is None})
    if unknown:
        return CellChecks(craft=(f"the stroke_line holds {' '.join(unknown)}, which are no strokes — "
                                 f"use the bol words, chikari or \"{STROKE_HOLD}\"",))
    if len(line) != matras:
        return CellChecks(craft=(f"the stroke_line has {len(line)} tokens for a {matras}-matra "
                                 f"avartan — one token per matra",))
    off, _ = stroke_line_match(cell, cycle_beats=cycle_beats) or ([], matras)
    if len(off) > (1 - _LINE_MIN_MATCH) * matras:
        return CellChecks(craft=(f"the notes play {matras - len(off)} of {matras} matras of your "
                                 f"stroke line (they differ at matra(s) {' '.join(map(str, off))}) "
                                 f"— give each note the bol its matra asks for, or revise the line",))
    return CellChecks()


# THE HEAD IS ONE SENTENCE (Sujit, 2026-10-12, on fusion_20261012_152048: "the mukhada sounds
# like 3 distinct phrases stitched together by rests — the entire mukhada should sound like an
# idea"). That head planned `da ra dir chikari` three times over, so every fourth matra became a
# melodic hole with a chikari strum in it. GAT_COMPOSITION.md §3.1 already said it (rule 6: no
# chikari and no gaps in the mukhda line; rule 5: its breath is a HELD resting swara, not a rest),
# and the shape Sujit asks for is a quick figure, then a held breather, then the approach into the
# sam. A gap is structural, so it is HARD; the shape's taste is reported.
_HEAD_SCALAR_MAX: Final = 4        # a head walking more swaras than this straight up/down is the scale
_HEAD_GAMAK_MAX: Final = 2         # gamak belongs in a head, sparingly (Sujit: "use wisely")
_EPS: Final = 1e-6


def _gamak_moments(notes: list[LeadNote]) -> int:
    """Gamaks as the ear counts them: consecutive gamak notes on one swara (a dir stroke split
    in two, a cell restruck) are ONE gamak."""
    moments, previous = 0, None
    for note in _melodic(notes):
        here = (note.swara, note.oct) if note.gamak_with else None
        if here is not None and here != previous:
            moments += 1
        previous = here
    return moments


def _held(note: LeadNote) -> bool:
    """A note the ear hears as ONE sustained sound: melodic, struck once (a compound bol re-strikes
    it, a gamak re-strikes it about every quarter second)."""
    strokes = stroke_line_attacks(note.bol) if note.bol else 1
    return (not note.rest and note.bol != "chikari" and not note.gamak_with
            and (strokes is None or strokes <= 1))


def _held_notes(notes: list[LeadNote]) -> list[tuple[float, LeadNote]]:
    """(onset, note) for every held note of at least `_MUKHADA_LONG` beats — a breather."""
    out: list[tuple[float, LeadNote]] = []
    t = 0.0
    for note in notes:
        if _held(note) and note.dur >= _MUKHADA_LONG - _EPS:
            out.append((t, note))
        t += note.dur
    return out


def _collapsed(notes: list[LeadNote]) -> list[tuple[str, int]]:
    """The head's swaras with repeated strokes merged — a dir doubling is one swara, not a turn."""
    out: list[tuple[str, int]] = []
    for note in _melodic(notes):
        pitch = (_landing_swara(note), _landing_oct(note))
        if not out or out[-1] != pitch:
            out.append(pitch)
    return out


def check_head_shape(cell: LeadPhrase, *, raga: str) -> CellChecks:
    """Is the gat head ONE continuous idea? HARD: no rest and no chikari anywhere in it (the head
    runs to the sam), and it HOLDS one note for at least `_MUKHADA_LONG` beats, struck once — the
    breather. CRAFT: it does not walk the bare scale, and it spends gamak on at most a couple of
    moments. Pure.

    The breather is HARD for a gat head (Sujit asked for it by name) where `check_mukhada` only
    reports a missing long note: the `fusion_20261012_152048` head's longest note was ONE beat,
    its "breath" four scheduled rests, and the craft note shipped with it unheeded."""
    hard: list[str] = []
    craft: list[str] = []
    gaps = [i + 1 for i, n in enumerate(cell.notes) if n.rest or n.bol == "chikari"]
    if gaps:
        hard.append(f"the head breaks at note(s) {' '.join(map(str, gaps))} with a rest or a "
                    f"chikari — it must sound as ONE idea: a quick figure, then a HELD breather "
                    f"(a resting swara left to ring, \"{STROKE_HOLD}\" in the stroke line), then "
                    f"the approach into the sam. Hold a note where you wanted the gap; no chikari "
                    f"inside the head")
    if not _held_notes(cell.notes):
        hard.append(f"the head never holds a note — it needs a BREATHER: one swara struck once "
                    f"and left to ring for at least {_MUKHADA_LONG:g} beats (no gamak, no compound "
                    f"bol on it), after the quick figure and before the approach. That held note "
                    f"is where the raga's own andolan or meend lives")
    run = max(scalar_runs(_collapsed(cell.notes), raga), default=0)
    if run > _HEAD_SCALAR_MAX:
        craft.append(f"the head walks {run} swaras straight along the scale — open with a phrase "
                     f"only this raga would play (its pakad or chalan), not the scale")
    moments = _gamak_moments(cell.notes)
    if moments > _HEAD_GAMAK_MAX:
        craft.append(f"the head swings a gamak on {moments} notes — in a head a gamak is an "
                     f"event: keep it to {_HEAD_GAMAK_MAX}, on the notes the phrase leans on, and "
                     f"let the breather ring with the raga's own andolan or meend")
    return CellChecks(tuple(hard), tuple(craft))


_SHAPE_FIT: Final = 1.0          # beats the planned stages may miss the avartan by


def _shape_windows(shape: list) -> list[tuple[str, float, float, str | None]]:
    """(stage, start, end, target) per planned stage, in beats from the sam."""
    out, t = [], 0.0
    for st in shape:
        out.append((st.stage, t, t + st.beats, st.target))
        t += st.beats
    return out


def check_head_plan(cell: LeadPhrase, *, cycle_beats: float) -> CellChecks:
    """The head's planned SHAPE (`PhrasePlan.head_shape`), measured against its notes. CRAFT only —
    like the stroke line, the plan is the composer's own and the judges read how far the notes kept
    to it: the stages are known and fill the avartan, there is a breather, and the notes HOLD a note
    (struck once, at least `_MUKHADA_LONG` beats) that starts inside the breather — on its target
    swara when one was named. Pure."""
    shape = cell.phrase_plan.head_shape
    if not shape:
        return CellChecks(craft=("no head_shape planned — plan the head's stages first (a quick "
                                 "figure, a held breather, then the approach into the sam)",))
    craft: list[str] = []
    unknown = sorted({st.stage for st in shape if st.stage not in HEAD_STAGES})
    if unknown:
        craft.append(f"head_shape names {' '.join(unknown)} — the stages are "
                     f"{' / '.join(HEAD_STAGES)}")
    total = sum(st.beats for st in shape)
    if abs(total - cycle_beats) > _SHAPE_FIT:
        craft.append(f"head_shape spans {total:g} beats for a {cycle_beats:g}-beat avartan — the "
                     f"stages are the whole head, in order")
    breathers = [w for w in _shape_windows(shape) if w[0] == "breather"]
    if not breathers:
        craft.append("head_shape has no breather — the head needs one held arrival")
        return CellChecks(craft=tuple(craft))
    held = _held_notes(cell.notes)
    for _, start, end, target in breathers:
        inside = [n for t, n in held if start - _EPS <= t < end - _EPS]
        if not inside:
            craft.append(f"your breather (beats {start:g}-{end:g}) holds no note — strike one swara "
                         f"there and let it ring")
        elif target and all(_landing_swara(n) != target for n in inside):
            craft.append(f"your breather was to hold {target}, but it holds "
                         f"{' '.join(_landing_swara(n) for n in inside)}")
    return CellChecks(craft=tuple(craft))


def check_head_idea(cell: LeadPhrase, idea: HeadIdea | None) -> CellChecks:
    """Did the composed head keep the Composer's IDEA (`HeadIdea`)? CRAFT only — "develop it, never
    replace it" is the brief, and the judges read how far the head strayed: its first note (which
    sounds on every sam) is the idea's sam swara, its core cell sounds in order (small gaps allowed,
    any octave), and it plans the idea's stroke line. No idea, nothing to compare. Pure."""
    sounding = _sounding(cell.notes)
    if idea is None or not sounding:
        return CellChecks()
    craft: list[str] = []
    if _landing_swara(sounding[0]) != idea.sam_swara:
        craft.append(f"the head opens on {_landing_swara(sounding[0])}, but your idea put "
                     f"{idea.sam_swara} on the sam — open the head on it")
    if not _quote_present([_landing_swara(n) for n in sounding], idea.cell, _QUOTE_MAX_GAP):
        craft.append(f"the idea's core cell ({' '.join(idea.cell)}) never sounds in the head — "
                     f"let it recur")
    if idea.stroke_line and cell.phrase_plan.stroke_line != idea.stroke_line:
        craft.append("the head's stroke_line differs from your idea's — keep the idea's right hand "
                     "unless the melody truly asks otherwise")
    return CellChecks(craft=tuple(craft))


def verify_bol_frame(cell: LeadPhrase, *, cycle_beats: float, frame: str) -> list[str]:
    """The bol frame's HARD faults only — what drives a re-roll. `check_bol_frame` adds the
    reported craft notes."""
    return list(check_bol_frame(cell, cycle_beats=cycle_beats, frame=frame).hard)


def _overrun_violation(notes: list[LeadNote], window_beats: float, cell_name: str,
                       tail: str) -> str | None:
    """The shared TRUNCATION guard for end-anchored cells: total duration (rests included)
    must not exceed the window, or placement clips the cadence the verifier just approved."""
    total = sum(n.dur for n in notes)
    if total <= _CELL_FILL_MAX * window_beats:
        return None
    return (f"the {cell_name} runs {total:g} beats but its window is {window_beats:g} — the "
            f"overrun gets TRUNCATED, cutting off your own ending; {tail}")


def intro_min_phrases(window_beats: float) -> int:
    """How many rest-separated phrases an alap window of this length must hold — the ask the
    prompt states and the floor this verifier enforces, so the two always agree. Pure."""
    return _INTRO_MIN_PHRASES if window_beats >= _INTRO_ROOMY_WINDOW else _INTRO_MIN_PHRASES_SHORT


def _phrase_end(phrase: list[LeadNote]) -> LeadNote | None:
    """A phrase's resting note: its last sounding note that is not a chikari stroke."""
    return next((n for n in reversed(phrase) if not n.rest and n.bol != "chikari"), None)


def _intro_call_and_answer(phrases: list[list[LeadNote]], raga: str) -> tuple[list[str], list[str]]:
    """The alap's phrase endings by ROLE (Sujit, 2026-10-19: "a call should not rest on a nyas; it
    ends on a note that builds tension, so the resolving phrase feels like home"):
      * a CALL ends OFF the raga's CORE nyas — on a tension note (a lighter permitted rest counts:
        tension is relative), never on a swara the raga forbids resting on;
      * an ANSWER resolves onto a CORE nyas (arrived the raga's way). Calls may pile up first — a
        long call, or two or three in a row, build more tension (Sujit) — and the close answers
        whatever is still open, so no call needs its answer in the very next phrase;
    CORE, not every permitted rest: in Malkauns all five swaras are permitted rests, which would
    leave a call nowhere to stop.
      * with three or more phrases, at least one call comes before the close — tension is built;
      * the close (checked elsewhere) is the held Sa.
    A phrase before the close that CLIMBS into a main nyas other than Sa is a hard fault (Sujit, same
    day: "a call should not stop on a nyas" — n d n R climbing into Re is a call that stopped on one).
    Sa is exempt: home is home from either side (d n S, the leading tone rising, resolves).
    Returns (hard faults, craft notes). Pure."""
    rules = NYAS[raga]
    hard: list[str] = []
    craft: list[str] = []
    roles: list[str] = []
    for i, ph in enumerate(phrases):
        melody = [n for n in ph if not n.rest and n.bol != "chikari"]
        if not melody:
            roles.append("none")
            continue
        end, before = melody[-1], (melody[-2] if len(melody) > 1 else None)
        swara = _landing_swara(end)
        rising = None if before is None or _height(before) == _height(end) else _height(before) < _height(end)
        if swara in rules["avoid"]:
            hard.append(f"phrase {i + 1} stops on {swara}, a weak swara in this raga — neither a call nor "
                        f"an answer may stop there")
            roles.append("none")
        elif swara not in rules["core"]:
            roles.append("call")
        else:
            problem = nyas_problem(raga, swara, rising)
            if problem:
                hard.append(f"phrase {i + 1}: {problem}")
            elif rising and swara != "S" and i < len(phrases) - 1:
                hard.append(f"phrase {i + 1} climbs into {swara}, a main nyas — that is a call stopping on a "
                            f"nyas, and it sounds unfinished. Either end the call on a tension note (off "
                            f"{' '.join(rules['core'])}), or make it an answer that FALLS or TURNS onto {swara}")
            roles.append("answer")
    if len(phrases) >= 3 and "call" not in roles[:-1]:
        hard.append(f"every phrase before the close rests on a main nyas — the alap never builds tension: "
                    f"let at least one CALL stop short of them ({' '.join(rules['core'])}) on a note that "
                    f"leans onward, so the answer that follows lands home")
    return hard, craft


def _height(note: LeadNote) -> int:
    return SWARAS[_landing_swara(note)] + 12 * _landing_oct(note)


def _intro_pulse_violations(notes: list[LeadNote], phrase_grid: tuple[float, ...],
                            from_beat: float = 0.0) -> list[str]:
    """The JOD walks on the pulse: from `from_beat` on, each phrase starts on a vibhag (a beat in
    `phrase_grid`, counted from the window's start) and every note of a beat or more starts on a
    beat. The unmetred alap before it is free. Pure."""
    viol: list[str] = []
    t, prev_rest, starts, off_beat = 0.0, True, [], []
    for n in notes:
        if not n.rest and t >= from_beat - 1e-6:
            if prev_rest:
                starts.append(t)
            if n.dur >= 1.0 and abs(t - round(t)) > 1e-6:
                off_beat.append(t)
        prev_rest = n.rest
        t += n.dur
    grid = [round(g, 6) for g in phrase_grid]
    stray = [b for b in starts if not any(abs(b - g) < 1e-6 for g in grid)]
    if stray:
        allowed = ", ".join(f"{g:g}" for g in grid[:8]) + (" ..." if len(grid) > 8 else "")
        viol.append(f"phrase(s) start at beat {', '.join(f'{b:g}' for b in stray)} — off the vibhag: "
                    f"start every phrase on a vibhag (beats {allowed} from the alap's first beat), "
                    f"so the call and answer walk on the pulse")
    if off_beat:
        viol.append(f"{len(off_beat)} note(s) of a beat or longer start between beats (first at beat "
                    f"{off_beat[0]:g}) — on a jod's pulse a long note lands ON a beat; only half-beat "
                    f"passing notes sit between")
    return viol


def _onsets(notes: list[LeadNote]) -> dict[int, float]:
    """Each note's start in beats from the line's first beat, keyed by the note's identity."""
    out: dict[int, float] = {}
    t = 0.0
    for n in notes:
        out[id(n)] = t
        t += n.dur
    return out


def _jod_entry_violations(notes: list[LeadNote], jod_at: float) -> list[str]:
    """The JOD enters ON its beat: a sounding note starts exactly at `jod_at`, and no alap note
    rings across it (the pulse must arrive, not blur in). Pure."""
    t = 0.0
    for n in notes:
        if t > jod_at + 1e-6:
            break
        if not n.rest and abs(t - jod_at) < 1e-6:
            return []
        if not n.rest and t < jod_at < t + n.dur - 1e-6:
            return [f"a note starting at beat {t:g} rings across beat {jod_at:g}, where the JOD must "
                    f"enter — end the alap's last phrase (a rest is fine) and strike the jod's first "
                    f"note exactly ON beat {jod_at:g}"]
        t += n.dur
    return [f"no note starts on beat {jod_at:g} — the JOD enters exactly there: let a rest carry the "
            f"alap up to beat {jod_at:g}, then strike the jod's first note on it"]


def _alap_hold_notes(notes: list[LeadNote], phrases: list[list[LeadNote]], jod_at: float | None,
                     bpm: float) -> list[str]:
    """The ALAP part (before the jod) is mostly HELD notes, each phrase standing on one held
    swara, and it opens the raga ONE FRONTIER AT A TIME (Clarke ch. 3; ALAP_RESEARCH.md).
    Measured in seconds, since a beat at a doom tempo is half a second. Craft notes. Pure."""
    start = _onsets(notes)
    alap = [ph for ph in phrases if ph and (jod_at is None or start[id(ph[0])] < jod_at - 1e-6)]
    melody = [n for ph in alap for n in _melodic(ph)]
    if not melody:
        return []
    held_beats = _ALAP_HELD_S * bpm / 60.0
    out: list[str] = []
    sound = sum(n.dur for n in melody)
    held = sum(n.dur for n in melody if n.dur >= held_beats - 1e-6)
    if held < _ALAP_HELD_SHARE * sound:
        out.append(f"only {held / sound:.0%} of the alap's sound is on notes held {_ALAP_HELD_S:g} s "
                   f"({held_beats:g} beats) or longer — an alap is mostly HELD notes: let each phrase "
                   f"stand on its swara for seconds and pass through the others")
    bare = [i + 1 for i, ph in enumerate(alap) if max((n.dur for n in _melodic(ph)), default=0.0) < held_beats - 1e-6]
    if bare:
        out.append(f"alap phrase(s) {', '.join(map(str, bare))} hold no note for {_ALAP_HELD_S:g} s — "
                   f"build each phrase around ONE held swara, the note it stands on")
    seen: set[int] = set()
    for i, ph in enumerate(alap):
        heights = {_landing_pitch(n) for n in _melodic(ph)}
        if seen:
            lo, hi = min(seen), max(seen)
            new = {h for h in heights if h < lo or h > hi}
            if len(new) > _ALAP_MAX_NEW_SWARAS:
                out.append(f"alap phrase {i + 1} opens {len(new)} new swaras at once — reveal the raga "
                           f"ONE frontier at a time: reach one swara past the ground so far and hold it")
        seen |= heights
    return out


def _intro_rhythm_violations(notes: list[LeadNote]) -> list[str]:
    """The alap keeps time with the arpeggio under it: durations on the sixteenth grid, single
    strokes, and quick steps as contrast rather than the texture. Pure."""
    viol: list[str] = []
    off = [n.dur for n in notes if abs(n.dur / _INTRO_GRID - round(n.dur / _INTRO_GRID)) > 1e-6]
    if off:
        viol.append(f"{len(off)} duration(s) fall off the beat grid (e.g. {off[0]:g}) — write every "
                    f"note and rest as a multiple of {_INTRO_GRID:g} (0.25, 0.5, 1, 1.5, 2 ...) so "
                    f"the alap stays in time with the arpeggio under it")
    melodic = [n for n in _sounding(notes) if n.bol != "chikari"]
    doubled = [n for n in melodic if n.bol in _INTRO_COMPOUND_BOLS]
    if doubled:
        viol.append(f"{len(doubled)} note(s) carry a compound bol (dir/dar/dara...) — those are the "
                    f"gat's stroke figures; an alap uses single strokes (da / ra)")
    if melodic:
        quick = sum(n.dur < _INTRO_QUICK for n in melodic) / len(melodic)
        if quick > _INTRO_QUICK_SHARE_MAX:
            viol.append(f"{quick:.0%} of the alap's notes are quick steps (under half a beat) — an "
                        f"alap is slow: keep quick steps under {_INTRO_QUICK_SHARE_MAX:.0%} for "
                        f"contrast and let most notes speak for a beat or more")
    return viol


def check_intro(cell: LeadPhrase, *, window_beats: float, raga: str,
                 mukhada: LeadPhrase | None = None,
                 phrase_grid: tuple[float, ...] | None = None,
                 jod_at: float | None = None, bpm: float = 60.0) -> CellChecks:
    """Return the intro/alap's structural violations (empty == a grounded alap). Pure.

    ALAP, THEN JOD (2026-10-19, second pass): the intro is an unmetred ALAP — mostly held notes,
    measured in seconds at `bpm` — and then, from `jod_at` (beats from the window's start), a short
    JOD on the pulse that walks the band in. The pulse rules below apply from `jod_at` only (from
    the first beat when `jod_at` is None and a `phrase_grid` is given — the whole line a jod), and
    the jod must ENTER on `jod_at` (hard). The alap's held share, held phrase notes and one-frontier
    reveal are craft notes. The motif comes from the raga's pakad/chalan; the head is PREPARED (its
    first swara rests near the close), never quoted.

    The shape is CALL AND ANSWER ON A JOD'S PULSE (Sujit's ear, 2026-10-19). The July design held
    every phrase's tension and let a code-plucked low Sa (the jod string) supply home between
    phrases; the jod was deleted on 2026-10-12 and nothing replaced it, so the alap became a
    string of questions with no answer, drifting off the beat ("random"). Now:
      * CALL AND ANSWER (hard) — a CALL ends OFF the nyas, on a note that builds tension; the next
        phrase ANSWERS it onto a nyas; at least one call comes before the close
        (`_intro_call_and_answer` — the generic every-ending-on-a-nyas rule does not apply here);
      * ON THE PULSE (hard, with `phrase_grid`) — every phrase starts on a vibhag (`phrase_grid`:
        the beats, from the window's start, where one begins) and every note of a beat or more
        starts on a beat;
      * OPENS AROUND SA — the first note is Sa or a step or two from it, never in the taar;
      * TOUCHES THE MANDRA — the melodic line itself dips below home;
      * ENDS ON A HELD SA — the final phrase resolves, onto the intro's longest Sa;
      * SA-ANCHORED — Sa (the plucks + the close) still carries real duration and recurs;
      * REAL SILENCE — at least two true rests of a beat or more.
    Plus the ONE-MOTIF discipline (`_motif_violations`): the intro develops a single declared
    motif — drawn from the raga's pakad/chalan, the mukhada head prepared but never quoted —
    and reveals it progressively (badhat) instead of
    inventing independent phrases. Badhat here means the ENVELOPE widens (narrow opening,
    widest reach past the midpoint) — individual phrases may ascend or descend freely.
    The long pause between the alap's last Sa and the mukhada is NOT checked here — that gap is
    code-reserved by the generator (a shortened window), never the LLM's job. But the alap must
    STAY inside its shortened window (`window_beats`) — an overrun spills into the reserved
    silence and erases the very pause the design owes the listener. An alap SHORTER than the
    window is fine (more silence, never less).
    """
    notes = cell.notes
    sounding = _sounding(notes)
    if not sounding:
        return CellChecks(hard=("the intro has no sounding notes — an alap must unfold the raga, sparsely",))

    hard: list[str] = []
    craft: list[str] = []
    total = sum(n.dur for n in notes)
    if total > _CELL_FILL_MAX * window_beats:
        hard.append(f"the alap runs {total:g} beats but its window is only {window_beats:g} — "
                    f"it would spill into the silence code reserves before the gat; end the "
                    f"held Sa within the window and let the quiet do the rest")

    first = sounding[0]
    if _landing_oct(first) >= 1 or _scale_steps_between(_landing_swara(first), "S", raga) > _INTRO_OPEN_MAX_STEPS:
        craft.append(f"the alap opens on {_landing_swara(first)} (oct {_landing_oct(first):+d}) — "
                    f"begin AROUND madhya Sa (Sa itself or a step or two from it); the exposition "
                    f"starts at home, then dips into the mandra")
    if not any(_landing_oct(n) < 0 for n in _melodic(sounding)):
        craft.append("the alap's melodic line never touches the mandra (lower) octave — dip "
                    "below home in the early phrases before the line rises (the low Sa pluck "
                    "alone is punctuation, not the dip)")

    last = sounding[-1]
    if _landing_swara(last) != "S":
        _cadence_bucket(_landing_swara(last), raga, hard, craft).append(f"the alap ends on {last.swara}, not Sa — it must RESOLVE: come home to a "
                    f"held Sa as the final note")
    elif last.dur < _INTRO_HELD_SA:
        craft.append(f"the alap's final Sa lasts only {last.dur:g} beats — HOLD it (>= "
                    f"{_INTRO_HELD_SA:g} beats) so the resolution is felt before the gat enters")

    total = sum(n.dur for n in sounding)
    sa_dur = sum(n.dur for n in sounding if _landing_swara(n) == "S")
    if sa_dur < _INTRO_SA_SHARE * total:
        craft.append(f"Sa carries only {sa_dur / total:.0%} of the alap's sounding time — keep "
                    f"home ringing (>= {_INTRO_SA_SHARE:.0%} by duration): let the answers come "
                    f"home to Sa and hold the closing Sa")
    returns = _sa_returns(sounding)
    if returns < _INTRO_MIN_SA_RETURNS:
        craft.append(f"Sa is sounded only {returns} separate time(s) — touch home at least "
                    f"{_INTRO_MIN_SA_RETURNS} times: an answer that comes home, and the held "
                    f"Sa at the close")

    rests = [n for n in notes if n.rest and n.dur >= _INTRO_MIN_REST_BEATS]
    if len(rests) < _INTRO_MIN_RESTS:
        craft.append(f"the alap has {len(rests)} true rest(s) of {_INTRO_MIN_REST_BEATS:g}+ beats — "
                    f"use at least {_INTRO_MIN_RESTS}; an alap breathes in real silence, not in "
                    f"wall-to-wall notes")

    craft += _intro_breath_violations(notes, bpm)
    craft += _intro_rhythm_violations(notes)

    # PHRASE GRAMMAR — short sentences separated by real silence, in CALL AND ANSWER: calls pause
    # on a nyas that is not Sa, answers come home to Sa (Sujit, 2026-10-19).
    phrases = _intro_phrases(notes)
    min_phrases = intro_min_phrases(window_beats)
    if len(phrases) < min_phrases:
        craft.append(f"the alap is only {len(phrases)} phrase(s) — compose at least "
                    f"{min_phrases} short, INDEPENDENT phrases separated by real silence; "
                    f"do not write one continuous line")
    for i, ph in enumerate(phrases[:-1]):           # every phrase but the final settle
        core = _melodic(ph)
        if core and all(_landing_swara(n) == "S" for n in core):
            craft.append(f"phrase {i + 1} is only Sa — a phrase must EXPLORE the motif through "
                        f"the raga's swaras; bare Sa is a drone stroke, not a sentence")
    calls, answers = _intro_call_and_answer(phrases, raga)
    hard += calls
    craft += answers
    if phrase_grid is not None:
        hard += _intro_pulse_violations(notes, phrase_grid, from_beat=jod_at or 0.0)
    if jod_at is not None:
        hard += _jod_entry_violations(notes, jod_at)
    craft += _alap_hold_notes(notes, phrases, jod_at, bpm)
    held = [n for n in notes if n.bol == "chikari" and n.dur > _CHIKARI_MAX_DUR]
    if held:
        hard.append(f"{len(held)} chikari stroke(s) written longer than {_CHIKARI_MAX_DUR:g} "
                    f"beat — a chikari is a STRUCK string filling an empty matra, played in "
                    f"time and then gone; held, it becomes a second drone over the tanpura. "
                    f"Write chikari short (0.25-0.5) and place it where the melody rests")
    run = _longest_mid_sa_run(notes)
    if run > _INTRO_MAX_SA_RUN:
        craft.append(f"the alap dwells on Sa for {run:g} continuous beats — Sa is a drone TOUCH "
                    f"between phrases, not a note to repeat or sustain; explore the motif "
                    f"between the Sa strokes")

    # STATE THE RAGA — the alap must make THIS raga unmistakable, so at least one phrase quotes the
    # PAKAD (the signature phrase), not just in-scale wandering (Sujit, 2026-07-15). Fuzzy, octave-
    # agnostic, small-gap match (a passing/grace note doesn't break the quote — the same tier Rasik
    # and the antara-quote use). This is the ONE authenticity fact the intro can be held to in code;
    # deeper raga-idiom judgement still belongs to Rasik.
    intro_swaras = [_landing_swara(n) for n in sounding]
    if not any(_quote_present(intro_swaras, phrase, _QUOTE_MAX_GAP)
               for phrase in RAGAS[raga]["pakad"]):
        pakad = " | ".join(" ".join(p) for p in RAGAS[raga]["pakad"])
        craft.append(f"the alap never states the raga's PAKAD ({pakad}) — build the phrases from the "
                    f"raga's signature phrase(s), quoting one then varying it, so the raga is clear; "
                    f"don't wander through in-scale notes at random")

    # ORNAMENT DISCIPLINE — the render anchors a meend on its TARGET, so an over-meended line is
    # HEARD as its targets (the audible-line checks above read exactly that). This names the
    # cause, so the judges see the disease, not only each symptom.
    craft.extend(_ornament_density_notes(notes, "alap"))

    craft.extend(_motif_violations(cell, phrases, mukhada, raga, reach_down=lives_low(raga)))

    return CellChecks(tuple(hard), tuple(craft))


def verify_intro(cell: LeadPhrase, *, window_beats: float, raga: str,
                 mukhada: LeadPhrase | None = None,
                 phrase_grid: tuple[float, ...] | None = None,
                 jod_at: float | None = None, bpm: float = 60.0) -> list[str]:
    """The intro's HARD faults only — what drives a re-roll. `check_intro` adds the
    reported craft notes."""
    return list(check_intro(cell, window_beats=window_beats, raga=raga, mukhada=mukhada,
                            phrase_grid=phrase_grid, jod_at=jod_at, bpm=bpm).hard)


def _intro_breath_violations(notes: list[LeadNote], bpm: float = 60.0) -> list[str]:
    """How much of the alap is SILENCE, and whether any one note swallows it.

    Both are shares rather than counts: a count of rests is satisfiable by writing the
    minimum (which is exactly what happened), and "the longest note" with no ceiling is
    satisfiable by holding one note to the end of the window."""
    total = sum(n.dur for n in notes)
    if total <= 0:
        return []
    viol: list[str] = []
    silence = sum(n.dur for n in notes if n.rest)
    if silence < _INTRO_REST_SHARE * total:
        viol.append(f"only {silence / total:.0%} of the alap is silence (need >= "
                    f"{_INTRO_REST_SHARE:.0%}) — the space between phrases is part of the "
                    f"music, not leftover time; let each phrase end and BREATHE before the next")
    ceiling = max(_INTRO_MAX_NOTE_BEATS, _ALAP_MAX_NOTE_S * bpm / 60.0, _INTRO_MAX_NOTE_SHARE * total)
    longest = max((n.dur for n in notes if not n.rest), default=0.0)
    if longest > ceiling:
        viol.append(f"one note is held {longest:g} beats — {longest / total:.0%} of the whole "
                    f"alap in a single sound. Keep any one note under {ceiling:g} beats: the "
                    f"closing Sa RESOLVES the line, it does not fill the rest of the window")
    return viol


def _ang_violation(sounding: list[LeadNote], raga: str, cell: str, *,
                   also_accept: list[str] | None = None) -> str | None:
    """Does this part state one of the raga's OWN movements, or just its notes?

    A part built only from legal swaras can belong to any raga sharing the scale — the
    2026-09-14 outro closed on `D R S` and a held Sa, which resolves the pitch and says
    nothing about Bageshree. `also_accept` lets a part qualify by quoting the head instead,
    since restating the gat's own phrase is as much the raga as quoting the pakad is.
    """
    seq = [(_landing_swara(n), _landing_oct(n)) for n in sounding]
    if ang_matches(seq, raga):
        return None
    swaras = [sw for sw, _ in seq]
    if also_accept and _quote_present(swaras, also_accept, _QUOTE_MAX_GAP):
        return None
    library = " | ".join(" ".join(a) for a in RAGAS[raga]["pakad"])
    return (f"the {cell} states none of this raga's own movements — it uses legal swaras in an "
            f"order that could belong to any raga sharing the scale. Build it from a phrase the "
            f"raga actually moves in ({library}), or from the gat head's own line")


def _motion_violations(sounding: list[LeadNote], raga: str, cell: str) -> list[str]:
    """Does the line MOVE like the raga, or merely use its notes? Pure.

    ONE measure, derived from already-encoded facts (the raga's own ladder): how far the line
    walks in one unbroken stepwise direction. That is the scale showing through, and it is
    unambiguous enough to reject.

    The VAKRA share — how often the line turns — is deliberately NOT a rule here, though it
    is measured for Rasik. Two reasons, both learned by trying it: a hand-written phrase that
    descends and then climbs reads as perfectly idiomatic while scoring only 25%, and the
    2026-09-14 render that prompted all this scored 38% — so a floor tight enough to catch the
    real failure would reject real music. Turn share is "legal but weakly characteristic",
    which belongs in a score a critic weighs, not a rule that rejects. Making every aesthetic
    property a hard rule produces stiff, uniform music.
    """
    seq = [(_landing_swara(n), _landing_oct(n)) for n in sounding]
    viol: list[str] = []
    # DIRECTION, checked on the REALIZED cell. The LLM guardrail already states this rule at
    # generation time, but a guardrail is a bounded retry: what it cannot fix, it ships. The
    # 2026-09-14 render shows where that lands — the verified head is clean, while the fast
    # developments and fills inside the same sections carry 3, 6 and 9 violations, because
    # `verify_fill` checks sixteenths and the seam and never looks at direction. A swara the
    # raga admits in one direction only is the raga's grammar, not a preference: Bageshree
    # ascending `m P D n S'` is generically modal, while `m D n S'` up and `S' n D P m` down
    # is the raga.
    viol += [f"{v} (in the {cell})" for v in dict.fromkeys(direction_violations(seq, raga))]
    scalar = _scalar_run_violation(seq, raga, cell)
    if scalar:
        viol.append(scalar)
    return viol


def _scalar_run_violation(seq: list[tuple[str, int]], raga: str, cell: str) -> str | None:
    """The stepwise-run cap, phrased as the REPAIR (None == the line turns often enough). Pure.

    HARD, deliberately (restored 2026-10-12). Phase 1b demoted it to craft, and the first live
    run showed the cost: every Producer verdict then targeted the taan's scalar runs, and each
    revise regenerated the WHOLE lead at full price and came back scalar again. As a hard fault
    it drives the cheap local re-roll of the one cell instead — and the message names the
    raga's own fragments, so the re-roll has something concrete to build from.

    ONE dash up to an octave passes (2026-10-12): the message always called a sapat idiomatic,
    but the cap rejected it — two of five live taan takes failed on a single 7-8 note dash. A
    second long run, or one longer than an octave, is the scale marching, and fails."""
    long_runs = [r for r in scalar_runs(seq, raga) if r > _TAAN_SCALAR_MAX]
    if not long_runs or (len(long_runs) == 1 and long_runs[0] <= octave_span(raga)):
        return None                    # one dash up to an octave is a sapat — the idiom allows it
    run = max(long_runs)
    fragments = " | ".join(" ".join(f) for f in RAGAS[raga]["chalan"])
    return (f"the {cell} walks {run} notes in one unbroken stepwise direction"
            f"{f' ({len(long_runs)} such runs)' if len(long_runs) > 1 else ''} — that is the "
            f"SCALE, not the raga. Rebuild it from the raga's vakra/chalan fragments "
            f"({fragments}): take a 3-4 note fragment, sequence it, and turn back, skip, or "
            f"repeat a swara within every {_TAAN_SCALAR_MAX} notes. One straight dash (a sapat) "
            f"is idiomatic; marching consecutive scale steps is not")


def _is_sa_pluck(note: LeadNote) -> bool:
    """The between-phrase DRONE anchor: a mandra (or lower) Sa sounding — the guitarist's low
    open string, the sitar's jod string. Analysis treats it as PUNCTUATION, not melody: it
    must not fake a mandra dip, a motif tone, or a phrase of its own."""
    return (not note.rest and note.bol != "chikari"
            and _landing_swara(note) == "S" and _landing_oct(note) <= _INTRO_PLUCK_MAX_OCT)


def _melodic(notes: list[LeadNote]) -> list[LeadNote]:
    """The MELODY notes of a line — sounding, minus the two kinds of punctuation: chikari
    strokes (taar-Sa accents) and mandra-Sa plucks (the drone anchor). Neither may fake a
    motif match, a register reach, or a phrase ending."""
    return [n for n in notes if not n.rest and n.bol != "chikari" and not _is_sa_pluck(n)]


def lives_low(raga: str) -> bool:
    """A raga developed in the mandra and not the taar (`raga.REGISTER`, sourced) — its alap's
    widest reach goes DOWN (Darbari: mandra Dha and Pa), not up into the taar."""
    saptak = REGISTER.get(raga, {}).get("saptak", [])
    return "mandra" in saptak and "taar" not in saptak


def _motif_violations(cell: LeadPhrase, phrases: list[list[LeadNote]],
                      mukhada: LeadPhrase | None, raga: str, *, reach_down: bool = False) -> list[str]:
    """The intro's ONE-MOTIF + BADHAT violations — the aochar develops a single recurring idea
    and reveals it progressively (see the `_INTRO_MOTIF_*` block for the diagnosed failure):
      * A REAL MOTIF IS DECLARED — `phrase_plan.seed` names the 2-5 swara kernel;
      * DRAWN FROM THE RAGA — the motif appears (in order, small gaps) in one of the raga's
        pakad/chalan phrases. Until 2026-10-19 it was drawn from the mukhada head, which made the
        alap a preview of the gat's tune — the pop way; a Hindustani alap PREPARES the head's
        swaras without quoting it (Clarke ch. 3, ALAP_RESEARCH.md). So, when the head is known:
      * PREPARED, NOT QUOTED — the head's first swara rests in one of the last two phrases, and
        the head's opening figure is not heard in the alap;
      * EVERY PHRASE CARRIES IT — each phrase except the final settle touches the motif's
        opening fragment (develop ONE thought, don't invent a new phrase each time);
      * REVEALED COMPLETELY — the full motif is stated somewhere before the held Sa;
      * NARROW OPENING — phrase 1 stays a fragment around home (<= `_INTRO_OPEN_SPAN`
        semitones), so there is range left to unfold;
      * LATE WIDEST REACH — the intro's highest melody note arrives past the midpoint; for a
        raga that lives low (`reach_down`), its LOWEST.
    """
    viol: list[str] = []
    seed = cell.phrase_plan.seed
    if not (_INTRO_MOTIF_MIN <= len(seed) <= _INTRO_MOTIF_MAX):
        viol.append(f"the intro declares no usable motif (seed = {' '.join(seed) or 'empty'}) — "
                    f"phrase_plan.seed must name the ONE recurring idea, "
                    f"{_INTRO_MOTIF_MIN}-{_INTRO_MOTIF_MAX} swaras from the raga's pakad or chalan, "
                    f"that every phrase develops")
    else:
        sources = [list(ph) for key in ("pakad", "chalan") for ph in RAGAS[raga].get(key, [])]
        if sources and not any(_quote_present(src, seed, _QUOTE_MAX_GAP) for src in sources):
            viol.append(f"the motif ({' '.join(seed)}) is not drawn from the raga's pakad or chalan — "
                        f"take the alap's idea from the raga's own phrases; the gat brings its own tune")
        anchor = seed[:_INTRO_ANCHOR_LEN]
        for i, ph in enumerate(phrases[:-1]):       # the final phrase only SETTLES — exempt
            if not _quote_present([_landing_swara(n) for n in _melodic(ph)], anchor, _QUOTE_MAX_GAP):
                viol.append(f"phrase {i + 1} never touches the motif ({' '.join(seed)}) — every "
                            f"phrase explores or varies the ONE motif (at least its opening "
                            f"{' '.join(anchor)}) before landing on Sa; do not invent a new "
                            f"phrase each time")
        all_melodic = [_landing_swara(n) for ph in phrases for n in _melodic(ph)]
        if not _quote_present(all_melodic, seed, _QUOTE_MAX_GAP):
            viol.append(f"the full motif ({' '.join(seed)}) is never stated — reveal it "
                        f"completely in a later phrase (the reveal is the intro's story)")

    first_melodic = _melodic(phrases[0]) if phrases else []
    if first_melodic:
        span = max(map(_landing_pitch, first_melodic)) - min(map(_landing_pitch, first_melodic))
        if span > _INTRO_OPEN_SPAN:
            viol.append(f"the opening phrase spans {span} semitones — badhat: phrase 1 states a "
                        f"NARROW fragment around home (<= {_INTRO_OPEN_SPAN}); each later phrase "
                        f"may add a note or widen the range")
    melodic = [n for ph in phrases for n in _melodic(ph)]
    if melodic:
        pitches = [_landing_pitch(n) for n in melodic]
        peak = pitches.index(min(pitches) if reach_down else max(pitches))
        elapsed = sum(n.dur for n in melodic[:peak])
        total = sum(n.dur for n in melodic)
        if elapsed < _INTRO_PEAK_MIN_POS * total:
            where = "lowest (this raga reaches DOWN)" if reach_down else "highest"
            viol.append(f"the intro's {where} note arrives too early — badhat: reveal the raga "
                        f"gradually and let the widest reach land past the midpoint, in the "
                        f"later phrases")
    if mukhada is not None:
        viol += _head_preparation_notes(phrases, mukhada)
    return viol


def _head_preparation_notes(phrases: list[list[LeadNote]], mukhada: LeadPhrase) -> list[str]:
    """The alap PREPARES the gat head without quoting it: the head's first swara (it sounds on
    every sam) rests near the close, and the head's opening figure is not heard. Craft. Pure."""
    head = [_landing_swara(n) for n in _sounding(mukhada.notes) if n.bol != "chikari"]
    if not head:
        return []
    notes: list[str] = []
    endings = [_phrase_end(ph) for ph in phrases[-2:]]
    if not any(e is not None and _landing_swara(e) == head[0] for e in endings):
        notes.append(f"the alap's last phrases never rest on {head[0]}, the head's first swara — "
                     f"prepare the gat: let the lead-in stand on the swara the head enters on")
    figure = head[:_INTRO_HEAD_QUOTE]
    line = [_landing_swara(n) for ph in phrases for n in _melodic(ph)]
    if len(figure) == _INTRO_HEAD_QUOTE and any(line[i:i + len(figure)] == figure
                                                 for i in range(len(line) - len(figure) + 1)):
        notes.append(f"the alap plays the head's opening figure ({' '.join(figure)}) — prepare the "
                     f"head's swaras, don't quote its tune: the gat's entry should be news")
    return notes


def _intro_groups(notes: list[LeadNote]) -> list[list[LeadNote]]:
    """Split the alap at true rests: each group is the run of sounding notes between rests.
    Leading/trailing rests create no empty group."""
    groups: list[list[LeadNote]] = []
    cur: list[LeadNote] = []
    for n in notes:
        if n.rest:
            if cur:
                groups.append(cur)
                cur = []
        else:
            cur.append(n)
    if cur:
        groups.append(cur)
    return groups


def _intro_phrases(notes: list[LeadNote]) -> list[list[LeadNote]]:
    """The alap's PHRASES: the rest-separated groups that carry melody. The vistar grammar is
    phrase -> silence -> low Sa pluck -> phrase..., so a group that is ONLY the mandra-Sa
    pluck is punctuation between phrases, not a phrase of its own."""
    return [g for g in _intro_groups(notes) if not all(_is_sa_pluck(n) for n in g)]


def _longest_mid_sa_run(notes: list[LeadNote]) -> float:
    """The longest run of consecutive Sa by duration (a REST breaks a run), EXCLUDING the alap's
    final held Sa (the close is meant to be long). Catches a Sa sustain/repeat inside the
    exposition — the 'Sa played continuously' failure — without penalising the closing nyas."""
    runs: list[float] = []
    run = 0.0
    for n in notes:
        if not n.rest and _landing_swara(n) == "S":
            run += n.dur
        else:
            if run:
                runs.append(run)
            run = 0.0
    if run:
        runs.append(run)
    sounding = _sounding(notes)
    if runs and sounding and _landing_swara(sounding[-1]) == "S":
        runs.pop()          # the final run is the held-Sa close — exempt
    if runs and sounding and sounding[0] is notes[0] and _landing_swara(sounding[0]) == "S":
        runs.pop(0)         # the opening sustained Sa is the establishing phase — exempt
    return max(runs, default=0.0)




def _sa_returns(sounding: list[LeadNote]) -> int:
    """How many separate times the line COMES HOME to Sa — a run of consecutive Sa notes
    (any octave; chikari counts) is one return, so held/repeated Sa isn't over-counted."""
    returns = 0
    prev_was_sa = False
    for n in sounding:
        is_sa = _landing_swara(n) == "S"
        if is_sa and not prev_was_sa:
            returns += 1
        prev_was_sa = is_sa
    return returns


def check_manjha(cell: LeadPhrase, *, mukhada: LeadPhrase, window_beats: float,
                  raga: str) -> CellChecks:
    """Return the manjha's structural violations (empty == a true return-cell). Pure.

    A manjha is COMPLEMENTARY to the mukhada — head x3-4, then the manjha carries the line to
    the sam and the head re-enters: one cohesive cycle. The diagnosed failure was "long bars of
    random notes with no definition and no return". The checkable core:
      * ARRIVES AT THE SAM — the cell fills its whole window (within loose bounds), so the head
        re-enters on time instead of after a dead gap or a truncation;
      * LEADS BACK INTO THE HEAD — the last note is a stepwise lead-in to the mukhada's first
        swara (the shared `_seam_violation` rule);
      * HAS A RHYTHMIC SHAPE — not a run of identical durations.
    Requires the cached mukhada cell — CROSS-CELL awareness; a manjha cannot be verified (or
    honestly composed) without knowing the head it returns to.
    """
    notes = cell.notes
    sounding = _sounding(notes)
    if not sounding:
        return CellChecks(hard=("the manjha has no sounding notes — it must develop the mukhada's material",))

    hard: list[str] = []
    craft: list[str] = []
    # The manjha is the raga's LOW, unhurried stretch — the one place with room to state the
    # raga's central swara plainly. The 2026-09-14 render's manjha contained no Ma AT ALL, in a
    # raga whose vadi is Ma: a section spent entirely away from the note the raga gravitates to.
    ang = _ang_violation(sounding, raga, "manjha",
                         also_accept=[_landing_swara(n) for n in _sounding(mukhada.notes)])
    if ang:
        craft.append(ang)
    vadi = RAGAS[raga]["vadi"]
    if vadi not in {_landing_swara(n) for n in sounding}:
        craft.append(f"the manjha never sounds {vadi}, this raga's VADI — the bridge is the "
                    f"calmest stretch in the piece and the natural place to let the raga's "
                    f"central swara ring; a manjha that avoids it develops the scale, not the raga")
    total = sum(n.dur for n in notes)
    if total < _CELL_FILL_MIN * window_beats:
        hard.append(f"the manjha fills only {total:g} of its {window_beats:g}-beat window — carry "
                    f"the line all the way to the closing sam, where the mukhada re-enters")
    else:
        over = _overrun_violation(notes, window_beats, "manjha",
                                  "land the final note ON the closing sam")
        if over:
            hard.append(over)

    seam = _seam_violation(sounding[-1], mukhada, raga, "manjha")
    if seam:
        hard.append(seam)

    if _rhythmically_flat(sounding):
        craft.append("the manjha is rhythmically flat — every note is the same length; develop the "
                    "head's rhythm, don't pace out even notes")

    # LOWER-REGISTER BRIDGE (Pandit Arvind Parikh; Masitkhani-gat descriptions, 2026-07-15): the
    # manjha takes the melody DOWN into the mandra octave — it is part of the sthayi and the ANTARA,
    # not the manjha, owns the taar. So it must DIP into the lower octave and must NOT climb into the
    # taar. This is what makes it a bridge that CONTRASTS the mukhada (by register) before the ascent.
    if not any(_landing_oct(n) < 0 for n in sounding):
        craft.append("the manjha never dips into the mandra (lower) octave — it must take the melody "
                    "DOWN below home; the manjha is the low bridge before the antara climbs")
    if any(_landing_oct(n) >= 1 for n in sounding):
        craft.append("the manjha reaches the taar (upper) octave — keep it in the mandra / lower-madhya "
                    "register; the ANTARA owns the upper octave, the manjha stays low")

    hard += nyas_violations(cell.notes, raga)
    craft += _ornament_density_notes(cell.notes, "manjha")
    return CellChecks(tuple(hard), tuple(craft))


def verify_manjha(cell: LeadPhrase, *, mukhada: LeadPhrase, window_beats: float,
                  raga: str) -> list[str]:
    """The manjha's HARD faults only — what drives a re-roll. `check_manjha` adds the
    reported craft notes."""
    return list(check_manjha(cell, mukhada=mukhada, window_beats=window_beats, raga=raga).hard)


def _quote_present(swaras: list[str], quote: list[str], max_gap: int) -> bool:
    """Does `quote` appear in `swaras` as an in-order subsequence with at most `max_gap`
    interleaved notes between consecutive quote tones? Octave-agnostic (swara names only) —
    the antara restates the head UP an octave, so pitch identity would be wrong. The same
    bounded-gap idea as Rasik's fuzzy pakad tier: a passing note doesn't break the quote."""
    for start in (i for i, s in enumerate(swaras) if s == quote[0]):
        i, matched = start, 1
        while matched < len(quote):
            nxt = next((j for j in range(i + 1, min(i + 2 + max_gap, len(swaras)))
                        if swaras[j] == quote[matched]), None)
            if nxt is None:
                break
            i, matched = nxt, matched + 1
        if matched == len(quote):
            return True
    return False


def _arc_violations(sounding: list[LeadNote], cell_name: str) -> list[str]:
    """The shared REGISTER-ARC rules for a climbing cell (antara, taan): open in the middle
    octave, actually reach the taar, peak past the midpoint, and come down after the peak.
    The upper octave is earned — a cell that starts high, peaks early, or exits on its own
    climax has no arc, just altitude."""
    viol: list[str] = []
    if _landing_oct(sounding[0]) >= 1:
        viol.append(f"the {cell_name} opens already in the taar octave — start in the middle "
                    f"(madhya) octave and CLIMB; the ascent is the {cell_name}'s story")
    if max(_landing_oct(n) for n in sounding) < 1:
        viol.append(f"the {cell_name} never reaches the taar octave — its climb must enter the "
                    f"upper octave (oct +1) for the composition's peak")
        return viol
    pitches = [_landing_pitch(n) for n in sounding]
    peak = pitches.index(max(pitches))
    elapsed = sum(n.dur for n in sounding[:peak])
    total = sum(n.dur for n in sounding)
    if elapsed < _PEAK_MIN_POS * total:
        viol.append(f"the {cell_name}'s highest note arrives too early — build gradually and "
                    f"reach the peak past the midpoint, then descend")
    if peak == len(sounding) - 1:
        viol.append(f"the {cell_name} ends ON its highest note — after the peak it must DESCEND "
                    f"and resolve; the climax is not the exit")
    return viol


def check_antara(cell: LeadPhrase, *, mukhada: LeadPhrase, window_beats: float,
                  raga: str, with_amad: bool = False) -> CellChecks:
    """Return the antara's structural violations (empty == a true second movement). Pure.

    The diagnosed failure: "lift into the upper octave" produced random high notes — the LLM
    read 'contrast' as 'new tune'. An antara is the SECOND HALF OF THE SAME GAT, and its arc
    is checkable:
      * QUOTES THE HEAD — the mukhada's opening swaras appear (in order, small gaps allowed,
        any octave) somewhere in the antara's first half: same DNA, not a new melody;
      * OPENS IN THE MIDDLE OCTAVE — the first note is not already in the taar (the climb is
        the point);
      * REACHES THE TAAR — the line actually enters the upper octave;
      * PEAKS LATE, THEN DESCENDS — the highest note arrives past the phrase's midpoint and
        is not the final note (the arc must come back down);
      * RESTS ON MADHYA SA — the last note is Sa at or below the home octave, the hand-off
        into the returning mukhada;
      * FITS ITS WINDOW — end-anchored, so an overrun truncates its own resolution (this exact
        failure was heard live: a verified ends-on-Sa antara clipped at the window edge and the
        piece heard it end on Re).
    With `with_amad` (Parikh's four-line model, 2026-07-20), the AMAD owns the homecoming —
    the antara keeps its whole arc (climb, late peak, descend after it) but is NOT required to
    come all the way down to madhya Sa itself; `verify_amad` holds the descent line to that.
    """
    notes = cell.notes
    sounding = _sounding(notes)
    if not sounding:
        return CellChecks(hard=("the antara has no sounding notes — it must develop the gat in the upper register",))

    hard: list[str] = []
    craft: list[str] = []
    total = sum(n.dur for n in notes)
    if total < _CELL_FILL_MIN * window_beats:
        hard.append(f"the antara fills only {total:g} of its {window_beats:g}-beat window — carry "
                    f"the arc all the way to the closing sam")
    else:
        over = _overrun_violation(notes, window_beats, "antara",
                                  "land the resolving Sa ON the closing sam")
        if over:
            hard.append(over)
    head_swaras = [_landing_swara(n) for n in _sounding(mukhada.notes)][:_ANTARA_QUOTE_LEN]
    half = sounding[:max(1, len(sounding) // 2)]
    if head_swaras and not _quote_present([_landing_swara(n) for n in half],
                                          head_swaras, _QUOTE_MAX_GAP):
        craft.append(f"the antara never quotes the mukhada's opening ({' '.join(head_swaras)}) — "
                    f"OPEN by restating it (an octave up is idiomatic); the antara is the second "
                    f"half of the SAME gat, not a new tune")

    craft.extend(_arc_violations(sounding, "antara"))

    last = sounding[-1]
    if not with_amad and (_landing_swara(last) != "S" or _landing_oct(last) >= 1):
        _cadence_bucket(_landing_swara(last), raga, hard, craft).append(f"the antara ends on {_landing_swara(last)} (oct {_landing_oct(last):+d}) — "
                    f"descend and come to rest on madhya Sa, handing off into the returning mukhada")

    # RHYTHMIC VARIETY (Sujit, 2026-07-16: the antara's harmonized guitar line was "single long
    # notes, no variation" — 26 two-beat notes): the second theme is still a THEME, so it mixes
    # note values (8ths and quarters against the held notes), same floor the taan is held to.
    if len({round(n.dur, 4) for n in sounding}) < _TAAN_MIN_DURATIONS:
        craft.append(f"the antara uses fewer than {_TAAN_MIN_DURATIONS} distinct note values — a "
                    f"wall of even long notes reads as a drone, not a theme; mix 8ths and "
                    f"quarters against the held notes")

    hard += nyas_violations(cell.notes, raga)
    craft += _ornament_density_notes(cell.notes, "antara")
    return CellChecks(tuple(hard), tuple(craft))


def verify_antara(cell: LeadPhrase, *, mukhada: LeadPhrase, window_beats: float,
                  raga: str, with_amad: bool = False) -> list[str]:
    """The antara's HARD faults only — what drives a re-roll. `check_antara` adds the
    reported craft notes."""
    return list(check_antara(cell, mukhada=mukhada, window_beats=window_beats, raga=raga, with_amad=with_amad).hard)


def check_amad(cell: LeadPhrase, *, mukhada: LeadPhrase, window_beats: float,
                raga: str, antara_last: str | None = None) -> CellChecks:
    """Return the amad's structural violations (empty == a true composed return). Pure.

    The amad is Parikh's FOURTH line — the composed descent that "brings you down to the
    point where the composition started, and thus completes the cycle" (2026-07-20 gat
    research). It occupies the antara section's final avartan, so the return to the head is
    COMPOSED, not left to the antara's tail. The checkable core:
      * FLOWS OUT OF THE ANTARA — when the antara's landing swara is known, the amad opens
        within a step or two of it (the fourth line continues the third, no jump-cut);
      * NET DESCENT, NO RE-PEAK — the line ends below where it began and never eddies more
        than a couple of semitones above its opening (a descent may breathe, never re-climb);
      * LANDS AT HOME — the final note sits at or below the madhya and leads into the
        mukhada's first swara (the shared return-seam rule): down to where it all started;
      * FITS ITS WINDOW — end-anchored like the manjha/antara (an overrun clips the very
        re-entry it composes);
      * HAS A RHYTHMIC SHAPE — not a run of identical durations.
    """
    notes = cell.notes
    sounding = _sounding(notes)
    if not sounding:
        return CellChecks(hard=("the amad has no sounding notes — it must compose the descent back to the head",))

    hard: list[str] = []
    craft: list[str] = []
    total = sum(n.dur for n in notes)
    if total < _CELL_FILL_MIN * window_beats:
        hard.append(f"the amad fills only {total:g} of its {window_beats:g}-beat window — carry "
                    f"the descent all the way to the closing sam, where the mukhada re-enters")
    else:
        over = _overrun_violation(notes, window_beats, "amad",
                                  "land the re-entry note ON the closing sam")
        if over:
            hard.append(over)

    first, last = sounding[0], sounding[-1]
    if antara_last is not None:
        steps = _scale_steps_between(_landing_swara(first), antara_last, raga)
        if steps > _SEAM_MAX_STEPS:
            hard.append(f"the amad opens on {_landing_swara(first)}, a leap from the antara's "
                        f"landing {antara_last} — the amad is the antara's own second line: "
                        f"open on or within a step or two of {antara_last} and descend from there")
    first_pitch = _landing_pitch(first)
    if _landing_pitch(last) >= first_pitch:
        craft.append("the amad does not DESCEND — it must end lower than it begins; the amad's "
                    "whole job is bringing the melody down to where the composition started")
    if max(map(_landing_pitch, sounding)) > first_pitch + _AMAD_RISE_MAX:
        craft.append("the amad climbs above its opening — the peak belongs to the antara; the "
                    "amad may eddy a step but its direction is DOWN, all the way home")
    if _landing_oct(last) > 0:
        craft.append(f"the amad ends in the taar (oct {_landing_oct(last):+d}) — come to rest at "
                    f"or below the madhya, where the returning mukhada picks up")
    seam = _seam_violation(last, mukhada, raga, "amad")
    if seam:
        hard.append(seam)

    if _rhythmically_flat(sounding):
        craft.append("the amad is rhythmically flat — every note is the same length; a composed "
                    "descent still phrases (mix note values on the way down)")

    hard += nyas_violations(cell.notes, raga)
    craft += _ornament_density_notes(cell.notes, "amad")
    return CellChecks(tuple(hard), tuple(craft))


def verify_amad(cell: LeadPhrase, *, mukhada: LeadPhrase, window_beats: float,
                raga: str, antara_last: str | None = None) -> list[str]:
    """The amad's HARD faults only — what drives a re-roll. `check_amad` adds the
    reported craft notes."""
    return list(check_amad(cell, mukhada=mukhada, window_beats=window_beats, raga=raga, antara_last=antara_last).hard)


def check_outro(cell: LeadPhrase, *, mukhada: LeadPhrase | None, raga: str) -> CellChecks:
    """Return the outro's violations (empty == an ending that RESOLVES the raga). Pure.

    The outro was the last unverified part of the gat, and it showed: the 2026-09-14 render
    ended on `D R S` and a long Sa — legal, and so unspecific it could close any raga sharing
    the scale. An ending should compress what the listener has learned, so the requirements
    are the two that make it a conclusion rather than a stop:
      * IT QUOTES THE RAGA — one of the raga's own movements, or the gat head's own line;
      * IT COMES HOME — the final note is Sa, held, so the piece resolves rather than halting.
    Everything else about an outro (how long, how ornamented, whether a tihai closes it) stays
    the composer's.
    """
    sounding = _sounding(cell.notes)
    if not sounding:
        return CellChecks(hard=("the outro has no sounding notes — it is the piece's resolution",))
    hard: list[str] = []
    craft: list[str] = []
    head = [_landing_swara(n) for n in _sounding(mukhada.notes)] if mukhada else None
    ang = _ang_violation(sounding, raga, "outro", also_accept=head)
    if ang:
        craft.append(ang)
    last = sounding[-1]
    if _landing_swara(last) != "S":
        _cadence_bucket(_landing_swara(last), raga, hard, craft).append(f"the outro ends on {_landing_swara(last)}, not Sa — the piece comes HOME: "
                    f"the last note is Sa, held long enough to feel final")
    elif last.dur < _INTRO_HELD_SA:
        craft.append(f"the outro's final Sa lasts only {last.dur:g} beats — hold it (>= "
                    f"{_INTRO_HELD_SA:g}) so the ending lands instead of stopping")
    hard += nyas_violations(cell.notes, raga)
    craft += _ornament_density_notes(cell.notes, "outro")
    return CellChecks(tuple(hard), tuple(craft))


def verify_outro(cell: LeadPhrase, *, mukhada: LeadPhrase | None, raga: str) -> list[str]:
    """The outro's HARD faults only — what drives a re-roll. `check_outro` adds the
    reported craft notes."""
    return list(check_outro(cell, mukhada=mukhada, raga=raga).hard)


def check_taan(cell: LeadPhrase, *, motif: list[str], window_beats: float,
                raga: str, reentry: str | None = None, bpm: float = 120.0) -> CellChecks:
    """Return the developed taan's (taan_long/solo) structural violations. Pure.

    A taan is the composition's PEAK, not "the scale, quickly". The checkable core of a
    concert taan (the taste — which style, which phrases — stays the LLM's):
      * GROWS FROM THE MOTIF — the piece's shared seed appears (in order, small gaps, any
        octave) somewhere in the taan: one journey, not unrelated fast phrases;
      * THE EARNED ARC — opens madhya, enters the taar, peaks ONCE past the midpoint, and
        comes down after the peak (`_arc_violations`, shared with the antara);
      * LANDS — the final note is a resting swara (Sa / vadi / samvadi), or, with a returning
        head, a step into its first swara with no silence before the sam;
      * FLOWS TO ITS PLAN — the phrase plan (`TaanPhrase`) fills the window, builds its pulse
        into ONE late climax and keeps it through the cadence; the notes run at each phrase's
        pulse, change speed only at its boundaries, never rest, never jump, and peak inside
        the climax phrase (`_taan_plan_checks`).
    """
    notes = cell.notes
    sounding = _sounding(notes)
    if not sounding:
        return CellChecks(hard=("the taan has no sounding notes — it is the composition's developed peak",))

    hard: list[str] = []
    craft: list[str] = []
    hard += _motion_violations(sounding, raga, "taan")     # direction + scalar run: both HARD

    total = sum(n.dur for n in notes)
    if abs(total - window_beats) > _TAAN_EPS:
        hard.append(f"the taan lasts {total:g} beats but its window is exactly {window_beats:g} — "
                    f"it runs without a break right up to the closing sam, so its notes fill the "
                    f"window exactly (a short taan leaves a gap before the sam, a long one is cut)")

    quote = motif[:_TAAN_QUOTE_LEN]
    if quote and not _quote_present([_landing_swara(n) for n in sounding], quote, _QUOTE_MAX_GAP):
        craft.append(f"the taan never grows from the piece's motif ({' '.join(quote)}) — restate "
                    f"or clearly derive from it; the taan develops the composition's ONE idea, "
                    f"it does not introduce a new tune at speed")

    arc = _arc_violations(sounding, "taan")
    early = [v for v in arc if "arrives too early" in v]
    hard += early                          # the climax belongs to the END (Sujit, 2026-10-12)
    craft.extend(v for v in arc if v not in early)

    last = sounding[-1]
    if reentry is not None:
        # The head returns on the next sam and ITS first note is the resolution: the taan runs
        # straight into it — its last note a step into that swara, with no silence before it.
        seam = _seam_violation_to(last, reentry, raga, "taan",
                                  "the returning mukhada's first swara on the next sam")
        if seam:
            hard.append(seam)
        if notes and notes[-1].rest:
            hard.append(f"the taan stops before the sam — a rest at its end leaves a gap before "
                        f"the returning mukhada; run the final approach right up to the sam and "
                        f"into {reentry}")
    else:
        resting = _resting_swaras(raga)
        if _landing_swara(last) not in resting:
            hard.append(f"the taan ends on {_landing_swara(last)}, not a resting swara "
                        f"({' '.join(sorted(resting))}) — the final phrase must resolve to the "
                        f"sam so the landing feels inevitable, not abrupt")

    plan_hard, plan_craft = _taan_plan_checks(cell, window_beats, reentry is not None, taan_pulse(bpm))
    hard += plan_hard
    craft += plan_craft
    hard += nyas_violations(cell.notes, raga)
    craft += _ornament_density_notes(cell.notes, "taan")
    return CellChecks(tuple(hard), tuple(craft))


def verify_taan(cell: LeadPhrase, *, motif: list[str], window_beats: float,
                raga: str, reentry: str | None = None, bpm: float = 120.0) -> list[str]:
    """The taan's HARD faults only — what drives a re-roll. `check_taan` adds the
    reported craft notes."""
    return list(check_taan(cell, motif=motif, window_beats=window_beats, raga=raga,
                           reentry=reentry, bpm=bpm).hard)


def _taan_plan_checks(cell: LeadPhrase, window_beats: float,
                      into_head: bool, opening: int = 4) -> tuple[list[str], list[str]]:
    """The taan's FLOW: its phrase plan is sound, and its notes follow it. Pure.

    HARD (re-rolled) — the plan and the notes disagreeing is a broken taan, whatever the taste:
    a missing or malformed plan, a plan that does not build (`_taan_plan_shape`), and notes that
    leave their phrase's pulse, cross a phrase boundary, rest, jump, or peak outside the climax
    (`_taan_note_faults`). CRAFT (reported): each phrase reaching the height it planned, and the
    builds climbing rather than sagging before the climax."""
    phrases = cell.phrase_plan.taan_phrases or []
    if not phrases:
        return ([f"the taan has no phrase plan — fill phrase_plan.taan_phrases: its phrases in "
                 f"order (statement, builds, ONE climax, cadence), each with its beats and its "
                 f"pulse (subdivision, notes per matra: {opening} = {_pulse_name(opening)} at this "
                 f"tempo), summing to {window_beats:g}"], [])
    shape = _taan_plan_shape(phrases, window_beats, opening)
    if shape:
        return shape, []
    groups = _notes_by_phrase(cell.notes, phrases)
    if isinstance(groups, str):
        return [groups], []
    hard = _taan_note_faults(groups, phrases, into_head)
    return hard, _taan_reach_notes(groups, phrases)


def _phrase_bounds(phrases: list[TaanPhrase]) -> list[tuple[float, float]]:
    """Each phrase's (start, end) in beats from the taan's start."""
    out, t = [], 0.0
    for ph in phrases:
        out.append((t, t + ph.beats))
        t += ph.beats
    return out


def _pulse_name(subdivision: int) -> str:
    return {2: "dugun", 3: "tigun", 4: "chaugun", 6: "chhagun", 8: "athgun"}.get(subdivision, f"{subdivision}/matra")


def _taan_plan_shape(phrases: list[TaanPhrase], window_beats: float, opening: int = 4) -> list[str]:
    """What is wrong with the PLAN itself, before any note is read. Pure."""
    bad = [f"phrase {i + 1}: " + (f"role '{ph.role}'" if ph.role not in _TAAN_ROLES else
                                  f"subdivision {ph.subdivision}")
           for i, ph in enumerate(phrases)
           if ph.role not in _TAAN_ROLES or ph.subdivision not in _TAAN_PULSES]
    if bad:
        return [f"the taan plan uses unknown values ({'; '.join(bad)}) — roles are "
                f"{' / '.join(_TAAN_ROLES)}, subdivisions {' / '.join(map(str, _TAAN_PULSES))}"]
    viol: list[str] = []
    if any(ph.beats < 1 - _TAAN_EPS or abs(ph.beats - round(ph.beats)) > _TAAN_EPS
           for ph in phrases):
        viol.append("every taan phrase lasts a whole number of matras (at least one) — the "
                    "speed changes on a matra, at the phrase boundary")
    planned = sum(ph.beats for ph in phrases)
    if abs(planned - window_beats) > _TAAN_EPS:
        viol.append(f"the taan's phrases sum to {planned:g} beats, not its {window_beats:g}-beat "
                    f"window — plan the whole run up to the sam")
    climaxes = [i for i, ph in enumerate(phrases) if ph.role == "climax"]
    if len(climaxes) != 1:
        return viol + [f"the taan plans {len(climaxes)} climax phrases — exactly ONE, in its "
                       f"later part, followed by the cadence"]
    if phrases[-1].role != "cadence":
        viol.append("the taan's last phrase is the cadence — after the climax, a phrase that "
                    "keeps the momentum and runs into the sam")
    return viol + _taan_build_faults(phrases, climaxes[0], window_beats, opening)


def _taan_build_faults(phrases: list[TaanPhrase], peak: int, window_beats: float, opening: int = 4) -> list[str]:
    """Does the plan BUILD — the pulse never slows on the way up, the climax lands in the later
    half, and what follows it is short and keeps moving? Pure."""
    viol: list[str] = []
    if phrases[0].subdivision < opening:
        viol.append(f"the taan opens at {_pulse_name(phrases[0].subdivision)} — launch it straight "
                    f"at {_pulse_name(opening)} ({opening} notes per matra, every note {1 / opening:g}, "
                    f"the base pulse at this tempo) and keep that pulse; quicken at most one step")
    rising = [ph.subdivision for ph in phrases[:peak + 1]]
    if any(b < a for a, b in zip(rising, rising[1:])):
        viol.append(f"the taan's pulse slows on the way to its climax ({' -> '.join(map(str, rising))}"
                    f" notes per matra) — build: keep or raise the subdivision at each phrase "
                    f"boundary until the climax")
    start, _ = _phrase_bounds(phrases)[peak]
    if start < _TAAN_CLIMAX_FROM * window_beats - _TAAN_EPS:
        viol.append(f"the climax phrase starts at beat {start:g} of {window_beats:g} — reserve it "
                    f"for the later half; build towards it")
    after = phrases[peak + 1:]
    if sum(ph.beats for ph in after) > _TAAN_AFTER_CLIMAX_MAX * window_beats + _TAAN_EPS:
        viol.append(f"{sum(ph.beats for ph in after):g} beats follow the climax — at most "
                    f"{_TAAN_AFTER_CLIMAX_MAX * window_beats:g}: a short cadence, not a long descent")
    floor = min(phrases[peak].subdivision, opening)
    if any(ph.subdivision < floor for ph in after):
        viol.append(f"the cadence slows below {floor} notes per matra — keep the climax's momentum "
                    f"all the way into the sam")
    return viol


def _notes_by_phrase(notes: list[LeadNote],
                     phrases: list[TaanPhrase]) -> list[list[LeadNote]] | str:
    """The notes grouped by the phrase they sound in, or the fault when a note CROSSES a phrase
    boundary (the speed change must fall between notes). Notes past the plan's end go to the
    last phrase — the fill check reports the overrun. Pure."""
    bounds = _phrase_bounds(phrases)
    groups: list[list[LeadNote]] = [[] for _ in phrases]
    t, k = 0.0, 0
    for note in notes:
        while k < len(bounds) - 1 and t >= bounds[k][1] - _TAAN_EPS:
            k += 1
        if k < len(bounds) - 1 and t + note.dur > bounds[k][1] + _TAAN_EPS:
            return (f"a note at beat {t:g} rings across the boundary between phrase {k + 1} and "
                    f"{k + 2} (beat {bounds[k][1]:g}) — end each phrase exactly on its boundary, "
                    f"where the pulse changes")
        groups[k].append(note)
        t += note.dur
    return groups


def _taan_note_faults(groups: list[list[LeadNote]], phrases: list[TaanPhrase],
                      into_head: bool) -> list[str]:
    """Where the notes leave the plan: rests, notes off their phrase's pulse, leaps inside a
    phrase, and a highest note outside the climax phrase. Pure."""
    viol: list[str] = []
    if any(n.rest for g in groups for n in g):
        viol.append("the taan rests mid-flight — a taan never stops: replace each rest with "
                    "notes at the phrase's pulse")
    for i, (group, ph) in enumerate(zip(groups, phrases)):
        last = into_head and i == len(groups) - 1
        off = _off_pulse(group, ph.subdivision, last)
        if off:
            viol.append(f"phrase {i + 1} ({ph.role}, {_pulse_name(ph.subdivision)}: every note "
                        f"{1 / ph.subdivision:g} beats) has {len(off)} note(s) off its pulse "
                        f"({', '.join(off[:4])}) — keep the phrase at ONE pulse; only its final "
                        f"note may ring longer (up to {_TAAN_PHRASE_END_MAX:g} beat), and a "
                        f"gamak note up to {_TAAN_GAMAK_MAX:g}")
        jumps = _leaps(group)
        if jumps:
            viol.append(f"phrase {i + 1} jumps {', '.join(jumps[:3])} — a taan runs: move by step "
                        f"or zig-zag, and change register across phrases, not inside one")
    split = [f"{n.bol} on {_landing_swara(n)}" for g in groups for n in g
             if n.bol in BOL_WORDS and is_compound(n.bol)]
    if split:
        viol.append(f"{len(split)} taan note(s) carry a compound stroke ({', '.join(split[:3])}) — a "
                    f"dir/dara splits its note into faster strokes and breaks the phrase's pulse; "
                    f"in a taan every note is ONE stroke: alternate da and ra")
    late = _peak_share(groups)
    if late is not None and late < _TAAN_PEAK_FROM - _TAAN_EPS:
        viol.append(f"the taan's highest note sounds at {late:.0%} of the run — save it for past "
                    f"{_TAAN_PEAK_FROM:.0%}, near the END of the climax phrase, so the cadence after "
                    f"it is a short fast run into the sam, not a long cascade down")
    peak = _peak_phrase(groups)
    climax = next(i for i, ph in enumerate(phrases) if ph.role == "climax")
    if peak is not None and peak != climax:
        viol.append(f"the taan's highest note sounds in phrase {peak + 1} ({phrases[peak].role}), "
                    f"not in the climax (phrase {climax + 1}) — the top of the run belongs to "
                    f"the climax")
    return viol


def _off_pulse(group: list[LeadNote], subdivision: int, into_head: bool) -> list[str]:
    """The durations in a phrase that leave its pulse (as "0.5 (note 3)" labels). Every note is
    one pulse long, except a gamak note (up to `_TAAN_GAMAK_MAX`, whole pulses) and the phrase's
    last note (up to `_TAAN_PHRASE_END_MAX`, or `_TAAN_FINAL_INTO_SAM_MAX` when it runs into the
    returning head). Pure."""
    step = 1.0 / subdivision
    out: list[str] = []
    for j, n in enumerate(group):
        whole = abs(n.dur / step - round(n.dur / step)) < _TAAN_EPS
        if abs(n.dur - step) < _TAAN_EPS:
            continue
        if j == len(group) - 1:
            cap = _TAAN_FINAL_INTO_SAM_MAX if into_head else _TAAN_PHRASE_END_MAX
            if whole and n.dur <= cap + _TAAN_EPS:
                continue
        elif n.gamak_with and whole and n.dur <= _TAAN_GAMAK_MAX + _TAAN_EPS:
            continue
        out.append(f"{n.dur:g} (note {j + 1})")
    return out


def _leaps(group: list[LeadNote]) -> list[str]:
    """Moves wider than `_TAAN_LEAP_MAX` semitones between consecutive sounding notes."""
    sounding = _sounding(group)
    return [f"{_landing_swara(a)}->{_landing_swara(b)} ({abs(_landing_pitch(b) - _landing_pitch(a))} st)"
            for a, b in zip(sounding, sounding[1:])
            if abs(_landing_pitch(b) - _landing_pitch(a)) > _TAAN_LEAP_MAX]


def _phrase_top(group: list[LeadNote]) -> int | None:
    pitches = [_landing_pitch(n) for n in group if not n.rest]
    return max(pitches) if pitches else None


def _pitch_label(pitch: int) -> str:
    """A pitch (semitones from madhya Sa) in sargam with its octave mark: "g'" taar, "P." mandra."""
    octave, semitone = divmod(pitch, 12)
    swara = next((sw for sw, st in SWARAS.items() if st == semitone), "?")
    return swara + ("'" * octave if octave > 0 else "." * -octave)


def _peak_share(groups: list[list[LeadNote]]) -> float | None:
    """How far into the taan (share of its length) its highest pitch FIRST sounds."""
    notes = [n for g in groups for n in g]
    total = sum(n.dur for n in notes)
    sounding = [(i, _landing_pitch(n)) for i, n in enumerate(notes) if not n.rest]
    if not sounding or total <= 0:
        return None
    top = max(p for _, p in sounding)
    first = next(i for i, p in sounding if p == top)
    return sum(n.dur for n in notes[:first]) / total


def _peak_phrase(groups: list[list[LeadNote]]) -> int | None:
    """The phrase holding the taan's FIRST arrival at its highest pitch."""
    tops = [_phrase_top(g) for g in groups]
    known = [t for t in tops if t is not None]
    return tops.index(max(known)) if known else None


def _taan_reach_notes(groups: list[list[LeadNote]], phrases: list[TaanPhrase]) -> list[str]:
    """CRAFT: does each phrase reach the height it planned, and do the phrases climb (not sag)
    on the way to the climax? Reported, never re-rolled. Pure."""
    notes: list[str] = []
    missed = [f"phrase {i + 1} planned {_pitch_label(planned)}, reached {_pitch_label(top)}"
              for i, (g, ph) in enumerate(zip(groups, phrases))
              if ph.reach in SWARAS and (top := _phrase_top(g)) is not None
              and top != (planned := (ph.reach_oct or 0) * 12 + SWARAS[ph.reach])]
    if missed:
        notes.append("the taan's register plan and its notes disagree: " + "; ".join(missed[:3]))
    climax = next(i for i, ph in enumerate(phrases) if ph.role == "climax")
    tops = [_phrase_top(g) for g in groups[:climax + 1]]
    known = [t for t in tops if t is not None]
    if any(b < a for a, b in zip(known, known[1:])):
        notes.append("the taan's phrases sag before the climax — each build should reach at least "
                     "as high as the one before it (badhat: widen the range, then the top)")
    return notes


def check_fill(cell: LeadPhrase, *, mukhada: LeadPhrase, window_beats: float,
                raga: str) -> CellChecks:
    """Return a mukhada taan-FILL's structural violations (empty == a clean splice). Pure.

    The fill is the classic gat move, and since the 2026-07-20 gat research it follows the
    tradition's geometry: the taan LAUNCHES FROM THE SAM and runs the FRONT of the avartan
    (the improvised region, matras ~1-11), then the head's own APPROACH — its final matras,
    the mukhda anacrusis — re-enters and lands the next sam. (The old splice cut the BACK
    half, deleting exactly the approach the tradition keeps sacrosanct.) Code owns the splice
    (where the head re-enters); this owns the fill's checkable grammar:
      * IT IS A TAAN — sixteenth notes (<= 0.25 beats) throughout, with at most one longer
        final landing note;
      * IT FITS THE CUT — the cell fills its front-of-avartan window almost exactly (a splice
        has no room for slack; `window_beats` IS the re-entry beat);
      * IT RESOLVES INTO THE RE-ENTERING APPROACH — the return-seam rule, aimed at the swara
        the head sounds AT the re-entry beat (not the head's first note, which lands the
        NEXT sam after the approach has run).
    """
    notes = cell.notes
    sounding = _sounding(notes)
    if not sounding:
        return CellChecks(hard=("the taan fill has no sounding notes — it must be a fast sixteenth-note run",))

    hard: list[str] = []
    craft: list[str] = []
    slow = [n for n in sounding[:-1] if n.dur > _TAAN_NOTE_MAX]
    if slow or sounding[-1].dur > _TAAN_LANDING_MAX:
        craft.append(f"a short taan moves in SIXTEENTHS — every note <= {_TAAN_NOTE_MAX:g} beats "
                    f"(only the final landing note may be longer, up to {_TAAN_LANDING_MAX:g})")

    total = sum(n.dur for n in notes)
    if not (_TAAN_FILL_MIN * window_beats <= total <= _CELL_FILL_MAX * window_beats):
        hard.append(f"the fill lasts {total:g} beats but must fill its {window_beats:g}-beat cut "
                    f"almost exactly — it is spliced into the mukhada, so there is no slack")

    hard += _motion_violations(sounding, raga, "taan fill")

    seam = _seam_violation_to(sounding[-1], reentry_swara(mukhada, window_beats), raga,
                              "taan fill", "the head's re-entering approach")
    if seam:
        hard.append(seam)

    return CellChecks(tuple(hard), tuple(craft))


def verify_fill(cell: LeadPhrase, *, mukhada: LeadPhrase, window_beats: float,
                raga: str) -> list[str]:
    """The fill's HARD faults only — what drives a re-roll. `check_fill` adds the
    reported craft notes."""
    return list(check_fill(cell, mukhada=mukhada, window_beats=window_beats, raga=raga).hard)


