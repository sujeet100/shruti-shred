"""
The Lead generator (step 4, generator #1) — the raga melodic voice.

Reads the shared Arrangement chart and, for each section where `lead` is active,
asks the LLM for ONE phrase (a `LeadPhrase`), then lays it onto that section's
window in the lead's register. The pattern on show: STRUCTURED GENERATION +
VALIDATION AT THE BOUNDARY — the same shape as the composers, but producing NOTES
now, not a plan.

The split the whole project preaches, applied to a generator:
  * the LLM supplies the MUSIC — which swaras, how long, which kan/meend — the part
    that is taste and idiom;
  * CODE owns the CHECKABLE — it places the phrase on the beat grid in the right
    register (`place_phrase`), and the legality guardrail (`validate_composition`'s
    core) bounces any out-of-raga swara back for one bounded retry.

Layering (pure core / imperative shell, as in composers.py):
  * pure          — `place_phrase`, the fact->prompt renderers, and `generate_lead`
                    (control flow over an injected `gen_fn`, so the loop tests with
                    no LLM);
  * imperative    — `_LeadCrew` / `_LLMLead` make the Gemini calls; `main` renders.

Entry point (ONE live LLM call — the lead over a bare drone):
  uv run python -m crew.lead
"""

from __future__ import annotations

import math
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Final, Protocol

import yaml
from crewai import Agent, Crew, Process, Task
from pydantic import ValidationError

from crew.config import AGENT_RETRY_LIMIT, GENERATOR_MAX_ITER, GENERATOR_RETRIES, generator_llm, load_env
from crew.contracts import (
    Arrangement,
    CanvasMove,
    DebateEvent,
    EventStream,
    EventType,
    Gat,
    Layer,
    LeadNote,
    LeadPhrase,
    Note,
    PhrasePlan,
    RiffNote,
    Section,
    SectionCanvas,
    SectionKind,
    motif_illegal_in_raga,
)
from crew.gat_verifier import (
    verify_antara,
    verify_fill,
    verify_intro,
    verify_manjha,
    verify_mukhada,
    verify_taan,
)
from crew.generators import (
    VOICES,
    SectionSpan,
    assemble_composition,
    drone_layer,
    render_composition,
    section_spans,
)
from crew.live import beat, flags
from raga import RAGAS, direction_violations, directional_varjya, scale_step_up, validate_composition

_LEAD_ROLE: Final = "lead"                 # the layer role this generator fills
_ROLE_GENERATOR: Final = "generator"       # DebateEvent role for a generator step
_MUKHADA: Final = "mukhada"                # the gat HEAD — a cached ~1-avartan cell, looped + reprised
_INTRO: Final = "intro"                    # the alap — Sa-anchored, verified, code-reserved silence after
_MANJHA: Final = "manjha"                  # the development — verified to RETURN into the head
_ANTARA: Final = "antara"                  # the second movement — verified arc: quote, climb, peak, descend
_TAAN_LONG: Final = "taan_long"            # the developed peak — verified: motif-grown, arced, burst+space
_CELL_REPAIR_TRIES: Final = 1              # extra re-rolls of a weak verified cell (bounded; best-of-N kept)

# The intro reserves a TRAILING SILENCE before the gat enters — the long breath between the
# alap's final held Sa and the mukhada. Rests render as true silence and sections have no
# cross-block ties, so this pause must live INSIDE the intro's window: the alap is generated
# for a SHORTENED window and placement simply leaves the tail empty. Code owns the pause —
# an LLM told to "leave a long gap" reliably fills it.
_INTRO_GAP_FRACTION: Final = 0.35          # up to this fraction of the intro window...
                                           # ...capped at one tala cycle (see _intro_gen_span)

# The intro's clean-guitar arpeggio establishes the pulse; the alap then LOCKS to it (Sujit,
# 2026-07-19, avartan-locked): a lead-in of whole avartan(s) plays the arpeggio ALONE before the
# sitar enters, and every alap phrase begins on a sam (`_place_intro_phrases`) so it rides the
# arpeggio's cycle instead of drifting against it. Both apply only when the intro carries the
# clean arpeggio — without a pulse there is nothing to lock to (the old flush-left placement).
_CLEAN_ROLE: Final = "clean"               # the harmony/arpeggio layer the alap locks onto
_INTRO_LEAD_IN_BARS: Final = 1             # avartan(s) of arpeggio ALONE before the alap enters
_PHRASE_BREAK_MIN_BEATS: Final = 1.0       # a rest this long ends a phrase; shorter rests stay within

# The manjha is a SHORT lower-register bridge (Pandit Arvind Parikh; Masitkhani-gat descriptions):
# at most one avartan, and we reserve a small breath before the mukhada re-enters — so it lands
# SUB-CYCLE (~12 matras in a 16-matra teentaal), matching the sources and Sujit's ear (8-11 matras).
# The old manjha filled its whole multi-bar section — a long developmental episode the tradition
# does NOT have. Register (dip to the mandra, no taar) is enforced by verify_manjha.
_MANJHA_MAX_CYCLES: Final = 1.0            # never longer than one avartan (a manjha is a short line)
_MANJHA_GAP_FRACTION: Final = 0.25         # reserve this much as a breath before the head returns

# The mukhada taan FILLS — cut the back half of head statements and splice sixteenth-note
# taans there, each resolving into the next statement (the classic gat move). Only a section
# long enough to spare statements gets them (never its first or last bar, so the head still
# opens and closes the section cleanly). Sujit's ask (2026-07-15): SEVERAL taan+mukhada
# phrases per piece, and they should not all be the same taan — so up to `_FILL_VARIANTS`
# DISTINCT cells are written and ROTATED across the fill slots.
_FILL_MIN_BARS: Final = 3                  # a mukhada section this long earns taan fills
_FILL_FRACTION: Final = 0.5                # a fill takes this much of its avartan (the back half)
_FILL_VARIANTS: Final = 3                  # at most this many distinct fill cells per piece
_FILL_BARS_PER_SECTION: Final = 3          # at most this many cut statements per section

_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
_SOUNDFONT: Final[Path] = _ROOT / "soundfonts" / "GeneralUser-GS.sf2"
_OUT_DIR: Final[Path] = _ROOT / "out"

# The exact JSON shape we want back, injected as an input so CrewAI's {placeholder}
# interpolation never has to parse these literal braces (same trick as composers).
_OUTPUT_SCHEMA: Final = """{
  "phrase_plan": {
    "seed": ["g", "m", "d"],
    "contour": "arch",
    "transformations": ["repeat", "sequence_up", "rhythmic_compression", "resolve"],
    "climax_and_sam": "peaks in the taar octave, then resolves down to land on the sam"
  },
  "notes": [
    {"swara": "d", "oct": -1, "dur": 2.0, "vel": 80, "bol": "da"},
    {"swara": "n", "oct": -1, "dur": 0.5},
    {"swara": "S", "oct": 0, "dur": 0.5},
    {"swara": "g", "oct": 0, "dur": 0.5, "grace": ["S"]},
    {"swara": "m", "oct": 0, "dur": 4.0, "meend_swara": "S", "meend_oct": 1},
    {"rest": true, "swara": "S", "dur": 1.0},
    {"swara": "g", "oct": 0, "dur": 1.5, "ornament": "murki"},
    {"swara": "S", "oct": 1, "dur": 0.5, "bol": "chikari"}
  ]
}
Decide "phrase_plan" FIRST, then write "notes" that REALIZE it. Most notes are PLAIN —
just swara, oct, dur (and optionally vel), like the second and third example notes: add
grace / meend / bol / ornament only where a rule asks for that specific gesture, and emit
"rest" only on an actual silence. "contour" is one of
ascending / descending / arch / wave / landing / explosion. "transformations" (in the
order they happen) are drawn from repeat, sequence_up, sequence_down, invert, fragment,
accelerate, answer, resolve, octave_shift, rhythmic_compression. For a TAAN/SOLO section
the plan has THREE more required fields (omit them elsewhere): "taan_style" (the ONE
dominant style — pick from the section guidance), "register_plan" (the arc in one line:
where you start, where the single peak lands, the descent), and "rhythm_plan" (the
burst/space shape, e.g. "pickup, 16th burst, held nyas, longer burst, tihai to sam"). For an
INTRO/alap section the plan has ONE more required field (omit it elsewhere): "badhat_plan"
(the progressive reveal in one line: the motif fragment phrase 1 states, what each later
phrase adds, where the widest reach lands). In the notes: "oct" is
your octave (0 = home; -1 mandra/lower, +1 taar/upper); "vel", "grace", "meend_swara",
"meend_oct" and "bol" are optional. "meend_swara" is a swara to glide to — and the note is
HEARD AT THE TARGET (the written swara is only the brief start of the pull), so a meend is an
OCCASIONAL ornament gliding INTO a note you want heard, never the default articulation: most
notes carry NO meend and sound their own written swara. Add "meend_oct" (same frame as a
note's "oct") ONLY to glide ACROSS octaves — omit it to glide within the note's own
octave. "bol" is the sitar mizrab STROKE (articulation, NOT a rhythm): "da" strong, "ra" softer,
"diri" a fast double-stroke (a pair), "darada" a triple-stroke (a triplet), "chikari" a bright
high-Sa punctuation accent (its swara is ignored). "rest" (optional) = a SILENT beat for nyas /
space: set rest:true with any swara (ignored) to rest on the sam or leave room for the tabla.
"ornament" (optional) = a light sitar flick the code decorates the note with — "murki" (delicate)
or "khatka" (sharper); only some ragas use them (see the raga facts), and code builds the cluster
from the raga's own neighbour swaras. Durations are in beats and must be positive."""


# --------------------------------------------------------------------------- #
# Placement: LLM phrase -> notes on the section's window. Pure.                #
# --------------------------------------------------------------------------- #

# A meend needs a long note to speak — a glide crammed onto a fast taan note reads as a
# sag, not an ornament (the "drunken staircase" a dense run of meends produces). So code
# strips meend from any note shorter than this, reserving it for held/cadential notes. The
# DIRECTION is left free: a bend may rise or fall (kan, khatka, murki, meend all move either
# way), so we gate on note length and density, never on which way it glides.
_MEEND_MIN_BEATS: Final = 1.0

# Andolan is a SLOW sway — it needs a held note to speak, exactly like a meend, so code flags
# it only on a sustained note (a note may carry BOTH: the renderer glides in, then sways —
# the "R -> g~~" Darbari entry). Which swaras sway
# is a RAGA FACT (raga["andolan"]), passed in from the layer that knows the raga; the renderer
# then draws the oscillation. "Code decides the checkable (which komal notes, how long); the
# renderer draws the gesture" — the LLM never asks for andolan (it can't hear it). This beat
# floor is only the coarse "is it held at all" cut; the REAL gate is wall-clock, in the
# renderer (ANDOLAN_MIN_MS — only it knows the tempo), so a flagged-but-short note plays plain.
_ANDOLAN_MIN_BEATS: Final = 1.0


def place_phrase(notes: list[LeadNote], *, start: float, end: float, register: int,
                 andolan_swaras: frozenset[str] = frozenset()) -> list[Note]:
    """Lay a phrase's notes end-to-end from `start`, seat them in `register`, and
    TRUNCATE at `end` so the lead never spills past its section window.

    The "code enforces" half of the split: the LLM aims for the window length, but
    code guarantees the phrase stays inside it and in the right octave. Each note's
    absolute octave is the lead's register plus the note's LOCAL octave; a straddling
    final note is clipped to the window edge; notes beyond it are dropped. `andolan_swaras`
    (a raga fact) flags a held note on one of those swaras for the renderer's oscillation.
    """
    placed: list[Note] = []
    t = start
    for ln in notes:
        if t >= end:
            break
        if ln.rest:                         # a SILENT beat (nyas/space) — advance time, sound nothing
            t += ln.dur
            continue
        dur = min(ln.dur, end - t)          # clip the note that straddles the edge
        placed.append(_placed_note(ln, register=register, start=t, dur=dur,
                                   andolan_swaras=andolan_swaras))
        t += ln.dur
    return placed


