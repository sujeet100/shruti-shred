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
"""

from __future__ import annotations

from collections import Counter

from typing import Final

from crew.contracts import LeadNote, LeadPhrase
from gats import GAT_FRAMES
from chalan import ang_matches, longest_scalar_run
from raga import RAGAS, direction_violations, SWARAS

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
_MUKHADA_PULSE_SHARE: Final = 0.35  # one note value must carry at least this much of the head
_MUKHADA_LONG: Final = 2.0          # ...and it still RESTS somewhere: one half-note+ nyas

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
_INTRO_MIN_PHRASES: Final = 3       # at least this many rest-separated phrases (musical sentences)
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
# intro's recurring motif (drawn from the mukhada head, so the gat arrives as its culmination),
# every phrase but the final settle carries its opening, the full motif is stated somewhere, the
# opening phrase stays a narrow fragment, and the intro's widest reach arrives past the midpoint.
_INTRO_MOTIF_MIN: Final = 2         # the declared motif is at least this many swaras...
_INTRO_MOTIF_MAX: Final = 5         # ...and at most this many (a kernel, not a whole line)
_INTRO_ANCHOR_LEN: Final = 2        # each phrase carries at least this opening fragment of the motif
_INTRO_OPEN_SPAN: Final = 7         # semitones: the FIRST phrase stays a narrow fragment around home
_INTRO_PEAK_MIN_POS: Final = 0.5    # the intro's highest note arrives past this fraction (badhat)
# A meend is an ORNAMENT — and the render anchors it on its TARGET, so a meend note is HEARD
# at the target, not the written swara. The 2026-07-16 render put a meend on ~100% of alap
# notes (all toward Sa): the whole exposition audibly collapsed onto one repeated note. The
# audible-line checks catch that collapse; this cap names the cause in the feedback.
_INTRO_MEEND_MAX_SHARE: Final = 0.5


def _real_meend(note: LeadNote) -> bool:
    """A meend that actually GLIDES — its target differs from the written pitch (the LLM
    sometimes stamps `meend_swara == swara`, a no-op the placement strips anyway)."""
    if note.rest or note.meend_swara is None:
        return False
    target_oct = note.meend_oct if note.meend_oct is not None else note.oct
    return (note.meend_swara, target_oct) != (note.swara, note.oct)

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
# concert taan: it grows from the MOTIF, climbs to ONE late peak, resolves to a resting swara,
# and shapes its speed as burst-and-space, not a wall of even sixteenths.
_TAAN_QUOTE_LEN: Final = 4          # how much of the motif the taan must audibly grow from
_TAAN_BURST_LEN: Final = 4          # a real burst: at least this many consecutive sixteenths
_TAAN_BURST_NOTE: Final = 0.25      # ...each at most a sixteenth
_TAAN_SPACE_BEATS: Final = 1.0      # "space": a rest, or a note held at least this long
_TAAN_MIN_DURATIONS: Final = 3      # distinct sounding durations — mixed subdivisions, not one wall
# The CADENTIAL RUN (Sujit, 2026-07-16: "taans end with complex 8th/16th notes and land on Sa —
# that creates tension"): a burst must END inside the final stretch of the taan, so the landing
# is arrived at in FLIGHT, not walked to on long notes.
_TAAN_END_BURST_WINDOW: Final = 0.3  # ...a burst ends within this final fraction of the taan
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
    """The swaras a mukhada may cadence onto — Sa (always a nyas) plus the raga's vadi/samvadi.
    Landing here is how the head resolves to the sam and loops cleanly."""
    r = RAGAS[raga]
    return {"S", r["vadi"], r["samvadi"]}


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


def verify_mukhada(cell: LeadPhrase, *, cycle_beats: float, raga: str) -> list[str]:
    """Return the mukhada head's TIME-legality violations (empty == a clean hook). Pure.

    Four checks the pitch guardrail can't make, each targeting a diagnosed failure of the first
    live gat (the fourth from the 2026-07-20 gat research):
      * FILLS THE AVARTAN — the head's total duration is about one cycle, so looping it re-lands on
        the sam instead of repeating a fragment (or being truncated mid-cadence);
      * CADENCES TO A RESTING SWARA — the last sounding note is Sa, the vadi, or the samvadi, so the
        head resolves to the sam and the loop seam lands rather than restarts;
      * NOT RHYTHMICALLY FLAT — the durations vary (the diagnosed failure was a gat of even quarter
        notes; a hook needs a rhythmic shape).
    A non-empty result drives a bounded RE-ROLL of the head in `generate_lead` — an early, local
    repair, distinct from the late global critique loop.
    """
    notes = cell.notes
    sounding = _sounding(notes)
    if not sounding:
        return ["the mukhada has no sounding notes — it must state a melodic head"]

    viol: list[str] = []
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
        viol.append(f"the mukhada fills only {total:g} of {cycle_beats:g} beats — a fragment, not a "
                    f"one-avartan head; fill about one full cycle so it loops on the sam")
    elif total > _FILL_MAX * cycle_beats:
        viol.append(f"the mukhada runs {total:g} beats, well over the {cycle_beats:g}-beat avartan — "
                    f"keep the head to about one cycle or it gets truncated mid-phrase")

    last = sounding[-1]
    landing = _landing_swara(last)   # a chikari sounds taar Sa (a resting note)
    if landing not in resting:
        viol.append(f"the mukhada ends on {last.swara}, not a resting swara "
                    f"({' '.join(sorted(resting))}) — cadence to the sam so the head lands and loops")

    durations = [round(n.dur, 4) for n in sounding]
    pulse, count = Counter(durations).most_common(1)[0]
    if len(sounding) >= _MIN_NOTES_FLAT and count < _MUKHADA_PULSE_SHARE * len(sounding):
        viol.append(f"the mukhada has no steady PULSE — its commonest note value covers only "
                    f"{count / len(sounding):.0%} of the head (need >= "
                    f"{_MUKHADA_PULSE_SHARE:.0%}). A gat is SUNG: it moves at one pulse, with "
                    f"paired strokes (two notes in a matra, 'dara') as its subdivision and a "
                    f"held nyas to rest on. Clap the rhythm on one pitch — if it is not "
                    f"recognisable that way, the head has no identity yet")
    if not any(d >= _MUKHADA_LONG for d in durations):
        viol.append(f"the mukhada has no long note (>= {_MUKHADA_LONG:g} beats) — the head "
                    f"RESTS somewhere (a nyas on a half/full note) before it moves again")
    # The loop is judged on the MELODIC cadence: a chikari is a stroke struck after the phrase
    # has landed, so it neither hides nor supplies the return.
    melodic = _melodic(sounding)
    if melodic and len(melodic) > 1 and (
            (_landing_swara(melodic[-1]), _landing_oct(melodic[-1]))
            == (_landing_swara(melodic[0]), _landing_oct(melodic[0]))):
        viol.append(f"the head ends on the same note it opens with "
                    f"({_landing_swara(melodic[-1])}), "
                    f"so the two merge across the loop and the SAM DISAPPEARS — the returning "
                    f"cycle must be audible. Cadence to a different resting swara and let the "
                    f"opening note re-enter (…m g R S | m m g g…)")

    return viol


def _double_attack_matras(notes: list[LeadNote]) -> set[int]:
    """The 1-indexed matras (1 matra == 1 beat) carrying a DOUBLE attack — a 'dir': either two
    or more sounding notes starting within the matra, or one note there whose bol is itself a
    compound stroke (diri/darada — `apply_strokes` splits those into multiple attacks)."""
    starts: dict[int, int] = {}
    t = 0.0
    for n in notes:
        if not n.rest:
            matra = int(t + 1e-6) + 1
            attacks = 2 if n.bol in ("diri", "darada") else 1
            starts[matra] = starts.get(matra, 0) + attacks
        t += n.dur
    return {m for m, count in starts.items() if count >= 2}


def verify_bol_frame(cell: LeadPhrase, *, cycle_beats: float, frame: str) -> list[str]:
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
        return []                       # verify_mukhada owns the degenerate-cell complaint

    viol: list[str] = []
    if sounding[0].bol != "da":
        viol.append("the head's first note is not struck 'da' — it sounds ON every sam, and "
                    "the gat frame lands its arrival stroke there strong; set bol \"da\" on it")

    doubles = _double_attack_matras(cell.notes)
    grid_matras = GAT_FRAMES[frame].get("bols") is not None and cycle_beats == GAT_FRAMES[frame]["matras"]
    if grid_matras:
        approach = [m for m in GAT_FRAMES[frame]["double_stroke_matras"]
                    if m > GAT_FRAMES[frame]["mukhda_start"] - 1]      # the dir's in the mukhda span
        missing = [m for m in approach if m not in doubles]
        if missing:
            viol.append(f"the {GAT_FRAMES[frame]['display']} approach needs a dir DOUBLE stroke "
                        f"on matra(s) {' '.join(map(str, missing))} (the dir-da-dir-da-ra surge "
                        f"into the next sam) — put two fast notes, or one note with bol "
                        f"\"diri\", starting in each of those matras")
    elif len(doubles) < _FRAME_MIN_DOUBLES:
        viol.append(f"the head has {len(doubles)} dir doubling(s) — a "
                    f"{GAT_FRAMES[frame]['display']} gat drives on double strokes: at least "
                    f"{_FRAME_MIN_DOUBLES} matras with two fast notes (or a \"diri\" bol)")

    with_bol = sum(1 for n in sounding if n.bol is not None)
    if with_bol < _BOL_MIN_COVERAGE * len(sounding):
        viol.append(f"only {with_bol} of {len(sounding)} notes carry a mizrab bol — the stroke "
                    f"pattern is the gat's identity: give most notes their da/ra (dir doublings "
                    f"where the frame asks), so the head has a rhythm signature, not just pitches")

    return viol


def _overrun_violation(notes: list[LeadNote], window_beats: float, cell_name: str,
                       tail: str) -> str | None:
    """The shared TRUNCATION guard for end-anchored cells: total duration (rests included)
    must not exceed the window, or placement clips the cadence the verifier just approved."""
    total = sum(n.dur for n in notes)
    if total <= _CELL_FILL_MAX * window_beats:
        return None
    return (f"the {cell_name} runs {total:g} beats but its window is {window_beats:g} — the "
            f"overrun gets TRUNCATED, cutting off your own ending; {tail}")


def verify_intro(cell: LeadPhrase, *, window_beats: float, raga: str,
                 mukhada: LeadPhrase | None = None) -> list[str]:
    """Return the intro/alap's structural violations (empty == a grounded alap). Pure.

    The shape is a MINIATURE ALAP VISTAR (Sujit's ear, 2026-07-16, revising the earlier
    every-phrase-resolves design): the phrases hold TENSION — each explores the motif, up or
    down, and does NOT come home — while the MANDRA Sa is PLUCKED between phrases as a drone
    anchor (the low open string / jod string), and the one true resolution is the close.
    Each requirement is that feel translated into a checkable rule (an LLM cannot invent
    silence or groundedness from "be spacious"):
      * OPENS AROUND SA — the first note is Sa or a step or two from it, never in the taar;
      * TOUCHES THE MANDRA — the melodic line itself dips below home (the pluck doesn't count);
      * TENSION HELD — no phrase before the last resolves onto a madhya-or-higher Sa;
      * PLUCKED HOME — every gap between phrases is anchored by a mandra-Sa pluck;
      * ENDS ON A HELD SA — the final phrase alone resolves, onto the intro's longest Sa;
      * SA-ANCHORED — Sa (the plucks + the close) still carries real duration and recurs;
      * REAL SILENCE — at least two true rests of a beat or more.
    Plus the ONE-MOTIF discipline (`_motif_violations`): the intro develops a single declared
    motif — drawn from the mukhada head when `mukhada` is given, so the gat enters as the
    culmination of the intro's idea — and reveals it progressively (badhat) instead of
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
        return ["the intro has no sounding notes — an alap must unfold the raga, sparsely"]

    viol: list[str] = []
    total = sum(n.dur for n in notes)
    if total > _CELL_FILL_MAX * window_beats:
        viol.append(f"the alap runs {total:g} beats but its window is only {window_beats:g} — "
                    f"it would spill into the silence code reserves before the gat; end the "
                    f"held Sa within the window and let the quiet do the rest")

    first = sounding[0]
    if _landing_oct(first) >= 1 or _scale_steps_between(_landing_swara(first), "S", raga) > _INTRO_OPEN_MAX_STEPS:
        viol.append(f"the alap opens on {_landing_swara(first)} (oct {_landing_oct(first):+d}) — "
                    f"begin AROUND madhya Sa (Sa itself or a step or two from it); the exposition "
                    f"starts at home, then dips into the mandra")
    if not any(_landing_oct(n) < 0 for n in _melodic(sounding)):
        viol.append("the alap's melodic line never touches the mandra (lower) octave — dip "
                    "below home in the early phrases before the line rises (the low Sa pluck "
                    "alone is punctuation, not the dip)")

    last = sounding[-1]
    if _landing_swara(last) != "S":
        viol.append(f"the alap ends on {last.swara}, not Sa — it must RESOLVE: come home to a "
                    f"held Sa as the final note")
    elif last.dur < _INTRO_HELD_SA:
        viol.append(f"the alap's final Sa lasts only {last.dur:g} beats — HOLD it (>= "
                    f"{_INTRO_HELD_SA:g} beats) so the resolution is felt before the gat enters")

    total = sum(n.dur for n in sounding)
    sa_dur = sum(n.dur for n in sounding if _landing_swara(n) == "S")
    if sa_dur < _INTRO_SA_SHARE * total:
        viol.append(f"Sa carries only {sa_dur / total:.0%} of the alap's sounding time — keep "
                    f"home ringing (>= {_INTRO_SA_SHARE:.0%} by duration): pluck the mandra Sa "
                    f"between phrases and hold the closing Sa")
    returns = _sa_returns(sounding)
    if returns < _INTRO_MIN_SA_RETURNS:
        viol.append(f"Sa is sounded only {returns} separate time(s) — touch home at least "
                    f"{_INTRO_MIN_SA_RETURNS} times: the low pluck between phrases, and the "
                    f"held Sa at the close")

    rests = [n for n in notes if n.rest and n.dur >= _INTRO_MIN_REST_BEATS]
    if len(rests) < _INTRO_MIN_RESTS:
        viol.append(f"the alap has {len(rests)} true rest(s) of {_INTRO_MIN_REST_BEATS:g}+ beats — "
                    f"use at least {_INTRO_MIN_RESTS}; an alap breathes in real silence, not in "
                    f"wall-to-wall notes")

    viol += _intro_breath_violations(notes)

    # PHRASE GRAMMAR — the alap is short independent sentences separated by real silence, each
    # holding its TENSION (no mid-intro homecoming), with the mandra-Sa pluck anchoring the gaps
    # and Sa never sustained as a wall. A pluck-only group is punctuation, not a phrase.
    phrases = _intro_phrases(notes)
    if len(phrases) < _INTRO_MIN_PHRASES:
        viol.append(f"the alap is only {len(phrases)} phrase(s) — compose at least "
                    f"{_INTRO_MIN_PHRASES} short, INDEPENDENT phrases separated by real silence; "
                    f"do not write one continuous line")
    for i, ph in enumerate(phrases[:-1]):           # every phrase but the final settle
        core = _melodic(ph)
        if not core:
            continue                                # a degenerate phrase; the pluck rules cover it
        last = core[-1]
        if _landing_swara(last) == "S" and _landing_oct(last) > _INTRO_PLUCK_MAX_OCT:
            viol.append(f"phrase {i + 1} resolves onto Sa — hold the TENSION: no phrase before "
                        f"the last comes home; touch home between phrases as a LOW plucked "
                        f"mandra Sa (oct {_INTRO_PLUCK_MAX_OCT}) instead, and save the real "
                        f"resolution for the closing held Sa")
        if all(_landing_swara(n) == "S" for n in core):
            viol.append(f"phrase {i + 1} is only Sa — a phrase must EXPLORE the motif through "
                        f"the raga's swaras; bare Sa is a drone stroke, not a sentence")
    unanchored = _unanchored_boundaries(notes)
    if unanchored:
        viol.append(f"{unanchored} gap(s) between phrases have no mandra-Sa pluck — between "
                    f"every pair of phrases, sound Sa LOW (oct {_INTRO_PLUCK_MAX_OCT}, like a "
                    f"low open string) so home keeps ringing under the held tension")
    held = [n for n in notes if n.bol == "chikari" and n.dur > _CHIKARI_MAX_DUR]
    if held:
        viol.append(f"{len(held)} chikari stroke(s) written longer than {_CHIKARI_MAX_DUR:g} "
                    f"beat — a chikari is a STRUCK string filling an empty matra, played in "
                    f"time and then gone; held, it becomes a second drone over the tanpura. "
                    f"Write chikari short (0.25-0.5) and place it where the melody rests")
    run = _longest_mid_sa_run(notes)
    if run > _INTRO_MAX_SA_RUN:
        viol.append(f"the alap dwells on Sa for {run:g} continuous beats — Sa is a drone TOUCH "
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
        viol.append(f"the alap never states the raga's PAKAD ({pakad}) — build the phrases from the "
                    f"raga's signature phrase(s), quoting one then varying it, so the raga is clear; "
                    f"don't wander through in-scale notes at random")

    # MEEND DISCIPLINE — the render anchors a meend on its TARGET, so an over-meended line is
    # HEARD as its targets (the audible-line checks above read exactly that). This check names
    # the cause so the re-roll fixes the disease, not each symptom.
    meends = sum(1 for n in sounding if _real_meend(n))
    if meends > _INTRO_MEEND_MAX_SHARE * len(sounding):
        viol.append(f"{meends} of {len(sounding)} notes carry a meend — a meend note is HEARD "
                    f"at its TARGET, so over-meending collapses the line onto the targets; use "
                    f"meend on at most half the notes (an ornament gliding INTO a note, not the "
                    f"default articulation), and let most notes sound their own written swara")

    viol.extend(_motif_violations(cell, phrases, mukhada))

    return viol


def _intro_breath_violations(notes: list[LeadNote]) -> list[str]:
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
    ceiling = max(_INTRO_MAX_NOTE_BEATS, _INTRO_MAX_NOTE_SHARE * total)
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
    run = longest_scalar_run(seq, raga)
    if run > _TAAN_SCALAR_MAX:
        viol.append(f"the {cell} walks {run} notes in one unbroken stepwise direction — that is "
                    f"the SCALE, not the raga. One straight dash is idiomatic (a sapat); past "
                    f"{_TAAN_SCALAR_MAX} notes turn back, skip, or repeat a swara. Build the fast "
                    f"passages out of the raga's own movements, not out of its note list")
    return viol


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


def _motif_violations(cell: LeadPhrase, phrases: list[list[LeadNote]],
                      mukhada: LeadPhrase | None) -> list[str]:
    """The intro's ONE-MOTIF + BADHAT violations — the aochar develops a single recurring idea
    and reveals it progressively (see the `_INTRO_MOTIF_*` block for the diagnosed failure):
      * A REAL MOTIF IS DECLARED — `phrase_plan.seed` names the 2-5 swara kernel;
      * DRAWN FROM THE HEAD — when the mukhada is known, the motif appears (in order, small
        gaps, any octave) in the head, so the gat enters as the intro's culmination;
      * EVERY PHRASE CARRIES IT — each phrase except the final settle touches the motif's
        opening fragment (develop ONE thought, don't invent a new phrase each time);
      * REVEALED COMPLETELY — the full motif is stated somewhere before the held Sa;
      * NARROW OPENING — phrase 1 stays a fragment around home (<= `_INTRO_OPEN_SPAN`
        semitones), so there is range left to unfold;
      * LATE WIDEST REACH — the intro's highest melody note arrives past the midpoint.
    """
    viol: list[str] = []
    seed = cell.phrase_plan.seed
    if not (_INTRO_MOTIF_MIN <= len(seed) <= _INTRO_MOTIF_MAX):
        viol.append(f"the intro declares no usable motif (seed = {' '.join(seed) or 'empty'}) — "
                    f"phrase_plan.seed must name the ONE recurring idea, "
                    f"{_INTRO_MOTIF_MIN}-{_INTRO_MOTIF_MAX} swaras drawn from the mukhada head "
                    f"(or the pakad), that every phrase develops")
    else:
        if mukhada is not None:
            head_swaras = [_landing_swara(n) for n in _sounding(mukhada.notes)]
            if head_swaras and not _quote_present(head_swaras, seed, _QUOTE_MAX_GAP):
                viol.append(f"the motif ({' '.join(seed)}) is not drawn from the mukhada head "
                            f"({' '.join(head_swaras)}) — derive it from the head's swaras so "
                            f"the mukhada arrives as the culmination of the intro's idea")
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
        peak = pitches.index(max(pitches))
        elapsed = sum(n.dur for n in melodic[:peak])
        total = sum(n.dur for n in melodic)
        if elapsed < _INTRO_PEAK_MIN_POS * total:
            viol.append("the intro's highest note arrives too early — badhat: reveal the raga "
                        "gradually and let the widest reach land past the midpoint, in the "
                        "later phrases")
    return viol


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


def _unanchored_boundaries(notes: list[LeadNote]) -> int:
    """How many gaps between consecutive PHRASES lack the mandra-Sa drone anchor. A gap is
    anchored when a pluck-only group sits between the phrases, or when the earlier phrase
    ends — or the later one begins — with the pluck (both orderings are idiomatic)."""
    groups = _intro_groups(notes)
    is_phrase = [not all(_is_sa_pluck(n) for n in g) for g in groups]
    idx = [i for i, p in enumerate(is_phrase) if p]
    missing = 0
    for a, b in zip(idx, idx[1:]):
        between = any(not is_phrase[j] for j in range(a + 1, b))
        edge = _is_sa_pluck(groups[a][-1]) or _is_sa_pluck(groups[b][0])
        if not (between or edge):
            missing += 1
    return missing


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


def verify_manjha(cell: LeadPhrase, *, mukhada: LeadPhrase, window_beats: float,
                  raga: str) -> list[str]:
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
        return ["the manjha has no sounding notes — it must develop the mukhada's material"]

    viol: list[str] = []
    # The manjha is the raga's LOW, unhurried stretch — the one place with room to state the
    # raga's central swara plainly. The 2026-09-14 render's manjha contained no Ma AT ALL, in a
    # raga whose vadi is Ma: a section spent entirely away from the note the raga gravitates to.
    ang = _ang_violation(sounding, raga, "manjha",
                         also_accept=[_landing_swara(n) for n in _sounding(mukhada.notes)])
    if ang:
        viol.append(ang)
    vadi = RAGAS[raga]["vadi"]
    if vadi not in {_landing_swara(n) for n in sounding}:
        viol.append(f"the manjha never sounds {vadi}, this raga's VADI — the bridge is the "
                    f"calmest stretch in the piece and the natural place to let the raga's "
                    f"central swara ring; a manjha that avoids it develops the scale, not the raga")
    total = sum(n.dur for n in notes)
    if total < _CELL_FILL_MIN * window_beats:
        viol.append(f"the manjha fills only {total:g} of its {window_beats:g}-beat window — carry "
                    f"the line all the way to the closing sam, where the mukhada re-enters")
    else:
        over = _overrun_violation(notes, window_beats, "manjha",
                                  "land the final note ON the closing sam")
        if over:
            viol.append(over)

    seam = _seam_violation(sounding[-1], mukhada, raga, "manjha")
    if seam:
        viol.append(seam)

    if _rhythmically_flat(sounding):
        viol.append("the manjha is rhythmically flat — every note is the same length; develop the "
                    "head's rhythm, don't pace out even notes")

    # LOWER-REGISTER BRIDGE (Pandit Arvind Parikh; Masitkhani-gat descriptions, 2026-07-15): the
    # manjha takes the melody DOWN into the mandra octave — it is part of the sthayi and the ANTARA,
    # not the manjha, owns the taar. So it must DIP into the lower octave and must NOT climb into the
    # taar. This is what makes it a bridge that CONTRASTS the mukhada (by register) before the ascent.
    if not any(_landing_oct(n) < 0 for n in sounding):
        viol.append("the manjha never dips into the mandra (lower) octave — it must take the melody "
                    "DOWN below home; the manjha is the low bridge before the antara climbs")
    if any(_landing_oct(n) >= 1 for n in sounding):
        viol.append("the manjha reaches the taar (upper) octave — keep it in the mandra / lower-madhya "
                    "register; the ANTARA owns the upper octave, the manjha stays low")

    return viol


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


def verify_antara(cell: LeadPhrase, *, mukhada: LeadPhrase, window_beats: float,
                  raga: str, with_amad: bool = False) -> list[str]:
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
        return ["the antara has no sounding notes — it must develop the gat in the upper register"]

    viol: list[str] = []
    total = sum(n.dur for n in notes)
    if total < _CELL_FILL_MIN * window_beats:
        viol.append(f"the antara fills only {total:g} of its {window_beats:g}-beat window — carry "
                    f"the arc all the way to the closing sam")
    else:
        over = _overrun_violation(notes, window_beats, "antara",
                                  "land the resolving Sa ON the closing sam")
        if over:
            viol.append(over)
    head_swaras = [_landing_swara(n) for n in _sounding(mukhada.notes)][:_ANTARA_QUOTE_LEN]
    half = sounding[:max(1, len(sounding) // 2)]
    if head_swaras and not _quote_present([_landing_swara(n) for n in half],
                                          head_swaras, _QUOTE_MAX_GAP):
        viol.append(f"the antara never quotes the mukhada's opening ({' '.join(head_swaras)}) — "
                    f"OPEN by restating it (an octave up is idiomatic); the antara is the second "
                    f"half of the SAME gat, not a new tune")

    viol.extend(_arc_violations(sounding, "antara"))

    last = sounding[-1]
    if not with_amad and (_landing_swara(last) != "S" or _landing_oct(last) >= 1):
        viol.append(f"the antara ends on {_landing_swara(last)} (oct {_landing_oct(last):+d}) — "
                    f"descend and come to rest on madhya Sa, handing off into the returning mukhada")

    # RHYTHMIC VARIETY (Sujit, 2026-07-16: the antara's harmonized guitar line was "single long
    # notes, no variation" — 26 two-beat notes): the second theme is still a THEME, so it mixes
    # note values (8ths and quarters against the held notes), same floor the taan is held to.
    if len({round(n.dur, 4) for n in sounding}) < _TAAN_MIN_DURATIONS:
        viol.append(f"the antara uses fewer than {_TAAN_MIN_DURATIONS} distinct note values — a "
                    f"wall of even long notes reads as a drone, not a theme; mix 8ths and "
                    f"quarters against the held notes")

    return viol


def verify_amad(cell: LeadPhrase, *, mukhada: LeadPhrase, window_beats: float,
                raga: str, antara_last: str | None = None) -> list[str]:
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
        return ["the amad has no sounding notes — it must compose the descent back to the head"]

    viol: list[str] = []
    total = sum(n.dur for n in notes)
    if total < _CELL_FILL_MIN * window_beats:
        viol.append(f"the amad fills only {total:g} of its {window_beats:g}-beat window — carry "
                    f"the descent all the way to the closing sam, where the mukhada re-enters")
    else:
        over = _overrun_violation(notes, window_beats, "amad",
                                  "land the re-entry note ON the closing sam")
        if over:
            viol.append(over)

    first, last = sounding[0], sounding[-1]
    if antara_last is not None:
        steps = _scale_steps_between(_landing_swara(first), antara_last, raga)
        if steps > _SEAM_MAX_STEPS:
            viol.append(f"the amad opens on {_landing_swara(first)}, a leap from the antara's "
                        f"landing {antara_last} — the amad is the antara's own second line: "
                        f"open on or within a step or two of {antara_last} and descend from there")
    first_pitch = _landing_pitch(first)
    if _landing_pitch(last) >= first_pitch:
        viol.append("the amad does not DESCEND — it must end lower than it begins; the amad's "
                    "whole job is bringing the melody down to where the composition started")
    if max(map(_landing_pitch, sounding)) > first_pitch + _AMAD_RISE_MAX:
        viol.append("the amad climbs above its opening — the peak belongs to the antara; the "
                    "amad may eddy a step but its direction is DOWN, all the way home")
    if _landing_oct(last) > 0:
        viol.append(f"the amad ends in the taar (oct {_landing_oct(last):+d}) — come to rest at "
                    f"or below the madhya, where the returning mukhada picks up")
    seam = _seam_violation(last, mukhada, raga, "amad")
    if seam:
        viol.append(seam)

    if _rhythmically_flat(sounding):
        viol.append("the amad is rhythmically flat — every note is the same length; a composed "
                    "descent still phrases (mix note values on the way down)")

    return viol


def verify_outro(cell: LeadPhrase, *, mukhada: LeadPhrase | None, raga: str) -> list[str]:
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
        return ["the outro has no sounding notes — it is the piece's resolution"]
    viol: list[str] = []
    head = [_landing_swara(n) for n in _sounding(mukhada.notes)] if mukhada else None
    ang = _ang_violation(sounding, raga, "outro", also_accept=head)
    if ang:
        viol.append(ang)
    last = sounding[-1]
    if _landing_swara(last) != "S":
        viol.append(f"the outro ends on {_landing_swara(last)}, not Sa — the piece comes HOME: "
                    f"the last note is Sa, held long enough to feel final")
    elif last.dur < _INTRO_HELD_SA:
        viol.append(f"the outro's final Sa lasts only {last.dur:g} beats — hold it (>= "
                    f"{_INTRO_HELD_SA:g}) so the ending lands instead of stopping")
    return viol


def verify_taan(cell: LeadPhrase, *, motif: list[str], window_beats: float,
                raga: str) -> list[str]:
    """Return the developed taan's (taan_long/solo) structural violations. Pure.

    A taan is the composition's PEAK, not "the scale, quickly". The checkable core of a
    concert taan (the taste — which style, which phrases — stays the LLM's):
      * GROWS FROM THE MOTIF — the piece's shared seed appears (in order, small gaps, any
        octave) somewhere in the taan: one journey, not unrelated fast phrases;
      * THE EARNED ARC — opens madhya, enters the taar, peaks ONCE past the midpoint, and
        comes down after the peak (`_arc_violations`, shared with the antara);
      * LANDS — the final note is a resting swara (Sa / vadi / samvadi), the resolution to
        the sam that makes the landing feel inevitable;
      * BURST AND SPACE — at least one true sixteenth-note burst (>= 4 consecutive notes at
        <= 0.25), at least one breath (a rest or a held note >= 1 beat), and at least three
        distinct durations — speed lands only against contrast, never as an even wall.
    """
    notes = cell.notes
    sounding = _sounding(notes)
    if not sounding:
        return ["the taan has no sounding notes — it is the composition's developed peak"]

    viol: list[str] = []
    viol += _motion_violations(sounding, raga, "taan")

    total = sum(n.dur for n in notes)
    if total < _CELL_FILL_MIN * window_beats:
        viol.append(f"the taan fills only {total:g} of its {window_beats:g}-beat window — the "
                    f"journey must run all the way to the closing sam")
    else:
        over = _overrun_violation(notes, window_beats, "taan",
                                  "the landing must arrive ON the closing sam")
        if over:
            viol.append(over)

    quote = motif[:_TAAN_QUOTE_LEN]
    if quote and not _quote_present([_landing_swara(n) for n in sounding], quote, _QUOTE_MAX_GAP):
        viol.append(f"the taan never grows from the piece's motif ({' '.join(quote)}) — restate "
                    f"or clearly derive from it; the taan develops the composition's ONE idea, "
                    f"it does not introduce a new tune at speed")

    viol.extend(_arc_violations(sounding, "taan"))

    resting = _resting_swaras(raga)
    last = sounding[-1]
    if _landing_swara(last) not in resting:
        viol.append(f"the taan ends on {_landing_swara(last)}, not a resting swara "
                    f"({' '.join(sorted(resting))}) — the final phrase must resolve to the sam "
                    f"so the landing feels inevitable, not abrupt")

    if not _has_burst(sounding):
        viol.append(f"the taan has no true sixteenth-note burst (>= {_TAAN_BURST_LEN} consecutive "
                    f"notes of <= {_TAAN_BURST_NOTE:g} beats) — it must actually run, in bursts")
    elif not _late_burst(sounding):
        viol.append("the taan's final approach WALKS to the landing on long notes — end with a "
                    "dense run (a last burst of 16ths/8ths) that resolves straight onto the "
                    "closing sam; the tension of the run is what makes the landing feel earned")
    if not any(n.rest for n in notes) and not any(n.dur >= _TAAN_SPACE_BEATS for n in sounding):
        viol.append("the taan never breathes — contrast the bursts with space: a true rest or a "
                    "held note of a beat or more")
    if len({round(n.dur, 4) for n in sounding}) < _TAAN_MIN_DURATIONS:
        viol.append(f"the taan uses fewer than {_TAAN_MIN_DURATIONS} distinct durations — mix "
                    f"subdivisions (eighths, sixteenths, held notes), not one even wall of notes")

    return viol


def _has_burst(sounding: list[LeadNote]) -> bool:
    """At least `_TAAN_BURST_LEN` consecutive sounding notes at sixteenth speed or faster."""
    run = 0
    for n in sounding:
        run = run + 1 if n.dur <= _TAAN_BURST_NOTE else 0
        if run >= _TAAN_BURST_LEN:
            return True
    return False


def _late_burst(sounding: list[LeadNote]) -> bool:
    """Does a burst END inside the taan's final stretch (`_TAAN_END_BURST_WINDOW`)? The
    cadential run — the landing note itself may be long; what matters is arriving in flight."""
    total = sum(n.dur for n in sounding)
    elapsed = 0.0
    run = 0
    for n in sounding:
        elapsed += n.dur
        run = run + 1 if n.dur <= _TAAN_BURST_NOTE else 0
        if run >= _TAAN_BURST_LEN and elapsed >= (1.0 - _TAAN_END_BURST_WINDOW) * total:
            return True
    return False


def verify_fill(cell: LeadPhrase, *, mukhada: LeadPhrase, window_beats: float,
                raga: str) -> list[str]:
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
        return ["the taan fill has no sounding notes — it must be a fast sixteenth-note run"]

    viol: list[str] = []
    slow = [n for n in sounding[:-1] if n.dur > _TAAN_NOTE_MAX]
    if slow or sounding[-1].dur > _TAAN_LANDING_MAX:
        viol.append(f"a short taan moves in SIXTEENTHS — every note <= {_TAAN_NOTE_MAX:g} beats "
                    f"(only the final landing note may be longer, up to {_TAAN_LANDING_MAX:g})")

    total = sum(n.dur for n in notes)
    if not (_TAAN_FILL_MIN * window_beats <= total <= _CELL_FILL_MAX * window_beats):
        viol.append(f"the fill lasts {total:g} beats but must fill its {window_beats:g}-beat cut "
                    f"almost exactly — it is spliced into the mukhada, so there is no slack")

    viol += _motion_violations(sounding, raga, "taan fill")

    seam = _seam_violation_to(sounding[-1], reentry_swara(mukhada, window_beats), raga,
                              "taan fill", "the head's re-entering approach")
    if seam:
        viol.append(seam)

    return viol
