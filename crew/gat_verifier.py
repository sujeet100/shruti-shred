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

from typing import Final

from crew.contracts import LeadNote, LeadPhrase
from raga import RAGAS, SWARAS

# A mukhada should fill about ONE avartan so it loops as a cycle. Too short == a fragment; well
# over the cycle == a phrase code has to truncate (cutting off its own cadence). Bounds are
# fractions of the avartan, deliberately loose — this flags the gross misses, not tight musical taste.
_FILL_MIN: Final = 0.6
_FILL_MAX: Final = 1.6
# Calling a head "flat" needs enough notes to judge — two notes of equal length is not a pattern.
_MIN_NOTES_FLAT: Final = 3

# Intro/alap — the diagnosed failure: random wandering that never resolves to Sa, with no space.
# Structure research-verified (2026-07-15, the AOCHAR — the short pre-gat alap; sources in
# DESIGN.md): opens AROUND MADHYA SA and dips into the mandra before rising; phrases end
# sustained on nyas swaras; Sa is re-sounded often (chikari between phrases); the close is the
# section's long final Sa, after which the gat's own mukhada brings the tala in.
_INTRO_SA_SHARE: Final = 0.35       # Sa carries at least this share of the SOUNDING duration
_INTRO_MIN_SA_RETURNS: Final = 3    # ...and the line RETURNS to Sa at least this many times
_INTRO_HELD_SA: Final = 2.0         # the closing Sa is HELD at least this long (beats)
_INTRO_MIN_RESTS: Final = 2         # at least this many true rests...
_INTRO_MIN_REST_BEATS: Final = 1.0  # ...each at least this long
_INTRO_OPEN_MAX_STEPS: Final = 2    # the opening note sits within this many ladder steps of Sa
# The alap's MICRO-structure (Sujit's live note + GPT's alap spec, 2026-07-15): the diagnosed
# failure was "Sa played repeatedly, continuously" — the model met the Sa-share/returns checks by
# CLUSTERING Sa instead of composing phrase -> Sa -> silence. So the sentence structure is now
# checkable: the alap is several SHORT INDEPENDENT phrases (rest-separated), each exploring then
# landing on Sa, and Sa is a LANDING between phrases — never a sustained/repeated wall.
_INTRO_MIN_PHRASES: Final = 3       # at least this many rest-separated phrases (musical sentences)
_INTRO_MAX_SA_RUN: Final = 3.0      # no mid-alap run of consecutive Sa longer than this (the held close is exempt)

# Manjha / taan-fill seam — "fluid" made checkable: the cell's last note sits within this many
# scale-degrees of the mukhada's first swara, so the head re-enters as a step, not a leap.
_SEAM_MAX_STEPS: Final = 2

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
# END-ANCHORED cells (manjha / antara / taan — their cadence IS the last note) must fill their
# window without overrunning it: placement TRUNCATES at the window edge, so any overrun cuts off
# the very cadence the verifier approved. (Caught live: an antara passed "ends on Sa", overran
# its window, and placement clipped the final Sa — the piece heard it end on Re.) The ceiling is
# therefore essentially 1.0 (a hair of rounding slack); the floor keeps the cell from dying early.
_CELL_FILL_MIN: Final = 0.85
_CELL_FILL_MAX: Final = 1.02
# A taan fill is a precise splice into a cut avartan: tighter floor, same hard ceiling.
_TAAN_FILL_MIN: Final = 0.9
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
    """The swara a note actually sounds — a chikari stroke rings taar Sa, whatever it wrote."""
    return "S" if note.bol == "chikari" else note.swara


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


def _seam_violation(last: LeadNote, mukhada: LeadPhrase, raga: str, cell_name: str) -> str | None:
    """The shared RETURN-SEAM rule: the cell's last note must lead fluidly into the mukhada's
    first swara (within `_SEAM_MAX_STEPS` on the raga's ladder — same note or a stepwise pull),
    so the head re-enters on the sam as a resolution, not a jump-cut."""
    head_first = _first_swara(mukhada)
    if head_first is None:
        return None                       # a degenerate head is the mukhada verifier's problem
    landing = _landing_swara(last)
    if _scale_steps_between(landing, head_first, raga) <= _SEAM_MAX_STEPS:
        return None
    return (f"the {cell_name} ends on {landing}, which does not lead into the mukhada's first "
            f"swara {head_first} — end on {head_first} itself or within a step or two of it "
            f"(a stepwise lead-in), so the head re-enters fluidly on the sam")