def _placed_note(ln: LeadNote, *, register: int, start: float, dur: float,
                 andolan_swaras: frozenset[str] = frozenset()) -> Note:
    """One placed Note, with the meend guard and andolan flag applied. A glide is kept only
    on a note at least `_MEEND_MIN_BEATS` long, so fast-run notes articulate cleanly instead
    of sagging. Andolan is flagged on a held note (>= `_ANDOLAN_MIN_BEATS`) whose RESTING
    swara — the meend target when the note glides, else its own — is one the raga
    oscillates: a gliding note spends its hold ON the target, so "R -> g" rests (and
    sways) on ga while "g -> m" rests on ma and plays straight. The renderer composes
    the two gestures (glide in, settle, sway — the research-correct Darbari entry)."""
    keep_meend = ln.meend_swara is not None and dur >= _MEEND_MIN_BEATS
    resting = ln.meend_swara if keep_meend else ln.swara
    andolan = (resting in andolan_swaras and dur >= _ANDOLAN_MIN_BEATS) or None
    return Note(swara=ln.swara, oct=register + ln.oct, start=round(start, 4),
                dur=round(dur, 4), vel=ln.vel, grace=ln.grace,
                meend_swara=ln.meend_swara if keep_meend else None,
                meend_oct=_place_meend_oct(ln, register) if keep_meend else None,
                andolan=andolan)


def _place_meend_oct(ln: LeadNote, register: int) -> int | None:
    """Register-shift the meend target's LOCAL octave into the absolute frame the renderer
    expects, exactly as the note's own octave is shifted. Returns None when the glide has
    no explicit octave — the renderer then glides WITHIN the note's own (already-seated)
    octave — or when there is no glide at all.
    """
    if ln.meend_swara is None or ln.meend_oct is None:
        return None
    return register + ln.meend_oct


# --------------------------------------------------------------------------- #
# The gat HEAD (mukhada) — a cached ~1-avartan cell, LOOPED across the section #
# and REPRISED verbatim on return. Pure. This is the fix for the core gat bug: #
# the lead used to compose ONE 40-matra phrase for the whole mukhada window    #
# (no repeatable hook) and REGENERATE the return (which drifted). Now the LLM  #
# writes exactly one avartan; CODE owns the recurrence, exactly as the riff    #
# slot cache does — the identity lives in code, not in the model remembering.  #
# --------------------------------------------------------------------------- #

def is_mukhada(section) -> bool:
    """Whether this section is the gat HEAD — the one form_role code loops + caches."""
    return section.form_role == _MUKHADA


def is_intro(section) -> bool:
    """Whether this section is the gat's intro/alap — verified, with a code-reserved pause."""
    return section.form_role == _INTRO


def is_manjha(section) -> bool:
    """Whether this section is the manjha — the development cell that must RETURN to the head."""
    return section.form_role == _MANJHA


def is_antara(section) -> bool:
    """Whether this section is the antara — the second movement with the verified arc."""
    return section.form_role == _ANTARA


def is_taan_long(section) -> bool:
    """Whether this section is the developed taan — the verified peak of the composition."""
    return section.form_role == _TAAN_LONG


def _one_cycle_span(span: SectionSpan, cycle_beats: float) -> SectionSpan:
    """A synthetic 1-bar (1-avartan) span, so the LLM composes the mukhada as EXACTLY one
    tala cycle — its `window_beats` and sam positions describe a single avartan — instead of
    the whole multi-avartan window. Code then loops that cell across the real bars."""
    return SectionSpan(index=span.index, section=span.section.model_copy(update={"bars": 1}),
                       start=span.start, end=span.start + cycle_beats)


def _ring_out_intro(line: list[Note], span: SectionSpan) -> list[Note]:
    """Let the intro's final note RING through the code-reserved gap, fading like a struck
    string dying away (Sujit: "resolve the intro to Sa — a long one, like a chord with
    sustain, dropping volume"). The verified alap ends on a held Sa inside its shortened
    window; code extends that note's SUSTAIN to the section edge and flags the renderer's
    `fade` — articulation, not composition: no pitch, no order, no new note. Any pitch-wheel
    gesture is stripped (a glide across a long dying tone would read as a swoop). Pure."""
    if not line:
        return line
    last = line[-1]
    return line[:-1] + [last.model_copy(update={
        "dur": round(span.end - last.start, 4), "fade": True,
        "meend_swara": None, "meend_oct": None, "andolan": None})]


def _intro_lead_in_beats(section: Section, cycle_beats: float) -> float:
    """The arpeggio-alone lead-in at the FRONT of the intro, in beats: `_INTRO_LEAD_IN_BARS`
    whole avartan(s) when the intro carries the clean arpeggio (there is a pulse to establish
    before the sitar enters), else zero — with no arpeggio nothing would sound, so keep the old
    flush-left placement."""
    return cycle_beats * _INTRO_LEAD_IN_BARS if _CLEAN_ROLE in section.layers else 0.0


def _intro_gen_span(span: SectionSpan, cycle_beats: float) -> SectionSpan:
    """The intro's SHORTENED generation window. CODE reserves two silences around the alap so
    the LLM composes only the sounding phrases:
      * a LEAD-IN of `_INTRO_LEAD_IN_BARS` avartan(s) at the FRONT — the clean-guitar arpeggio
        establishes the pulse ALONE before the sitar enters (only when the intro carries that
        arpeggio; see `_intro_lead_in_beats`);
      * a TRAILING gap (up to one cycle, at most `_INTRO_GAP_FRACTION` of the REMAINING window)
        the alap's final Sa rings and fades across (`_ring_out_intro`) before the mukhada's entry.
    The LLM composes into what is left; `_place_intro_phrases` then snaps each phrase onto a sam.
    An alap SHORTER than the window is fine (more silence, never less)."""
    start = span.start + _intro_lead_in_beats(span.section, cycle_beats)
    gap = min(cycle_beats, (span.end - start) * _INTRO_GAP_FRACTION)
    return SectionSpan(index=span.index, section=span.section,
                       start=start, end=span.end - gap)


def _next_sam(t: float, *, origin: float, cycle_beats: float) -> float:
    """The first sam (avartan downbeat) at or after `t`, on the grid anchored at `origin` — the
    intro's start, where the clean arpeggio restarts its figure each bar. Pure."""
    steps = max(0, math.ceil((t - origin - 1e-9) / cycle_beats))
    return origin + steps * cycle_beats


def _split_phrases(notes: list[LeadNote]) -> list[list[LeadNote]]:
    """Split an alap into PHRASES at its breathing rests: a rest of at least
    `_PHRASE_BREAK_MIN_BEATS` ends a phrase (the true silence the alap leaves between ideas),
    while a shorter rest stays inside its phrase as a micro-gap. The long rests are dropped —
    `_place_intro_phrases` replaces them with the snap-to-sam gap. Non-empty phrases, in order."""
    phrases: list[list[LeadNote]] = []
    current: list[LeadNote] = []
    for n in notes:
        if n.rest and n.dur >= _PHRASE_BREAK_MIN_BEATS:
            if current:
                phrases.append(current)
                current = []
        else:
            current.append(n)
    if current:
        phrases.append(current)
    return phrases


def _is_mandra_pluck(phrase: list[LeadNote]) -> bool:
    """A between-phrases mandra-Sa PLUCK (the alap-vistar drone anchor `verify_intro` expects
    in every gap): a phrase whose every sounding note is a LOW (mandra) Sa. In the avartan-locked
    intro the clean arpeggio holds Sa between phrases, so the pluck's anchoring role is already
    covered — placement drops it, letting the MELODIC phrases land cleanly on the sams. The
    closing madhya Sa (oct 0, held) is not a pluck, so the resolution always survives."""
    sounding = [n for n in phrase if not n.rest]
    return bool(sounding) and all(n.swara == "S" and n.oct < 0 for n in sounding)


def _place_intro_phrases(notes: list[LeadNote], *, gen_span: SectionSpan,
                         section_span: SectionSpan, register: int, cycle_beats: float,
                         andolan_swaras: frozenset[str] = frozenset()) -> list[Note]:
    """Place the alap so each PHRASE begins on a sam (Sujit's avartan-locked intro): the first
    phrase enters at `gen_span.start` — one arpeggio avartan in, after the clean-guitar lead-in —
    and every later phrase is nudged forward to the next sam, so it locks to the clean arpeggio's
    cycle instead of drifting against it. Notes flow freely WITHIN a phrase (the alap keeps its
    free rhythm); only phrase STARTS snap. The between-phrases mandra-Sa plucks are dropped (the
    arpeggio anchors Sa now — `_is_mandra_pluck`). Phrases fill the sams up to the section edge;
    the final resolving Sa is ring-extended across the tail by the caller (`_ring_out_intro`) —
    the trailing silence the LLM leaves is a compose-window reserve, not a placement barrier. Pure."""
    placed: list[Note] = []
    cursor = gen_span.start
    for phrase in _split_phrases(notes):
        if _is_mandra_pluck(phrase):                    # the arpeggio holds Sa between phrases now
            continue
        start = _next_sam(cursor, origin=section_span.start, cycle_beats=cycle_beats)
        if start >= section_span.end - 1e-9:            # no whole sam left before the edge — stop
            break
        seg = place_phrase(phrase, start=start, end=section_span.end, register=register,
                           andolan_swaras=andolan_swaras)
        if not seg:                                     # fully truncated — try the next sam
            cursor = start + cycle_beats
            continue
        placed.extend(seg)
        cursor = seg[-1].start + seg[-1].dur
    return placed


def _manjha_gen_span(span: SectionSpan, cycle_beats: float) -> SectionSpan:
    """The manjha's SHORT generation window: at most one avartan, minus a reserved breath before
    the mukhada re-enters, so the low bridge lands sub-cycle instead of filling a whole multi-bar
    section (Parikh: the manjha is a short line that takes the melody into the lower octave, not a
    long development). Front-positioned like the intro; code leaves the trailing beats as silence."""
    length = min(span.length, cycle_beats * _MANJHA_MAX_CYCLES) * (1.0 - _MANJHA_GAP_FRACTION)
    return SectionSpan(index=span.index, section=span.section,
                       start=span.start, end=span.start + length)


def _fill_bars(section) -> list[int]:
    """Which bars of a mukhada section get a taan fill — the MIDDLE statements of a section
    long enough to spare them (never the first bar, which states the head, nor the last, which
    closes the section; capped so a long section is still mostly head). Empty when the section
    keeps every statement whole."""
    if not is_mukhada(section) or section.bars < _FILL_MIN_BARS:
        return []
    return list(range(1, section.bars - 1))[:_FILL_BARS_PER_SECTION]


def _place_lead_section(notes: list[LeadNote], *, span: SectionSpan, register: int,
                        cycle_beats: float,
                        andolan_swaras: frozenset[str] = frozenset(),
                        bar_fills: dict[int, list[LeadNote]] | None = None) -> list[Note]:
    """Place a section's notes on its window. A MUKHADA loops its one-avartan cell across every
    bar (each bar re-lands on the sam — the repeating hook); every other role lays its phrase
    once across the whole window. Truncation at each cycle edge means even an over-long cell
    degrades to 'loop the first avartan', so the loop is robust to a cell that overshoots.

    When `bar_fills` is given (bar index -> that bar's taan cell), those statements of the
    mukhada section are CUT: the head plays its front, the sixteenth-note taan takes the back,
    and the next statement re-enters on its sam — the splice is code's, the taans are the
    LLM's (each verified to resolve into the head)."""
    if is_manjha(span.section):                     # the low bridge occupies a SHORT sub-cycle window
        m = _manjha_gen_span(span, cycle_beats)     # (the same window it was generated + verified against)
        return place_phrase(notes, start=m.start, end=m.end, register=register,
                            andolan_swaras=andolan_swaras)
    if not is_mukhada(span.section):
        return place_phrase(notes, start=span.start, end=span.end, register=register,
                            andolan_swaras=andolan_swaras)
    placed: list[Note] = []
    for bar in range(span.section.bars):
        bar_start = span.start + bar * cycle_beats
        bar_end = bar_start + cycle_beats
        fill = (bar_fills or {}).get(bar)
        if fill is not None:
            cut = bar_start + cycle_beats * (1.0 - _FILL_FRACTION)
            placed.extend(place_phrase(notes, start=bar_start, end=cut, register=register,
                                       andolan_swaras=andolan_swaras))
            placed.extend(place_phrase(fill, start=cut, end=bar_end, register=register,
                                       andolan_swaras=andolan_swaras))
        else:
            placed.extend(place_phrase(notes, start=bar_start, end=bar_end,
                                       register=register, andolan_swaras=andolan_swaras))
    return placed


# --------------------------------------------------------------------------- #
# Mizrab bols — realise the sitar's right-hand STROKE as articulation. Pure.   #
# A bol is a stroke, not a pitch or a duration (source-verified; see DESIGN.md #
# step 5), and our GM sitar can't voice true stroke timbre, so code renders it #
# with the honest lever we have — velocity, a double-stroke, a bright accent — #
# BEFORE placement, preserving each note's total duration so timing is intact. #
# --------------------------------------------------------------------------- #

_BOL_DA_VEL: Final = 1.12        # da — the strong stroke, accented
_BOL_RA_VEL: Final = 0.82        # ra — the softer return
_STROKE_STRONG: Final = 1.05     # a `da` within a compound (diri/darada) — a touch strong
_STROKE_SOFT: Final = 0.80       # a `ra` within a compound — softer
_CHIKARI_VEL: Final = 1.10       # chikari — a bright accent
_CHIKARI_OCT: Final = 1          # ...on the taar-Sa drone strings (at least the upper octave)

# Murki / khatka — a light neighbour-cluster wrapping the note. ONE shape (upper + lower raga
# neighbour crushed before the main note), distinguished only by WEIGHT + how much of the note
# the cluster eats — exactly how the sources separate them (murki delicate, khatka sharper). See
# DESIGN.md "Murki/khatka".
_ORNAMENT_MIN_BEATS: Final = 0.5  # a note shorter than this can't carry a wrap-around ornament cleanly
_MURKI_VEL: Final = 0.82          # delicate — the cluster is softer than the note
_KHATKA_VEL: Final = 1.10         # sharper — the cluster is accented
_MURKI_FRONT: Final = 0.30        # the crushed cluster occupies this fraction of the note...
_KHATKA_FRONT: Final = 0.40       # ...a touch more for the heavier khatka


def _scaled_vel(vel: int, scale: float) -> int:
    return max(1, min(127, round(vel * scale)))


def apply_strokes(notes: list[LeadNote]) -> list[LeadNote]:
    """Realise each note's mizrab `bol` as sitar articulation — PURE, before placement.

    `da` is a strong stroke, `ra` a softer return, `diri` a fast da+ra DOUBLE-stroke (the note
    split in two — a PAIR), `darada` a da+ra+da TRIPLE-stroke (split in three — a TRIPLET), each of
    which also re-articulates (countering the sitar's decay), and `chikari` a bright high-Sa
    drone-string accent (its melodic swara is IGNORED — the chikari strings sound taar Sa). A note
    with no bol passes through. Each note's total duration is preserved (the split pieces sum to the
    original), so placement and timing are untouched, and the bol is consumed (cleared) here — the
    render `Note` never needs a bol field."""
    out: list[LeadNote] = []
    for n in notes:
        if n.rest:                                      # a silent beat carries no stroke — leave it as space
            out.append(n.model_copy())
        elif n.bol == "da":
            out.append(n.model_copy(update={"vel": _scaled_vel(n.vel, _BOL_DA_VEL), "bol": None}))
        elif n.bol == "ra":
            out.append(n.model_copy(update={"vel": _scaled_vel(n.vel, _BOL_RA_VEL), "bol": None}))
        elif n.bol in ("diri", "darada"):              # a compound = 2 (diri) or 3 (darada) strokes
            out.extend(_split_strokes(n, 2 if n.bol == "diri" else 3))
        elif n.bol == "chikari":                       # the bright high-Sa drone-string accent
            out.append(n.model_copy(update={"swara": "S", "oct": max(n.oct, _CHIKARI_OCT),
                                            "vel": _scaled_vel(n.vel, _CHIKARI_VEL), "grace": None,
                                            "meend_swara": None, "meend_oct": None, "bol": None}))
        else:
            out.append(n)
    return out


def _split_strokes(n: LeadNote, count: int) -> list[LeadNote]:
    """Split one note into `count` equal fast strokes (diri = 2 da-ra, darada = 3 da-ra-da),
    accenting on the da's (odd strokes) and softening the ra's. Grace stays on the FIRST stroke,
    meend is dropped (a compound is too fast to glide), and the pieces sum to the original dur."""
    piece = round(n.dur / count, 4)
    out: list[LeadNote] = []
    for i in range(count):
        dur = round(n.dur - piece * (count - 1), 4) if i == count - 1 else piece  # last takes the remainder
        scale = _STROKE_STRONG if i % 2 == 0 else _STROKE_SOFT                     # da, ra, da, ...
        out.append(n.model_copy(update={
            "dur": dur, "vel": _scaled_vel(n.vel, scale),
            "grace": n.grace if i == 0 else None,
            "meend_swara": None, "meend_oct": None, "bol": None}))
    return out


def strip_noop_meends(notes: list[LeadNote]) -> list[LeadNote]:
    """Strip meends that don't GLIDE — the target IS the written pitch. The LLM stamps
    `meend_swara == swara` on many notes as schema over-fill; the render anchors a meend on
    its target, so a no-op meend still pays the pre-bend gesture for nothing. Real meends
    (target differs) pass through untouched — the audible-line verifier judges those. Pure."""
    out: list[LeadNote] = []
    for n in notes:
        target_oct = n.meend_oct if n.meend_oct is not None else n.oct
        if n.meend_swara is not None and (n.meend_swara, target_oct) == (n.swara, n.oct):
            out.append(n.model_copy(update={"meend_swara": None, "meend_oct": None}))
        else:
            out.append(n)
    return out


# --------------------------------------------------------------------------- #
# Murki / khatka — realise an EXPRESSIVE ornament the composer asked for. Pure. #
# The counterpoint to andolan: andolan is a raga FACT code applies to a swara;  #
# these are a CHOICE the LLM places on a note. Code owns only the REALISATION — #
# the cluster is built from the raga's own scale neighbours, so it is legal by  #
# construction — and the per-raga GATE (a raga that doesn't use them plays the  #
# note plain). "The LLM decides where; code decides it stays in the grammar."   #
# --------------------------------------------------------------------------- #

def apply_ornaments(notes: list[LeadNote], raga: str) -> list[LeadNote]:
    """Realise any murki/khatka the composer flagged — but ONLY on a raga that uses them
    (`raga["ornaments"]`, a source-verified fact). On a raga that doesn't, the flag is stripped
    and the note plays plain, so a light Bhairavi ornament can't leak into a grave andolan raga
    like Darbari. Pure; runs BEFORE `apply_strokes` (the cluster carries no bol of its own)."""
    allowed = set(RAGAS[raga].get("ornaments", []))
    out: list[LeadNote] = []
    for n in notes:
        if n.ornament in allowed and n.ornament is not None:
            out.extend(_realize_ornament(n, raga))
        elif n.ornament is not None:            # asked for, not idiomatic here — strip it, play plain
            out.append(n.model_copy(update={"ornament": None}))
        else:
            out.append(n)
    return out


def _realize_ornament(n: LeadNote, raga: str) -> list[LeadNote]:
    """Expand ONE murki/khatka into its neighbour-cluster: the note's UPPER and LOWER raga-scale
    neighbours crushed fast, then the main note sustaining the remainder (so the structural note
    stays prominent). Both ornaments share this shape; a khatka is louder and eats a little more of
    the note than a murki — the sourced WEIGHT distinction, not a different note pattern. Neighbours
    come from the raga's own ladder (`scale_step_up` ±1), so the cluster is LEGAL BY CONSTRUCTION.
    A note too short to wrap passes through plain (the ornament can't speak on a fast note)."""
    if n.dur < _ORNAMENT_MIN_BEATS:
        return [n.model_copy(update={"ornament": None})]
    is_khatka = n.ornament == "khatka"
    up_sw, up_do = scale_step_up(n.swara, raga, 1)
    dn_sw, dn_do = scale_step_up(n.swara, raga, -1)          # -1 step = the lower neighbour
    front = round(n.dur * (_KHATKA_FRONT if is_khatka else _MURKI_FRONT), 4)
    piece = round(front / 2, 4)
    vel = _scaled_vel(n.vel, _KHATKA_VEL if is_khatka else _MURKI_VEL)
    cluster = [LeadNote(swara=up_sw, oct=n.oct + up_do, dur=piece, vel=vel),
               LeadNote(swara=dn_sw, oct=n.oct + dn_do, dur=piece, vel=vel)]
    main = n.model_copy(update={"dur": round(n.dur - piece * 2, 4),
                                "ornament": None, "grace": None})  # ornament replaces the kan
    return cluster + [main]


# --------------------------------------------------------------------------- #
# Voicing: render ONE melodic line as sitar and/or lead guitar. Pure.          #
# The Lead generator writes one line per section; the voicing decides which     #
# timbre(s) play it and whether the guitar harmonizes — a texture choice keyed   #
# to the section kind (an alaap sings on sitar; a taan is a harmonized shred).   #
# --------------------------------------------------------------------------- #

class Voicing(Enum):
    """How a section's lead line is voiced across sitar and lead guitar."""
    SITAR = "sitar"          # solo sitar — the raga voice
    GUITAR = "guitar"        # solo lead guitar — the metal shred voice
    UNISON = "unison"        # both, the same line (thickened)
    OCTAVE = "octave"        # both, an octave apart
    THIRD = "third"          # both, a raga-diatonic third apart (harmonized)


# Default voicing per section kind: the raga-idiom sections sing on sitar, the
# virtuosic metal sections move to (harmonized) lead guitar. A sensible default,
# not a law — a section could carry its own voicing hint later.
_VOICING_BY_KIND: Final[dict[SectionKind, Voicing]] = {
    SectionKind.ALAAP: Voicing.SITAR,
    SectionKind.MELODY: Voicing.UNISON,
    SectionKind.TAAN: Voicing.THIRD,
    SectionKind.SOLO: Voicing.GUITAR,
    SectionKind.BREAKDOWN: Voicing.GUITAR,
    SectionKind.OUTRO: Voicing.SITAR,
    SectionKind.RIFF: Voicing.SITAR,
}