def verify_mukhada(cell: LeadPhrase, *, cycle_beats: float, raga: str) -> list[str]:
    """Return the mukhada head's TIME-legality violations (empty == a clean hook). Pure.

    Three checks the pitch guardrail can't make, each targeting a diagnosed failure of the first
    live gat:
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
    total = sum(n.dur for n in notes)
    if total < _FILL_MIN * cycle_beats:
        viol.append(f"the mukhada fills only {total:g} of {cycle_beats:g} beats — a fragment, not a "
                    f"one-avartan head; fill about one full cycle so it loops on the sam")
    elif total > _FILL_MAX * cycle_beats:
        viol.append(f"the mukhada runs {total:g} beats, well over the {cycle_beats:g}-beat avartan — "
                    f"keep the head to about one cycle or it gets truncated mid-phrase")

    resting = _resting_swaras(raga)
    last = sounding[-1]
    landing = _landing_swara(last)   # a chikari sounds taar Sa (a resting note)
    if landing not in resting:
        viol.append(f"the mukhada ends on {last.swara}, not a resting swara "
                    f"({' '.join(sorted(resting))}) — cadence to the sam so the head lands and loops")

    if _rhythmically_flat(sounding):
        viol.append("the mukhada is rhythmically flat — every note is the same length; vary the "
                    "durations so the head has a rhythmic shape (a gat head is not even quarters)")

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


def verify_intro(cell: LeadPhrase, *, window_beats: float, raga: str) -> list[str]:
    """Return the intro/alap's structural violations (empty == a grounded alap). Pure.

    The diagnosed failure of the first live gat: an alap of wandering notes that NEVER resolved
    to Sa, barely touched it, and left no silence. Each requirement is Sujit's feel — plus the
    research-verified AOCHAR shape — translated into a checkable rule (an LLM cannot invent
    silence or groundedness from "be spacious"):
      * OPENS AROUND SA — the first note is Sa or a step or two from it, never in the taar
        (the exposition starts around the middle tonic and dips into the mandra first);
      * TOUCHES THE MANDRA — the early phrases reach below the home octave before the rise;
      * ENDS ON A HELD SA — the alap must come to rest, not stop;
      * SA-ANCHORED — Sa carries >= 30% of the sounding duration AND the line RETURNS to Sa
        several separate times (Sa is HOME and the ear must keep hearing it come home);
      * REAL SILENCE — at least two true rests of a beat or more;
      * A BREATH AFTER SA — at least one rest immediately follows a Sa landing (the nyas).
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
    if first.oct >= 1 or _scale_steps_between(_landing_swara(first), "S", raga) > _INTRO_OPEN_MAX_STEPS:
        viol.append(f"the alap opens on {_landing_swara(first)} (oct {first.oct:+d}) — begin "
                    f"AROUND madhya Sa (Sa itself or a step or two from it); the exposition "
                    f"starts at home, then dips into the mandra")
    if not any(n.oct < 0 for n in sounding):
        viol.append("the alap never touches the mandra (lower) octave — dip below home in the "
                    "early phrases before the line rises; that dip is the aochar's first move")

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
        viol.append(f"Sa carries only {sa_dur / total:.0%} of the alap's sounding time — return "
                    f"to Sa often (>= {_INTRO_SA_SHARE:.0%} by duration); the alap's job is to "
                    f"establish Sa as home")
    returns = _sa_returns(sounding)
    if returns < _INTRO_MIN_SA_RETURNS:
        viol.append(f"the line comes home to Sa only {returns} time(s) — RETURN to Sa at least "
                    f"{_INTRO_MIN_SA_RETURNS} separate times (end phrases on Sa, and punctuate "
                    f"between phrases with chikari strokes)")

    rests = [n for n in notes if n.rest and n.dur >= _INTRO_MIN_REST_BEATS]
    if len(rests) < _INTRO_MIN_RESTS:
        viol.append(f"the alap has {len(rests)} true rest(s) of {_INTRO_MIN_REST_BEATS:g}+ beats — "
                    f"use at least {_INTRO_MIN_RESTS}; an alap breathes in real silence, not in "
                    f"wall-to-wall notes")

    if not _rest_after_sa(notes):
        viol.append("no rest follows a Sa landing — after you land on Sa, take a true rest "
                    "(the nyas breath) before moving on")

    # PHRASE GRAMMAR — the alap is a sequence of short sentences (explore -> resolve to Sa ->
    # silence), NOT one continuous line, and Sa is a LANDING, never a sustained wall. This is the
    # structure the Sa-share/returns checks above could not enforce (they were met by clustering Sa).
    phrases = _intro_phrases(notes)
    if len(phrases) < _INTRO_MIN_PHRASES:
        viol.append(f"the alap is only {len(phrases)} phrase(s) — compose at least "
                    f"{_INTRO_MIN_PHRASES} short, INDEPENDENT phrases separated by real silence, "
                    f"each exploring then resolving to Sa; do not write one continuous line")
    for i, ph in enumerate(phrases):
        if _landing_swara(ph[-1]) != "S":
            viol.append(f"phrase {i + 1} ends on {_landing_swara(ph[-1])}, not Sa — every alap "
                        f"phrase must RESOLVE home to Sa before its pause")
        if i < len(phrases) - 1 and all(_landing_swara(n) == "S" for n in ph):
            viol.append(f"phrase {i + 1} is only Sa — a phrase must EXPLORE a swara or two of the "
                        f"raga and THEN land on Sa; bare Sa is a drone, not a sentence")
    run = _longest_mid_sa_run(notes)
    if run > _INTRO_MAX_SA_RUN:
        viol.append(f"the alap dwells on Sa for {run:g} continuous beats — Sa is where each phrase "
                    f"LANDS, not a note to repeat or sustain; explore between the Sa landings")

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

    return viol