def _voicing_for(section) -> Voicing:
    """The section's voicing — by KIND, with one form_role override: a MUKHADA always voices
    UNISON (sitar + guitar doubling), whatever section kind carries it. The head is the gat's
    identity and returns verbatim; its first statements ride melody-kind sections (unison) but
    the post-climax return often rides a riff-kind one, which voiced SOLO SITAR — the hook came
    back audibly thinner than it first appeared (Sujit's 2026-07-16 render)."""
    if is_mukhada(section):
        return Voicing.UNISON
    return _VOICING_BY_KIND.get(section.kind, Voicing.SITAR)


def _harmony_note(base: Note, swara: str, octave: int) -> Note:
    """A clean harmony note taken from a base note — NO kan/meend (the ornaments live
    on the melody line; doubling them on the harmony would clash)."""
    return Note(swara=swara, oct=octave, start=base.start, dur=base.dur, vel=base.vel)


# The call-and-response taan (Sujit, 2026-07-15): sitar and lead guitar playing the whole
# taan in constant harmony flattens the drama — instead they TRADE the line bar by bar
# (call, response, call, ...) and JOIN in a raga third only for the final avartan(s), so the
# two voices arriving together IS the climax. Deterministic: code owns which voice plays
# which bar; the line itself is untouched.
_JOIN_BARS_SHORT: Final = 1     # taans up to _JOIN_THRESHOLD bars join for the last bar...
_JOIN_BARS_LONG: Final = 2      # ...longer taans for the last two
_JOIN_THRESHOLD: Final = 4


def _voice_taan_call_response(line: list[Note], span: SectionSpan, cycle_beats: float,
                              raga: str) -> tuple[list[Note], list[Note]]:
    """Split a taan section's placed line into (sitar, guitar) by AVARTAN: the voices
    alternate solo bars (sitar calls, guitar responds), then both play the final bar(s) —
    guitar a raga-diatonic third above. Pure."""
    bars = span.section.bars
    join_bars = _JOIN_BARS_SHORT if bars <= _JOIN_THRESHOLD else _JOIN_BARS_LONG
    join_from = max(0, bars - join_bars)              # a 1-bar taan just joins (no room to trade)
    sitar: list[Note] = []
    guitar: list[Note] = []
    for n in line:
        bar = int((n.start - span.start) // cycle_beats)
        if bar >= join_from:                          # the JOIN — both voices, harmonized
            sitar.append(n)
            swara, octave_delta = scale_step_up(n.swara, raga, 2)
            guitar.append(_harmony_note(n, swara, n.oct + octave_delta))
        elif bar % 2 == 0:                            # the sitar's call
            sitar.append(n)
        else:                                         # the guitar's response
            guitar.append(n.model_copy())
    return sitar, guitar


def _voice_line(line: list[Note], voicing: Voicing, raga: str) -> tuple[list[Note], list[Note]]:
    """Split one melodic line into (sitar_notes, guitar_notes) per the voicing.

    Harmony is computed IN THE RAGA — octave = the same swara one octave up; third =
    two scale-degrees up the raga's ladder (`scale_step_up`) — so every harmony note
    is legal by construction. Unison copies the line verbatim (ornaments and all);
    octave and third strip ornaments for a clean double.
    """
    if voicing is Voicing.SITAR:
        return line, []
    if voicing is Voicing.GUITAR:
        return [], line
    if voicing is Voicing.UNISON:
        return line, [n.model_copy() for n in line]
    if voicing is Voicing.OCTAVE:
        return line, [_harmony_note(n, n.swara, n.oct + 1) for n in line]
    if voicing is Voicing.THIRD:
        harmony: list[Note] = []
        for n in line:
            swara, octave_delta = scale_step_up(n.swara, raga, 2)
            harmony.append(_harmony_note(n, swara, n.oct + octave_delta))
        return line, harmony
    raise ValueError(f"unknown voicing {voicing!r}")


# --------------------------------------------------------------------------- #
# Facts -> prompt text. Pure. (Shares shape with composers' raga renderer; when #
# the Riff generator lands as the third user, extract a shared fact-renderer.)  #
# --------------------------------------------------------------------------- #

@lru_cache(maxsize=1)
def _role_briefs() -> dict[str, Any]:
    """The per-role / per-kind lead briefs (`crew/config/lead_roles.yaml`), read once.

    Exactly ONE brief is injected per call as `{role_brief}` — the 2026-07-16 latency fix:
    the old universal prompt taught every gat role and section kind on every call, and the
    model deliberated over all of them (irrelevant rules cost thinking tokens, not just
    context)."""
    path = Path(__file__).parent / "config" / "lead_roles.yaml"
    return yaml.safe_load(path.read_text())


def _render_role_brief(section) -> str:
    """The one brief this section composes under: its gat `form_role`'s (the role subsumes
    the kind — a mukhada's rules cover its being an alaap or melody section), else its
    section kind's, else the generic default."""
    briefs = _role_briefs()
    role_text = briefs["roles"].get(section.form_role or "")
    if role_text is not None:
        return role_text
    return briefs["kinds"].get(section.kind.value, briefs["default"])


def render_direction_rule(rules: dict[str, str]) -> str:
    """One line naming the raga's one-directional swaras — data-derived (see
    `directional_varjya`), rendered for a prompt's raga facts."""
    down = [sw for sw, d in rules.items() if d == "avaroha"]
    up = [sw for sw, d in rules.items() if d == "aroha"]
    parts: list[str] = []
    if down:
        parts.append(f"{' '.join(down)} appear{'s' if len(down) == 1 else ''} ONLY in "
                     f"DESCENT — touch on the way down, approached from above, never "
                     f"from below (the aroha skips {'it' if len(down) == 1 else 'them'})")
    if up:
        parts.append(f"{' '.join(up)} appear{'s' if len(up) == 1 else ''} ONLY in "
                     f"ASCENT — approached from below, never from above")
    return "; ".join(parts)


def _render_raga_facts(raga: str) -> str:
    """The raga's facts the lead composes from — the single source of truth."""
    r = RAGAS[raga]
    lines = [
        f"  {r['display']} ({r['western_mode']}) — allowed swaras: {' '.join(r['allowed'])}",
        f"  aroha: {' '.join(r['aroha'])}   avaroha: {' '.join(r['avaroha'])}",
        f"  vadi {r['vadi']}, samvadi {r['samvadi']}",
        f"  pakad: {' | '.join(' '.join(p) for p in r['pakad'])}",
        f"  chalan: {' | '.join(' '.join(p) for p in r['chalan'])}",
    ]
    direction = directional_varjya(raga)
    if direction:
        lines.append(f"  direction rule — {render_direction_rule(direction)}")
    if r.get("andolan"):
        lines.append(f"  andolan — the code SWAYS these komal swaras when you HOLD them (a slow"
                     f" oscillation that defines the raga), so give them length: {' '.join(r['andolan'])}")
    if r.get("ornaments"):
        lines.append(f"  ornaments — light decorations idiomatic to THIS raga (flag a note's "
                     f"\"ornament\"; favour the komal notes): {', '.join(r['ornaments'])}")
    if r.get("kan"):
        kan = "; ".join(f"{sw}: kan {v['aroha']} ascending, {v['avaroha']} descending"
                        for sw, v in r["kan"].items())
        lines.append(f"  kan conventions: {kan}")
    return "\n".join(lines)


@dataclass(frozen=True)
class LeadMemo:
    """One realized prior lead section — the memory the NEXT section develops from.

    Composition MEMORY is how the music stops being a bag of unrelated sections: each
    lead phrase is generated seeing what the lead already played, so it can restate or
    vary the motif, answer the previous section, and build toward the climax. Holds the
    section kind, the phrase as the model emitted it (LOCAL octaves), and the section's
    gat form_role — labelling the memory lets a later cell FIND the head (the manjha and
    the taan fill both orbit the mukhada, so they must know which memory it is)."""
    kind: str
    phrase: LeadPhrase
    form_role: str | None = None


def _local_token(note: LeadNote) -> str:
    """One realized note as the model wrote it — swara with its LOCAL octave, its mizrab bol
    (`/da`) and a `~` for a meend — the frame (and the bol IDENTITY) the next phrase builds on,
    so a returning mukhada can restate the SAME bol pattern. A rest shows as `-` (the silence/nyas)."""
    if note.rest:
        return "-"
    tok = note.swara if note.oct == 0 else f"{note.swara}({note.oct:+d})"
    if note.bol:
        tok += f"/{note.bol}"
    if note.meend_swara is not None:
        tok += "~"
    return tok


def _render_previous(memory: list[LeadMemo]) -> str:
    """The lead's realized prior sections — its memory of the piece so far. Each line is
    labelled with the section's gat role, so the model can tell the head from the rest."""
    if not memory:
        return "  (this is the FIRST lead section — introduce the theme)"
    return "\n".join(
        f"  {memo.kind}{f' [{memo.form_role}]' if memo.form_role else ''}: "
        f"{' '.join(_local_token(n) for n in memo.phrase.notes)}"
        for memo in memory)


def _render_mukhada_head(memory: list[LeadMemo], *, tease: bool = False) -> str:
    """The cached gat HEAD, rendered for a cell that must RETURN to it (manjha / taan fill) —
    or, with `tease`, for the INTRO that must FORESHADOW it.

    CROSS-CELL awareness made explicit: the mukhada cache fixed the head's identity, and this
    extends it cell-to-cell — a manjha cannot honestly lead back into a head it has never seen,
    and an intro cannot tease a head it has never seen. For a returning cell it calls out the
    head's FIRST sounding swara (the seam the verifier will check); for the intro it directs
    the motif derivation the intro verifier will check."""
    memo = next((m for m in memory if m.form_role == _MUKHADA), None)
    if memo is None:
        return "  (no mukhada stated yet — not applicable to this section)"
    tokens = " ".join(_local_token(n) for n in memo.phrase.notes)
    if tease:
        return (f"  the head (ALREADY COMPOSED — it enters right after your closing held Sa):\n"
                f"  {tokens}\n"
                f"  derive your recurring motif (phrase_plan.seed) from its swaras and reveal it "
                f"phrase by phrase, so the mukhada arrives as the natural culmination of your idea.")
    sounding = [n for n in memo.phrase.notes if not n.rest]
    first = ("S" if sounding[0].bol == "chikari" else sounding[0].swara) if sounding else "S"
    return (f"  the head: {tokens}\n"
            f"  its FIRST note is {first} — the head re-enters on the sam right after you, so "
            f"shape your FINAL notes as a stepwise lead-in that flows into {first}.")


def _render_tala_position(span: SectionSpan, cycle_beats: float) -> str:
    """Where the sam falls INSIDE this section's window, so the lead can LAND on it. Pure.

    Sections are laid end-to-end on cycle boundaries, so a section starts on a sam and ends on
    one; the cycle downbeats inside the phrase are at local beats 0, C, 2C, ... This is the tala
    timing the lead used to lack — it was told to 'resolve on the sam' with no idea where the sam
    actually was (GPT's catch), so a taan could never reliably land."""
    bars = span.section.bars
    window = span.length
    sams = ", ".join(f"{i * cycle_beats:g}" for i in range(bars))
    return (f"one cycle = {cycle_beats:g} beats; your phrase spans {bars} cycle(s) "
            f"({window:g} beats). The sam (cycle downbeat) falls at beat(s) {sams} within your "
            f"phrase, and the phrase ENDS on the closing sam (beat {window:g}). Shape your "
            f"durations so a RESOLVING note lands on a sam — above all the final resolution, "
            f"which must arrive on the closing sam.")


def _render_repair(feedback: list[str] | None) -> str:
    """The gat verifier's violations from a FAILED prior attempt, rendered so a re-roll fixes
    exactly those. Serves every VERIFIED cell (mukhada, intro, manjha, taan fill); on the first
    attempt (no feedback) it is a benign line, so one prompt serves both. Code never edits the
    notes — it only tells the composer WHAT failed; the LLM re-composes the cell."""
    if not feedback:
        return "  (first attempt — compose freely within the rules above)"
    issues = "\n".join(f"    - {v}" for v in feedback)
    return ("  YOUR PREVIOUS ATTEMPT FAILED the gat structure check. Keep everything that already "
            "worked, and FIX EXACTLY these:\n" + issues)


def _riff_line_token(note: RiffNote) -> str:
    """One RiffNote as the LEAD sees it on the shared canvas — swara with its local octave
    and any power chord (+X) — enough for the lead to answer the riff's pitches and weight."""
    tok = note.swara if note.oct == 0 else f"{note.swara}({note.oct:+d})"
    return tok + "+" + "+".join(note.chord) if note.chord else tok


def _render_canvas_for_lead(canvas: SectionCanvas | None, move: CanvasMove) -> str:
    """What the lead SEES on this section's shared canvas, rendered for its MOVE. Pure.

    The cooperative pattern made concrete: on RESPOND the lead answers what the riff just
    played (call-and-response, not doubling); on REFINE it reworks its own line against the
    finished ensemble. When it OPENS the section (PROPOSE) or there is no canvas at all (the
    solo / non-studio path), the canvas is empty and the lead simply states the theme — so
    one prompt serves both the studio and the standalone generator."""
    if canvas is None or move is CanvasMove.PROPOSE:
        return "  (you OPEN this section — the canvas is empty; state the theme the band builds on)"
    lines: list[str] = []
    riff = canvas.riff
    if riff is not None:
        lines.append(f"  the Riff laid down: {' '.join(_riff_line_token(n) for n in riff.notes)}")
    if move is CanvasMove.RESPOND:
        lines.append("  ANSWER the riff — weave your line through its groove (call-and-response),"
                     " leaving space on its accents; do not merely double it."
                     if riff is not None else
                     "  (no riff on the canvas yet — lead the section.)")
    else:  # REFINE
        if canvas.lead is not None:
            lines.append(f"  your current line: {' '.join(_local_token(n) for n in canvas.lead.notes)}")
        lines.append("  REFINE your line to lock with the ensemble above — keep what works and"
                     " sharpen the interplay and the arc.")
    return "\n".join(lines)


class _LeadContext:
    """Assembles a lead turn's prompt inputs. The piece-level facts (raga, motif,
    register, tempo) are CONSTANT across a run, so they render once; the per-section
    fields and the realized-so-far MEMORY change per turn. Pure — no I/O."""

    def __init__(self, arr: Arrangement) -> None:
        from subgenres import SUBGENRES
        from talas import TALAS
        self._cycle_beats: float = arr.beats_per_bar
        self._static: dict[str, Any] = {
            "raga_block": _render_raga_facts(arr.raga),
            "motif": " ".join(arr.motif),
            "subgenre_feel": SUBGENRES[arr.subgenre]["feel"],
            "bpm": arr.bpm,
            "tala": TALAS[arr.tala]["display"],
            "output_schema": _OUTPUT_SCHEMA,
        }

    def inputs_for(self, span: SectionSpan, memory: list[LeadMemo], *,
                   canvas: SectionCanvas | None = None,
                   move: CanvasMove = CanvasMove.PROPOSE,
                   feedback: list[str] | None = None) -> dict[str, Any]:
        section = span.section
        return {
            **self._static,
            "section_kind": section.kind.value,
            "form_role": section.form_role or "free (no gat role set)",
            "role_brief": _render_role_brief(section),
            "section_intent": section.intent or "(none given — use your judgment for this kind)",
            "section_transition": section.transition or "(none given)",
            "window_beats": f"{span.length:g}",
            "tala_position": _render_tala_position(span, self._cycle_beats),
            "previous": _render_previous(memory),
            "mukhada_head": _render_mukhada_head(memory, tease=is_intro(section)),
            "move": move.value,
            "canvas": _render_canvas_for_lead(canvas, move),
            "repair": _render_repair(feedback),
        }


# --------------------------------------------------------------------------- #
# Boundary parsing + the legality guardrail (the hard line). Imperative-ish.   #
# --------------------------------------------------------------------------- #

def _phrase_from_output(output: Any) -> LeadPhrase | None:
    """The LeadPhrase CrewAI parsed via output_pydantic (or None if parsing failed)."""
    parsed = getattr(output, "pydantic", None)
    if isinstance(parsed, LeadPhrase):
        return parsed
    raw = getattr(output, "raw", None)
    try:
        return LeadPhrase.model_validate_json(raw) if raw else None
    except ValidationError:
        return None


def _phrase_swaras(phrase: LeadPhrase) -> list[str]:
    """Every swara the phrase commits to — the declared seed, plus each note, its kan and
    its meend target — flattened so the raga grammar can judge them all (no ornament or
    seed blind spot; a seed the raga forbids fails the guardrail like any other)."""
    swaras: list[str] = list(phrase.phrase_plan.seed)
    for note in phrase.notes:
        if note.rest:                      # a rest sounds nothing — its swara is an ignored placeholder
            continue
        if note.bol == "chikari":          # chikari sounds taar Sa (always legal); its written swara is ignored
            continue
        swaras.append(note.swara)
        swaras.extend(note.grace or [])
        if note.meend_swara is not None:
            swaras.append(note.meend_swara)
    return swaras


def _phrase_direction_seq(phrase: LeadPhrase) -> list[tuple[str, int]]:
    """The phrase's sounding line as (swara, octave) steps for the direction rule — a
    meend adds its own step (the glide LANDS on the target), rests and chikari are
    skipped (punctuation, not melodic entries)."""
    seq: list[tuple[str, int]] = []
    for n in phrase.notes:
        if n.rest or n.bol == "chikari":
            continue
        seq.append((n.swara, n.oct))
        if n.meend_swara is not None:
            seq.append((n.meend_swara, n.meend_oct if n.meend_oct is not None else n.oct))
    return seq


def _phrase_grammar_error(phrase: LeadPhrase, raga: str) -> str | None:
    """The ONE domain rule both lead guardrails share, as a precise retryable error (or
    None when clean): every swara the phrase sounds must be legal in the raga, and a
    one-directional swara (Bageshree's descent-only P...) must be entered from its own
    side (`direction_violations` — the same data-derived rule the prompt states)."""
    illegal = motif_illegal_in_raga(_phrase_swaras(phrase), raga)
    if illegal:
        allowed = " ".join(RAGAS[raga]["allowed"])
        return (f"swaras {sorted(set(illegal))} are illegal in raga {raga}. "
                f"Use only these swaras: {allowed}. Fix and resend.")
    direction = direction_violations(_phrase_direction_seq(phrase), raga)
    if direction:
        return "; ".join(dict.fromkeys(direction)) + ". Fix the approach and resend."
    return None


def _lead_guardrail(raga: str):
    """Build the Task guardrail for a given raga: the raga-grammar rule — legal swaras,
    entered from the legal direction (`_phrase_grammar_error`). `output_pydantic`
    guarantees the SHAPE; this checks the grammar and, on a violation, returns the
    precise error so CrewAI re-runs the section (a bounded retry, not a loop).

    Contract: returns (True, LeadPhrase) or (False, error-message). CrewAI reads the
    guardrail's RETURN ANNOTATION and requires the literal object tuple[bool, Any];
    `from __future__ import annotations` would stringify a normal hint, so it is set
    as a real object on the closure below.
    """
    def guard(output: Any):
        phrase = _phrase_from_output(output)
        if phrase is None:
            return (False, "Return a single valid LeadPhrase JSON object and nothing else.")
        error = _phrase_grammar_error(phrase, raga)
        if error:
            return (False, error)
        return (True, phrase)

    guard.__annotations__["return"] = tuple[bool, Any]
    return guard


class _LeadCrew:
    """Runs ONE section's lead generation as an isolated single-agent crew.

    Config is read once at construction; each call builds the per-section task with
    the raga-bound guardrail. Structured output is CrewAI's job (`output_pydantic`),
    so there is no hand-rolled JSON parsing beyond the defensive fallback.
    """

    def __init__(self) -> None:
        config_dir = Path(__file__).parent / "config"
        self._agent_config = yaml.safe_load((config_dir / "agents.yaml").read_text())["lead"]
        self._task_config = yaml.safe_load((config_dir / "tasks.yaml").read_text())["generate_lead"]

    def run(self, raga: str, inputs: dict[str, Any]) -> LeadPhrase:
        agent = Agent(config=self._agent_config, llm=generator_llm(),
                      allow_delegation=False, max_iter=GENERATOR_MAX_ITER,
                      max_retry_limit=AGENT_RETRY_LIMIT, verbose=False)
        task = Task(config=self._task_config, agent=agent, output_pydantic=LeadPhrase,
                    guardrail=_lead_guardrail(raga), guardrail_max_retries=GENERATOR_RETRIES)
        crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)
        phrase = _phrase_from_output(crew.kickoff(inputs=inputs))
        if phrase is None:
            raise ValueError("lead generator returned no parseable LeadPhrase")
        return phrase


class LeadFn(Protocol):
    """A phrase provider: given a section span, the chart, and the memory of the sections
    realized so far, return this section's lead phrase. `feedback` (optional) carries the gat
    verifier's violations from a failed prior attempt, so a RE-ROLL can fix exactly those — the
    LLM re-composes the head (no code note-surgery); code only decides WHAT was wrong."""

    def __call__(self, span: SectionSpan, arr: Arrangement, memory: list[LeadMemo], *,
                 feedback: list[str] | None = None) -> LeadPhrase: ...


class _LLMLead:
    """The real (LLM-backed) `gen_fn` — holds the crew and the precomputed context."""

    def __init__(self, arr: Arrangement) -> None:
        self._crew = _LeadCrew()
        self._context = _LeadContext(arr)

    def __call__(self, span: SectionSpan, arr: Arrangement, memory: list[LeadMemo], *,
                 feedback: list[str] | None = None) -> LeadPhrase:
        return self._crew.run(arr.raga, self._context.inputs_for(span, memory, feedback=feedback))


# --------------------------------------------------------------------------- #
# The WHOLE-GAT generator: mukhada + manjha + antara composed as ONE object.   #
# --------------------------------------------------------------------------- #

# The Gat JSON we want back — each part is a lead phrase (see _OUTPUT_SCHEMA for the phrase shape).
_GAT_OUTPUT_SCHEMA: Final = (
    '{\n'
    '  "anchor": "one line: the single idea seeding all three parts (a pakad phrase, a register plan)",\n'
    '  "mukhada": <a phrase — the madhya HEAD>,\n'
    '  "manjha":  <a phrase — the mandra BRIDGE (omit unless asked)>,\n'
    '  "antara":  <a phrase — the taar SECOND THEME (omit unless asked)>\n'
    '}\n'
    'Each of mukhada / manjha / antara has the SAME shape as one lead phrase:\n' + _OUTPUT_SCHEMA
)


class GatFn(Protocol):
    """A gat provider: compose the whole gat (mukhada + optionally manjha/antara) for a chart as
    ONE coherent object. `needs_manjha`/`needs_antara` say which optional parts the arrangement
    actually uses, so tokens aren't spent on parts that won't be rendered."""

    def __call__(self, arr: Arrangement, *, needs_manjha: bool, needs_antara: bool) -> Gat: ...