def _intro_phrases(notes: list[LeadNote]) -> list[list[LeadNote]]:
    """Split the alap into PHRASES at true rests: each phrase is the run of sounding notes
    between rests. The alap's grammar is phrase -> Sa -> silence repeated, so a phrase is
    exactly what a rest separates. Leading/trailing rests create no empty phrase."""
    phrases: list[list[LeadNote]] = []
    cur: list[LeadNote] = []
    for n in notes:
        if n.rest:
            if cur:
                phrases.append(cur)
                cur = []
        else:
            cur.append(n)
    if cur:
        phrases.append(cur)
    return phrases


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


def _rest_after_sa(notes: list[LeadNote]) -> bool:
    """Does any true rest immediately follow a sounding Sa?"""
    return any(n.rest and not prev.rest and _landing_swara(prev) == "S"
               for prev, n in zip(notes, notes[1:]))


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
    if not any(n.oct < 0 for n in sounding):
        viol.append("the manjha never dips into the mandra (lower) octave — it must take the melody "
                    "DOWN below home; the manjha is the low bridge before the antara climbs")
    if any(n.oct >= 1 for n in sounding):
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
    if sounding[0].oct >= 1:
        viol.append(f"the {cell_name} opens already in the taar octave — start in the middle "
                    f"(madhya) octave and CLIMB; the ascent is the {cell_name}'s story")
    if max(n.oct for n in sounding) < 1:
        viol.append(f"the {cell_name} never reaches the taar octave — its climb must enter the "
                    f"upper octave (oct +1) for the composition's peak")
        return viol
    pitches = [n.oct * 12 + SWARAS[_landing_swara(n)] for n in sounding]
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
                  raga: str) -> list[str]:
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
    if _landing_swara(last) != "S" or last.oct >= 1:
        viol.append(f"the antara ends on {_landing_swara(last)} (oct {last.oct:+d}) — descend and "
                    f"come to rest on madhya Sa, handing off into the returning mukhada")

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


def verify_fill(cell: LeadPhrase, *, mukhada: LeadPhrase, window_beats: float,
                raga: str) -> list[str]:
    """Return a mukhada taan-FILL's structural violations (empty == a clean splice). Pure.

    The fill is the classic gat move: cut a few matras out of a head statement, burst a short
    sixteenth-note taan there, and resolve back so the head re-enters fluently on the next sam.
    Code owns the splice (where the head is cut); this owns the fill's checkable grammar:
      * IT IS A TAAN — sixteenth notes (<= 0.25 beats) throughout, with at most one longer
        final landing note;
      * IT FITS THE CUT — the cell fills its half-avartan window almost exactly (a splice has
        no room for slack);
      * IT RESOLVES INTO THE HEAD — the same return-seam rule as the manjha.
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

    seam = _seam_violation(sounding[-1], mukhada, raga, "taan fill")
    if seam:
        viol.append(seam)

    return viol