class _GatContext:
    """Assembles the whole-gat prompt inputs — the piece-level facts plus which parts to compose.
    Pure; no per-section span (the gat is composed as a unit, not a section)."""

    def __init__(self, arr: Arrangement) -> None:
        from subgenres import SUBGENRES
        from talas import TALAS
        self._static: dict[str, Any] = {
            "raga_block": _render_raga_facts(arr.raga),
            "motif": " ".join(arr.motif),
            "subgenre_feel": SUBGENRES[arr.subgenre]["feel"],
            "bpm": arr.bpm,
            "tala": TALAS[arr.tala]["display"],
            "cycle_beats": f"{arr.beats_per_bar:g}",
            "gat_output_schema": _GAT_OUTPUT_SCHEMA,
        }

    def inputs_for(self, *, needs_manjha: bool, needs_antara: bool) -> dict[str, Any]:
        parts = ["mukhada"] + (["manjha"] if needs_manjha else []) + (["antara"] if needs_antara else [])
        return {**self._static, "parts_needed": ", ".join(parts)}


def _gat_from_output(output: Any) -> Gat | None:
    """The Gat CrewAI parsed via output_pydantic (or None if parsing failed)."""
    parsed = getattr(output, "pydantic", None)
    if isinstance(parsed, Gat):
        return parsed
    raw = getattr(output, "raw", None)
    try:
        return Gat.model_validate_json(raw) if raw else None
    except ValidationError:
        return None


def _gat_guardrail(raga: str):
    """Build the whole-gat guardrail: every part faces the same raga-grammar rule as the
    per-section lead (`_phrase_grammar_error` — legal swaras, entered from the legal
    direction), each violation named with its part."""
    def guard(output: Any):
        gat = _gat_from_output(output)
        if gat is None:
            return (False, "Return a single valid Gat JSON object and nothing else.")
        for name, part in (("mukhada", gat.mukhada), ("manjha", gat.manjha),
                           ("antara", gat.antara)):
            if part is None:
                continue
            error = _phrase_grammar_error(part, raga)
            if error:
                return (False, f"in the {name}: {error}")
        return (True, gat)

    guard.__annotations__["return"] = tuple[bool, Any]
    return guard


class _GatCrew:
    """Runs the whole-gat generation as an isolated single-agent crew (the `lead` agent), mirroring
    `_LeadCrew` — config read once, `output_pydantic=Gat` for the shape, the raga-bound guardrail
    for legality."""

    def __init__(self) -> None:
        config_dir = Path(__file__).parent / "config"
        self._agent_config = yaml.safe_load((config_dir / "agents.yaml").read_text())["lead"]
        self._task_config = yaml.safe_load((config_dir / "tasks.yaml").read_text())["generate_gat"]

    def run(self, raga: str, inputs: dict[str, Any]) -> Gat:
        agent = Agent(config=self._agent_config, llm=generator_llm(),
                      allow_delegation=False, max_iter=GENERATOR_MAX_ITER,
                      max_retry_limit=AGENT_RETRY_LIMIT, verbose=False)
        task = Task(config=self._task_config, agent=agent, output_pydantic=Gat,
                    guardrail=_gat_guardrail(raga), guardrail_max_retries=GENERATOR_RETRIES)
        crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)
        gat = _gat_from_output(crew.kickoff(inputs=inputs))
        if gat is None:
            raise ValueError("gat generator returned no parseable Gat")
        return gat


class _LLMGat:
    """The real (LLM-backed) `gat_fn` — holds the crew and the precomputed context."""

    def __init__(self, arr: Arrangement) -> None:
        self._crew = _GatCrew()
        self._context = _GatContext(arr)

    def __call__(self, arr: Arrangement, *, needs_manjha: bool, needs_antara: bool) -> Gat:
        return self._crew.run(
            arr.raga, self._context.inputs_for(needs_manjha=needs_manjha, needs_antara=needs_antara))


# --------------------------------------------------------------------------- #
# The generator loop — pure control flow, LLM injected via `gen_fn`.           #
# --------------------------------------------------------------------------- #

def _render_plan(plan: PhrasePlan) -> str:
    """One-line human view of the compositional plan, for the trace and the debate event."""
    seed = " ".join(plan.seed) or "?"
    moves = " → ".join(plan.transformations) or "—"
    line = f"seed [{seed}] · {plan.contour} · {moves} · {plan.climax_and_sam}"
    if plan.taan_style:
        line = f"{plan.taan_style} taan · {line}"
    if plan.badhat_plan:
        line = f"{line} · badhat: {plan.badhat_plan}"
    return line


def _lead_event(span: SectionSpan, phrase: LeadPhrase, line: list[Note],
                voicing: Voicing) -> DebateEvent:
    return DebateEvent(
        type=EventType.PROPOSE, agent="Lead", role=_ROLE_GENERATOR,
        text=f"{span.section.kind.value}: {len(line)} notes over {span.length:g} beats "
             f"[{voicing.value}]",
        data={"reasoning": _render_plan(phrase.phrase_plan), "voicing": voicing.value,
              "swaras": [n.swara for n in line]})


def _lead_reprise_event(span: SectionSpan) -> DebateEvent:
    """The mukhada RETURNS — code reuses the cached head verbatim (no LLM call). A light INFO
    beat (not a fresh PROPOSE) so the timeline shows the gat hook coming back, mirroring the
    riff's reprise event."""
    bars = span.section.bars
    return DebateEvent(
        type=EventType.INFO, agent="Lead", role=_ROLE_GENERATOR,
        text=f"reprise: the mukhada returns ({bars} avartan{'s' if bars != 1 else ''})",
        data={"form_role": _MUKHADA, "reprise": True})


def _gat_repair_event(role: str, tries: int, violations: list[str]) -> DebateEvent:
    """The gat verifier caught a weak cell and RE-ROLLED it (bounded). Shows the TIME-legality
    repair in the timeline/trace — the early local fix, before the late critics run. Notes whether
    the re-roll landed clean or code kept the best-of-N with issues remaining."""
    tail = f"still flags: {'; '.join(violations)}" if violations else "clean"
    return DebateEvent(
        type=EventType.INFO, agent="Lead", role=_ROLE_GENERATOR,
        text=f"gat verify: {role} re-rolled ({tries} tries) -> {tail}",
        data={"gat_verify": True, "cell": role, "tries": tries, "violations": violations})


# A verifier bound to its cell's context (cycle/window/head), applied to a candidate phrase.
type CellVerifier = Callable[[LeadPhrase], list[str]]


def _generate_verified_cell(gen_span: SectionSpan, arr: Arrangement, memory: list[LeadMemo], *,
                            gen_fn: LeadFn, verify: CellVerifier) -> tuple[LeadPhrase, int, list[str]]:
    """Generate a VERIFIED gat cell (mukhada / intro / manjha / taan fill), RE-ROLLING a weak
    one up to `_CELL_REPAIR_TRIES` times. The re-roll is FED the exact violations (a targeted
    re-roll, not a blind one) so the LLM re-composes the cell to fix precisely what failed — code
    never edits the notes. Bounded, keeping the best-of-N (fewest violations) if none come back
    clean. Returns (cell, tries_used, remaining_violations). Pure control flow: the verifiers are
    deterministic and `gen_fn` is injected, so this repair loop tests with no LLM (the live
    `beat`s are ambient no-ops without a sink)."""
    cell_name = gen_span.section.form_role or gen_span.section.kind.value
    best_cell: LeadPhrase | None = None
    best_viol: list[str] | None = None
    feedback: list[str] | None = None                        # None on attempt 1; the prior violations after
    for attempt in range(_CELL_REPAIR_TRIES + 1):
        if feedback is None:
            beat("Lead", f"composing the {cell_name}…")
        else:                                                # SHOW WHY the piece is being redone
            beat("Lead", f"re-rolling the {cell_name} — flagged: {flags(feedback)}",
                 data={"violations": feedback, "cell": cell_name, "attempt": attempt + 1})
        cell = gen_fn(gen_span, arr, list(memory), feedback=feedback)
        viol = verify(cell)
        if not viol:
            return cell, attempt + 1, []
        feedback = viol                                      # the re-roll sees EXACTLY what failed
        if best_viol is None or len(viol) < len(best_viol):
            best_cell, best_viol = cell, viol
    assert best_cell is not None and best_viol is not None    # the loop runs at least once
    return best_cell, _CELL_REPAIR_TRIES + 1, best_viol


def _verify_or_repair_part(part: LeadPhrase, role: str, gen_span: SectionSpan, arr: Arrangement,
                           memory: list[LeadMemo], *, verify: CellVerifier, gen_fn: LeadFn,
                           events: list[DebateEvent]) -> LeadPhrase:
    """A gat part from the joint composition: KEEP it if it passes its verifier; otherwise repair
    it IN ISOLATION — regenerate ONLY this part (the already-accepted parts stay fixed and are in
    `memory`), via the per-section `gen_fn` bounded re-roll. The joint call gives coherence; this
    keeps a single weak part from forcing a whole-gat rewrite (Sujit's steer, 2026-07-16)."""
    part_viol = verify(part)
    if not part_viol:
        return part                                  # the jointly-composed part is clean — keep it
    beat("Lead", f"the gat's {role} failed its check — repairing in isolation; flagged: "
                 f"{flags(part_viol)}", data={"violations": part_viol, "cell": role})
    repaired, tries, viol = _generate_verified_cell(gen_span, arr, memory, gen_fn=gen_fn, verify=verify)
    events.append(_gat_repair_event(f"{role} (gat, in isolation)", tries + 1, viol))
    return repaired


def _compose_gat(arr: Arrangement, *, gat_fn: GatFn, gen_fn: LeadFn,
                 events: list[DebateEvent]) -> Gat | None:
    """Compose the gat as ONE object — mukhada + (manjha) + (antara) in a single `gat_fn` call so
    they share a motif and a register arc — then verify each part and repair a failing one in
    isolation. Returns None when the arrangement has no mukhada (nothing to compose jointly). Pure
    control flow: `gat_fn` and `gen_fn` are injected, so this is fully tested with no LLM."""
    spans = list(section_spans(arr))
    mspan = next((s for s in spans if is_mukhada(s.section)), None)
    if mspan is None:
        return None
    manjha_span = next((s for s in spans if is_manjha(s.section)), None)
    antara_span = next((s for s in spans if is_antara(s.section)), None)
    cycle, raga = arr.beats_per_bar, arr.raga

    beat("Lead", "composing the whole gat (mukhada + manjha + antara) in one call…")
    gat = gat_fn(arr, needs_manjha=manjha_span is not None, needs_antara=antara_span is not None)
    parts = "mukhada" + (" + manjha" if manjha_span else "") + (" + antara" if antara_span else "")
    events.append(DebateEvent(
        type=EventType.INFO, agent="Lead", role=_ROLE_GENERATOR,
        text=f"gat composed as ONE object ({parts})" + (f" — {gat.anchor}" if gat.anchor else ""),
        data={"gat": True, "anchor": gat.anchor, "parts": parts}))

    memory: list[LeadMemo] = []
    mukhada = _verify_or_repair_part(
        gat.mukhada, _MUKHADA, _one_cycle_span(mspan, cycle), arr, memory,
        verify=lambda c: verify_mukhada(c, cycle_beats=cycle, raga=raga), gen_fn=gen_fn, events=events)
    memory.append(LeadMemo(mspan.section.kind.value, mukhada, _MUKHADA))

    manjha = None
    if manjha_span is not None:
        gen_span = _manjha_gen_span(manjha_span, cycle)
        window = gen_span.length
        manjha = _verify_or_repair_part(
            gat.manjha or mukhada, _MANJHA, gen_span, arr, memory,
            verify=lambda c: verify_manjha(c, mukhada=mukhada, window_beats=window, raga=raga),
            gen_fn=gen_fn, events=events)
        memory.append(LeadMemo(manjha_span.section.kind.value, manjha, _MANJHA))

    antara = None
    if antara_span is not None:
        antara = _verify_or_repair_part(
            gat.antara or mukhada, _ANTARA, antara_span, arr, memory,
            verify=lambda c: verify_antara(c, mukhada=mukhada, window_beats=antara_span.length, raga=raga),
            gen_fn=gen_fn, events=events)

    return Gat(anchor=gat.anchor, mukhada=mukhada, manjha=manjha, antara=antara)


def _fill_gen_span(span: SectionSpan, cycle_beats: float, head_first: str) -> SectionSpan:
    """The synthetic span a mukhada taan FILL is generated against: half an avartan, framed as
    a `taan_short` with an intent that states the splice contract (where it cuts in, that it
    moves in sixteenths, and that it resolves into the head's first swara on the next sam)."""
    half = cycle_beats * _FILL_FRACTION
    section = span.section.model_copy(update={
        "kind": SectionKind.TAAN, "bars": 1, "form_role": "taan_short",
        "intent": (f"a taan FILL spliced into the mukhada: the head plays the first "
                   f"{cycle_beats - half:g} beats of the avartan, then YOU take the last "
                   f"{half:g} beats — one burst of sixteenth-notes (dur 0.25; only the final "
                   f"landing note may be longer) that resolves stepwise into the head's first "
                   f"swara ({head_first}), arriving exactly on the next sam"),
    })
    return SectionSpan(index=span.index, section=section,
                       start=span.start, end=span.start + half)


def _fill_event(fills: list[LeadPhrase], half_beats: float) -> DebateEvent:
    """The taan fills are written once and spliced by code into the middle statements of the
    long mukhada sections — a light INFO beat so the timeline shows the gat technique."""
    n = len(fills)
    return DebateEvent(
        type=EventType.INFO, agent="Lead", role=_ROLE_GENERATOR,
        text=f"gat fills: {n} distinct {half_beats:g}-beat sixteenth-note taan{'s' if n != 1 else ''} "
             f"will cut into the mukhada's middle statements and resolve back into the head",
        data={"form_role": "taan_short", "fill": True, "count": n,
              "swaras": [[x.swara for x in f.notes if not x.rest] for f in fills]})


def _lead_layer(voice_name: str, notes: list[Note]) -> Layer:
    """Build a lead Layer for one timbre (sitar or lead_guitar). Both carry the
    `lead` role; the patch, channel, and pan differ (sitar left / lead guitar right,
    so a harmonized third separates across the stereo field)."""
    voice = VOICES[voice_name]
    return Layer(role=_LEAD_ROLE, instrument=voice.instrument, program=voice.program,
                 channel=voice.channel, pan=voice.pan, notes=notes)


def lead_layers_from(phrases: dict[int, LeadPhrase], arr: Arrangement,
                     fills: list[LeadPhrase] | None = None) -> list[Layer]:
    """Assemble the lead layer(s) from already-generated per-section phrases (section index
    -> phrase). Places and VOICES each phrase exactly as the fan-out does — solo sitar,
    solo lead guitar, unison, octave, or a raga-diatonic third — so the studio, which
    generates phrases on the shared canvas rather than in the fan-out loop, produces
    identical layers. A section with no phrase (a voice that laid out) is skipped. `fills`
    (optional) are the verified sixteenth-note taans, ROTATED across the fill slots of the
    long mukhada sections so consecutive cuts are distinct taans, not one repeated lick. Pure."""
    sitar_notes: list[Note] = []
    guitar_notes: list[Note] = []
    andolan_swaras = frozenset(RAGAS[arr.raga].get("andolan", []))   # a raga fact; empty -> no sway
    fill_notes = [apply_strokes(apply_ornaments(strip_noop_meends(f.notes), arr.raga))
                  for f in fills or []]
    fill_cursor = 0
    for span in section_spans(arr):
        phrase = phrases.get(span.index)
        if phrase is None:
            continue
        bar_fills: dict[int, list[LeadNote]] = {}
        if fill_notes:
            for bar in _fill_bars(span.section):
                bar_fills[bar] = fill_notes[fill_cursor % len(fill_notes)]
                fill_cursor += 1
        processed = apply_strokes(apply_ornaments(strip_noop_meends(phrase.notes), arr.raga))
        if is_intro(span.section) and _CLEAN_ROLE in span.section.layers:
            # The alap LOCKS to the clean arpeggio: a lead-in avartan of arpeggio alone, then
            # each phrase enters on a sam (`_place_intro_phrases`) instead of drifting flush-left.
            gen_span = _intro_gen_span(span, arr.beats_per_bar)
            line = _place_intro_phrases(processed, gen_span=gen_span, section_span=span,
                                        register=arr.registers[_LEAD_ROLE],
                                        cycle_beats=arr.beats_per_bar,
                                        andolan_swaras=andolan_swaras)
            line = _ring_out_intro(line, span)        # the final Sa rings into the reserved gap
        elif is_intro(span.section):
            line = _place_lead_section(processed, span=span, register=arr.registers[_LEAD_ROLE],
                                       cycle_beats=arr.beats_per_bar, andolan_swaras=andolan_swaras)
            line = _ring_out_intro(line, span)        # the final Sa rings into the reserved gap
        else:
            line = _place_lead_section(processed, span=span, register=arr.registers[_LEAD_ROLE],
                                       cycle_beats=arr.beats_per_bar,
                                       andolan_swaras=andolan_swaras, bar_fills=bar_fills)
        if span.section.kind is SectionKind.TAAN:     # the solo trades bars, then joins
            sitar_line, guitar_line = _voice_taan_call_response(
                line, span, arr.beats_per_bar, arr.raga)
        else:
            sitar_line, guitar_line = _voice_line(line, _voicing_for(span.section), arr.raga)
        sitar_notes.extend(sitar_line)
        guitar_notes.extend(guitar_line)
    layers: list[Layer] = []
    if sitar_notes:
        layers.append(_lead_layer("sitar", sitar_notes))
    if guitar_notes:
        layers.append(_lead_layer("lead_guitar", guitar_notes))
    return layers


def _fill_slot_count(arr: Arrangement) -> int:
    """How many fill slots (cut statements) the arrangement's lead-active mukhada sections
    offer — the number of DISTINCT fill cells to write is capped by this and `_FILL_VARIANTS`."""
    return sum(len(_fill_bars(s)) for s in arr.sections if _LEAD_ROLE in s.layers)


def generate_lead(arr: Arrangement, *, gen_fn: LeadFn,
                  gat_fn: GatFn | None = None) -> tuple[list[Layer], list[DebateEvent]]:
    """Fill the lead across the arrangement's lead-active sections, VOICED.

    For each section that lists `lead`: get a phrase (threading the realized prior sections as
    memory), then assemble every phrase into a sitar line and/or a lead-guitar line via
    `lead_layers_from`. Returns up to TWO layers and an empty list when no section uses the lead.
    `gen_fn` (and `gat_fn`) are injected so this loop is tested with no LLM.

    WHOLE-GAT COMPOSITION (Sujit + GPT, 2026-07-16): when a `gat_fn` is given, the mukhada, manjha
    and antara are composed TOGETHER as ONE coherent object (a single call — a shared motif and a
    planned register arc: madhya head, mandra bridge, taar answer), the way a musician conceives a
    gat, rather than three lines composed in isolation. Each part is then verified and — if it
    fails — repaired IN ISOLATION (the others held fixed; nobody rewrites a whole gat for one weak
    antara). Absent a `gat_fn` (the studio path, most tests), each gat part falls back to the
    per-section generation below, unchanged.

    The STRUCTURED GAT CELLS are special — each is generated against its own deterministic
    verifier with a bounded feedback re-roll (`_generate_verified_cell`):
      * the FIRST `mukhada` is written as exactly ONE avartan and CACHED; every later mukhada
        reuses the cell verbatim (the hook returns identically instead of drifting), and code
        loops it across each section's bars;
      * an `intro` is verified to establish and RESOLVE to Sa with true rests, and is generated
        into a SHORTENED window so code reserves a real silence before the gat enters;
      * a `manjha` is generated KNOWING the cached head (cross-cell awareness) and verified to
        arrive at the sam and LEAD BACK into the head's first swara;
      * when a mukhada section runs long, ONE sixteenth-note taan FILL is written (verified to
        move in sixteenths and resolve into the head) and code splices it into the middle
        statement of every such section.
    Every other role is generated once across its whole window, as before.
    """
    events: list[DebateEvent] = []
    phrases: dict[int, LeadPhrase] = {}
    memory: list[LeadMemo] = []                     # the sections realized so far — the memory
    mukhada_cell: LeadPhrase | None = None          # the cached gat head, reused on every return
    fill_cells: list[LeadPhrase] = []               # the distinct taan fills spliced into long mukhadas
    cycle_beats = arr.beats_per_bar
    register = arr.registers[_LEAD_ROLE]
    raga = arr.raga
    gat = _compose_gat(arr, gat_fn=gat_fn, gen_fn=gen_fn, events=events) if gat_fn else None
    # The head as a memo, for cells generated BEFORE the mukhada span is reached (the intro
    # precedes the head in the timeline but the gat is composed first): injected into the
    # intro's memory so the `{mukhada_head}` block can show the head it must tease — the same
    # pattern `_generate_fills` uses to show the head to a fill.
    head_memo: LeadMemo | None = None
    if gat is not None:
        mukhada_kind = next(s.section.kind.value for s in section_spans(arr)
                            if is_mukhada(s.section))
        head_memo = LeadMemo(mukhada_kind, gat.mukhada, _MUKHADA)
    for span in section_spans(arr):
        section = span.section
        if _LEAD_ROLE not in section.layers:
            continue
        if is_mukhada(section) and mukhada_cell is not None:
            phrase = mukhada_cell                   # the hook RETURNS — reuse, don't regenerate
            events.append(_lead_reprise_event(span))
        elif is_mukhada(section):                   # the FIRST mukhada — from the joint gat, or per-section
            if gat is not None:
                phrase, tries, viol = gat.mukhada, 1, []   # composed with the manjha/antara, already repaired
            else:
                gen_span = _one_cycle_span(span, cycle_beats)
                phrase, tries, viol = _generate_verified_cell(
                    gen_span, arr, memory, gen_fn=gen_fn,
                    verify=lambda c: verify_mukhada(c, cycle_beats=cycle_beats, raga=raga))
            mukhada_cell = phrase                   # cache the head for its returns
            line = _place_lead_section(phrase.notes, span=span, register=register,
                                       cycle_beats=cycle_beats)
            events.append(_lead_event(span, phrase, line, _voicing_for(section)))
            # The head rides the event stream (see `mukhada_cell_from_events`) so the RIFF
            # generator — which runs after the lead — can reduce it, with no signature churn.
            events[-1].data["mukhada_cell"] = phrase.model_dump(exclude_none=True)
            if tries > 1:                           # the verifier re-rolled a weak hook — show it
                events.append(_gat_repair_event(_MUKHADA, tries, viol))
            fill_cells = _generate_fills(span, arr, memory, mukhada_cell,
                                         gen_fn=gen_fn, events=events)
        elif is_intro(section):                     # the alap — verified, with a code-reserved pause
            gen_span = _intro_gen_span(span, cycle_beats)
            window = gen_span.length                # the SHORTENED window — overrun eats the silence
            head = gat.mukhada if gat is not None else None
            intro_memory = memory + [head_memo] if head_memo is not None else memory
            phrase, tries, viol = _generate_verified_cell(
                gen_span, arr, intro_memory, gen_fn=gen_fn,
                verify=lambda c: verify_intro(c, window_beats=window, raga=raga, mukhada=head))
            if _CLEAN_ROLE in section.layers:         # the event shows the real avartan-locked placement
                line = _place_intro_phrases(phrase.notes, gen_span=gen_span, section_span=span,
                                            register=register, cycle_beats=cycle_beats)
            else:
                line = _place_lead_section(phrase.notes, span=span, register=register,
                                           cycle_beats=cycle_beats)
            events.append(_lead_event(span, phrase, line, _voicing_for(section)))
            if tries > 1:
                events.append(_gat_repair_event(_INTRO, tries, viol))
        elif is_manjha(section) and mukhada_cell is not None:  # the SHORT low bridge back to the head
            if gat is not None and gat.manjha is not None:
                phrase, tries, viol = gat.manjha, 1, []       # composed as part of the gat, already repaired
            else:
                head = mukhada_cell
                gen_span = _manjha_gen_span(span, cycle_beats)  # short, sub-cycle window (code reserves the rest)
                window = gen_span.length
                phrase, tries, viol = _generate_verified_cell(
                    gen_span, arr, memory, gen_fn=gen_fn,
                    verify=lambda c: verify_manjha(c, mukhada=head, window_beats=window, raga=raga))
            line = _place_lead_section(phrase.notes, span=span, register=register,
                                       cycle_beats=cycle_beats)
            events.append(_lead_event(span, phrase, line, _voicing_for(section)))
            if tries > 1:
                events.append(_gat_repair_event(_MANJHA, tries, viol))
        elif is_antara(section) and mukhada_cell is not None:  # the second movement — the verified arc
            if gat is not None and gat.antara is not None:
                phrase, tries, viol = gat.antara, 1, []       # composed as part of the gat, already repaired
            else:
                head = mukhada_cell
                phrase, tries, viol = _generate_verified_cell(
                    span, arr, memory, gen_fn=gen_fn,
                    verify=lambda c: verify_antara(c, mukhada=head, window_beats=span.length,
                                                   raga=raga))
            line = _place_lead_section(phrase.notes, span=span, register=register,
                                       cycle_beats=cycle_beats)
            events.append(_lead_event(span, phrase, line, _voicing_for(section)))
            if tries > 1:
                events.append(_gat_repair_event(_ANTARA, tries, viol))
        elif is_taan_long(section):                 # the developed peak — motif-grown, arced, burst+space
            phrase, tries, viol = _generate_verified_cell(
                span, arr, memory, gen_fn=gen_fn,
                verify=lambda c: verify_taan(c, motif=arr.motif, window_beats=span.length,
                                             raga=raga))
            line = _place_lead_section(phrase.notes, span=span, register=register,
                                       cycle_beats=cycle_beats)
            events.append(_lead_event(span, phrase, line, _voicing_for(section)))
            if tries > 1:
                events.append(_gat_repair_event(_TAAN_LONG, tries, viol))
        else:
            beat("Lead", f"composing the {section.kind.value} line…")
            phrase = gen_fn(span, arr, list(memory))   # a COPY, so gen_fn can't mutate history
            line = _place_lead_section(phrase.notes, span=span, register=register,
                                       cycle_beats=cycle_beats)
            events.append(_lead_event(span, phrase, line, _voicing_for(section)))
        phrases[span.index] = phrase
        memory.append(LeadMemo(section.kind.value, phrase, section.form_role))

    layers = lead_layers_from(phrases, arr, fills=fill_cells)
    if not layers:
        events.append(DebateEvent(type=EventType.INFO, agent="Lead", role=_ROLE_GENERATOR,
                                  text="no lead-active sections in this arrangement"))
    return layers, events


def _retrograde_fill(fill: LeadPhrase) -> LeadPhrase:
    """A distinct fill from a base one, DETERMINISTICALLY: reverse the run but KEEP the final
    landing note (so it still resolves into the head). Same pitches (legal), same sixteenth
    durations (still a valid taan fill), different contour. No LLM."""
    notes = fill.notes
    if len(notes) <= 2:
        return fill
    return fill.model_copy(update={"notes": list(reversed(notes[:-1])) + [notes[-1]]})


def _step_up_fill(fill: LeadPhrase, raga: str) -> LeadPhrase:
    """A distinct fill: shift every run note UP one scale-degree in the raga (legal BY
    CONSTRUCTION via `scale_step_up`), keeping the landing note. A higher variant; clears any
    meend target on the shifted notes so nothing illegal is left dangling. No LLM."""
    notes = fill.notes
    if len(notes) <= 2:
        return fill
    shifted: list[LeadNote] = []
    for n in notes[:-1]:
        if n.rest:
            shifted.append(n)
            continue
        sw, oct_delta = scale_step_up(n.swara, raga, 1)
        shifted.append(n.model_copy(update={"swara": sw, "oct": n.oct + oct_delta,
                                            "meend_swara": None, "meend_oct": None}))
    return fill.model_copy(update={"notes": shifted + [notes[-1]]})


def _fill_variants(base: LeadPhrase, count: int, raga: str) -> list[LeadPhrase]:
    """Up to `count` DISTINCT fills from ONE generated base, via deterministic in-raga transforms
    (the base, its retrograde, a scale-step-up). Consecutive mukhada cuts get contrasting taans
    WITHOUT extra LLM calls (Sujit, 2026-07-16: the LLM-written variants sounded alike anyway, and
    each cost a call). Every transform preserves the splice contract — sixteenths, length, and the
    landing that resolves into the head — so the variants stay verified by construction."""
    variants = [base, _retrograde_fill(base), _step_up_fill(base, raga)]
    return (variants * (count // len(variants) + 1))[:count]


def _generate_fills(span: SectionSpan, arr: Arrangement, memory: list[LeadMemo],
                    mukhada_cell: LeadPhrase, *, gen_fn: LeadFn,
                    events: list[DebateEvent]) -> list[LeadPhrase]:
    """Write the mukhada taan fills. ONE fill is GENERATED by the LLM (verified, bounded re-roll)
    right after the head is cached; the additional distinct fills are DERIVED deterministically
    (`_fill_variants`), so consecutive cuts contrast without extra LLM calls. It sees the head
    (memory `[mukhada]` + the `{mukhada_head}` block); the verifier holds it to the splice contract
    (sixteenths, exact length, resolves into the head)."""
    count = min(_FILL_VARIANTS, _fill_slot_count(arr))
    if count == 0:
        return []
    cycle_beats = arr.beats_per_bar
    head_memory = memory + [LeadMemo(span.section.kind.value, mukhada_cell, _MUKHADA)]
    head_first = next((("S" if n.bol == "chikari" else n.swara)
                       for n in mukhada_cell.notes if not n.rest), "S")
    fill_span = _fill_gen_span(span, cycle_beats, head_first)
    half = cycle_beats * _FILL_FRACTION
    base, tries, viol = _generate_verified_cell(
        fill_span, arr, head_memory, gen_fn=gen_fn,
        verify=lambda c: verify_fill(c, mukhada=mukhada_cell, window_beats=half, raga=arr.raga))
    if tries > 1:
        events.append(_gat_repair_event("taan fill", tries, viol))
    fills = _fill_variants(base, count, arr.raga)
    events.append(_fill_event(fills, half))
    return fills


def compose_lead(arr: Arrangement) -> tuple[list[Layer], list[DebateEvent]]:
    """Run the real (LLM-backed) lead generation for a chart — the gat composed as ONE object
    (`_LLMGat`), everything else per-section (`_LLMLead`)."""
    return generate_lead(arr, gen_fn=_LLMLead(arr), gat_fn=_LLMGat(arr))


def mukhada_cell_from_events(events: list[DebateEvent]) -> LeadPhrase | None:
    """The cached gat HEAD a lead run emitted, fished back out of its event stream.

    The seam for CROSS-VOICE seeding: the riff generator runs AFTER the lead and should
    reduce the head rhythmically (Sujit: the riff-only section should almost play the
    mukhada) — the events already travel to every caller, so the head rides them instead
    of changing `compose_lead`'s signature. None when no mukhada was generated."""
    for event in events:
        cell = event.data.get("mukhada_cell")
        if cell:
            return LeadPhrase.model_validate(cell)
    return None


# A canvas-aware per-section lead call, for the cooperative studio loop: (span, memory,
# canvas, move) -> the section's phrase, answering what is already on the canvas.
type StudioLeadFn = Callable[[SectionSpan, list[LeadMemo], SectionCanvas, CanvasMove], LeadPhrase]


def studio_lead_fn(arr: Arrangement) -> StudioLeadFn:
    """A CANVAS-AWARE lead generator for the studio loop.

    Where `compose_lead` fans out over the whole arrangement on its own, this returns a
    per-section call the cooperative loop drives: it generates ONE section's phrase given
    the shared canvas (the riff's line to answer) and the move (propose / respond / refine).
    The crew and the piece-level context are built once and reused across the run."""
    crew = _LeadCrew()
    context = _LeadContext(arr)

    def gen(span: SectionSpan, memory: list[LeadMemo], canvas: SectionCanvas,
            move: CanvasMove) -> LeadPhrase:
        beat("Lead", f"{span.section.kind.value} — {move.value}…")
        return crew.run(arr.raga, context.inputs_for(span, memory, canvas=canvas, move=move))

    return gen


# --------------------------------------------------------------------------- #
# The imperative edge — a single live confirmation: lead over a bare drone.    #
# --------------------------------------------------------------------------- #

def _lead_demo_arrangement() -> Arrangement:
    """A one-section chart (lead + drone) so the live confirmation is ONE LLM call.

    A harmonized TAAN in Darbari on purpose: a taan maps to the THIRD voicing, and
    Darbari is a seven-note raga, so the diatonic third is clean — the confirmation
    shows the lead voiced as sitar + lead guitar a raga-third apart. Built through the
    real composer contract (no LLM here).
    """
    from crew.contracts import ArrangementDraft, CompositionBrief, Section, SectionKind, build_arrangement
    draft = ArrangementDraft(
        raga="darbari", subgenre="thrash", tala="teentaal", bpm=180,
        motif=["S", "R", "g", "R", "g", "m", "P"],
        sections=[Section(kind=SectionKind.TAAN, bars=1, layers=["lead", "drone"],
                          foreground="lead", form_role="taan_long",
                          intent="a fast virtuosic taan climbing toward the taar")],
    )
    return build_arrangement(draft, CompositionBrief(mood="dark"))


def _run() -> None:
    arr = _lead_demo_arrangement()
    stream = EventStream()
    lead_layers, events = compose_lead(arr)
    for event in events:
        stream.emit(event)

    layers = [drone_layer(arr)] + lead_layers
    comp = assemble_composition(arr, layers)
    payload = comp.model_dump(exclude_none=True)
    violations = validate_composition(payload)
    print(f"lead+drone composition ({len(layers)} layers): {len(violations)} grammar violation(s)")

    if shutil.which("fluidsynth") and _SOUNDFONT.exists():
        wav = render_composition(comp, out_dir=_OUT_DIR, name="lead_taan", soundfont=_SOUNDFONT)
        print(f"-> rendered {wav.relative_to(_ROOT)}")
    else:
        print("-> render skipped (fluidsynth or soundfont not found)")


def main(argv: list[str]) -> int:
    load_env()  # entry point loads .env
    # Trace by default — every live run is captured for the portal (RMA_TRACE=0 opts out).
    from contextlib import nullcontext

    from crew.tracing import traced, tracing_enabled
    ctx = traced("lead-demo") if tracing_enabled() else nullcontext()
    with ctx:
        _run()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
