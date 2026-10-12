"""
The Riff generator (step 4, generator #2) — the metal rhythm guitar.

Where the Lead free-sequences a melodic phrase, the Riff LOCKS to the tala. It asks
the LLM for ONE cycle of riff (a tight, loopable figure) and the code repeats that
cycle across the section's bars — so every bar re-lands on the sam — and PUNCHES the
notes that fall on the accent grid's sam/tali beats, which is how the riff interlocks
with the kick (DESIGN.md: "the tala accent grid so riff and kick interlock").

Same split as the Lead: the LLM supplies the music (which swaras, the rhythm, the
subgenre feel); code owns the checkable — it lays the cycle on the beat grid in the
downtuned rhythm register, accents the tala's stressed matras, and the legality
guardrail refuses any out-of-raga swara for one bounded retry. On top of legality,
every cycle passes the TEXTURE verifier (`crew/riff_texture.py`): the section's mode
(drive / pads / stabs, decided by code from its gat role) sets budgets — chug ground,
weight on the sam, real silence, the bright-colour ration — and a miss drives a bounded
feedback re-roll at the LLM boundary (`verified_riff`), so a riff is idiomatic METAL
before it is clever.

The Bass is NOT here — it is a DETERMINISTIC shadow of the riff (`generators.bass_layer`),
run right after this generator. See DESIGN.md, "The low end".

Entry point (ONE live LLM call — riff + bass + drone):
  uv run python -m crew.riff
"""

from __future__ import annotations

import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import yaml
from crewai import Agent, Crew, Process, Task
from pydantic import ValidationError

from crew.config import (
    AGENT_RETRY_LIMIT,
    GENERATOR_MAX_ITER,
    GENERATOR_RETRIES,
    generator_llm,
    load_env,
    structured_output,
)
from crew.contracts import (
    RHYTHM_FLOOR,
    Arrangement,
    CanvasMove,
    DebateEvent,
    EventStream,
    EventType,
    Layer,
    LeadNote,
    LeadPhrase,
    Note,
    RiffNote,
    RiffPattern,
    SectionCanvas,
    motif_illegal_in_raga,
)
from crew.generators import (
    VOICES,
    SectionSpan,
    assemble_composition,
    bass_layer,
    drone_layer,
    render_composition,
    section_spans,
)
from crew.live import beat, flags
from crew.realized import kept_riffs, riff_realized_event
from crew.riff_family import develop_section
from crew.riff_playability import playability_check, render_playability
from crew.riff_texture import (
    MODE_BRIEFS,
    riff_mode_for,
    texture_measures,
    texture_notes,
    verified_riff,
)
from crew.anchor import (
    RIFF_EVENT_KEY,
    hook_seed_for_riff,
    main_riff_slot,
    render_song_seed,
    riff_from_events,
    slot_of,
)
from crew.riff_from_mukhada import HeadRiff, head_riff, render_head_riff
from crew.riff_statements import develop_riff_first, develop_statements
from crew.riff_voicing import home_root, render_power_roots, voice_riff
from crew.lead import render_direction_rule
from crew.user_request import render_request
from raga import (
    NYAS,
    RAGAS,
    ascent_step,
    direction_violations,
    directional_varjya,
    half_step_pairs,
    semitone,
    validate_composition,
)
from subgenres import SUBGENRES
from talas import TALAS

_RHYTHM_ROLE: Final = "rhythm"             # the layer role this generator fills
_ROLE_GENERATOR: Final = "generator"
_MUKHADA_ROLE: Final = "mukhada"           # the form_role whose riff and sitar head share one idea
_SEED_KEY: Final = RIFF_EVENT_KEY           # event-data key carrying the head section's riff
_ACCENT_KINDS: Final = ("sam", "tali")     # the matras a riff should punch
_RIFF_ACCENT_BOOST: Final[float] = 1.12    # velocity multiplier on an accented onset

_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
_SOUNDFONT: Final[Path] = _ROOT / "soundfonts" / "GeneralUser-GS.sf2"
_OUT_DIR: Final[Path] = _ROOT / "out"

_OUTPUT_SCHEMA: Final = """{
  "reasoning": "the riff's HOOK — the ONE short cell it states and RESTATES (A A' A B, not a new figure each time) — which raga swaras / part of the motif it is built on, and how it lands the sam",
  "notes": [
    {"swara": "<raga swara: a root>", "oct": <octave>, "dur": <beats>},
    {"swara": "<raga swara>", "oct": <octave>, "dur": <beats>, "technique": "<optional, from the list below>"},
    {"rest": true, "swara": "S", "dur": <beats>}
  ]
}
(Format only — the riff's notes, rhythm and techniques are your choice.)
"reasoning" comes FIRST. This is ONE tala cycle; the arrangement repeats AND develops it across the
section (A, A', a stripped or heaviest variant), so write one strong, COMPLETE cycle. "oct" is your
octave (0 = home/low; -1 lower). "vel" is optional. Durations are in beats (0.25 = 16th, 0.5 = 8th,
1 = quarter) and should sum to one full cycle, COUNTING rests.
"chord" (optional) — LEAVE IT EMPTY for weight: code voices every bare stroke as a power chord
inside the raga (fifth, else the inverted fourth, else the octave — by the stroke's role). Write a
chord only for a deliberate COLOUR: extra raga swaras sounded WITH the root, each a LEGAL swara (a
second above the root sounds as an ADD9, a third as a TENTH; a tritone or semitone has no clean
seat under distortion and becomes octave weight). A note with a slide, bend or legato stays single.
"technique" (optional) = palm_mute (a tight
chug — the core texture), slide (short fret-to-fret), long_slide (a wide slow position shift — a
signature sitar-fusion move), pick_scrape (the pick dragged down the strings INTO a downbeat
chord), bend, hammer_on, pull_off; omit for a plain picked note. "rest" (optional) = a SILENT beat
for SPACE — set rest:true with any swara (ignored); include at least one per cycle so the tabla
and gat breathe."""


# --------------------------------------------------------------------------- #
# Placement: one cycle -> repeated, register-seated, accent-locked notes. Pure. #
# --------------------------------------------------------------------------- #

# The widest riff bend, in semitones (a minor third — still an idiomatic metal bend).
# When the raga's next enterable swara sits farther than this, the note plays PLAIN:
# a partial bend would hold an out-of-raga apex, and a wider one reads as a slide.
_BEND_MAX_ST: Final = 3


def _bend_depth(swara: str, raga: str) -> int | None:
    """Semitones a bend on `swara` rises IN THIS RAGA — up to the next swara the raga
    lets you enter from below (`ascent_step`: legal by set AND direction), or None when
    that seat is too far to bend (the note plays plain). The old fixed 2-semitone bend
    HELD its apex on whatever pitch lay a whole tone up — out of raga wherever the
    ladder steps differently (Sujit's ear, 2026-07-16: bends pausing on varjya notes)."""
    sw, oct_d = ascent_step(swara, raga)
    depth = semitone(sw) + 12 * oct_d - semitone(swara)
    return depth if depth <= _BEND_MAX_ST else None


def _sequence_cycle(pattern: list[RiffNote], cycle_beats: float, register: int,
                    raga: str | None = None) -> list[Note]:
    """Lay one cycle's notes end-to-end from beat 0, seat them in `register`, and make
    them cover EXACTLY one cycle so the riff loops seamlessly.

    A pattern that overruns is clipped at the cycle edge; one that falls SHORT has its
    last note extended to the edge, so there is no silent gap at the downbeat where
    the loop repeats (a gap would limp every bar). The LLM is asked to fill the cycle
    exactly (see the prompt); this is the guarantee behind that ask.

    Each note's ABSOLUTE octave is clamped at `RHYTHM_FLOOR`: the register default keeps
    the layer out of sub-bass, but the LLM's local `oct: -1` could still push a root an
    octave below it (~D1, 37 Hz — heard as bass-register mud on the first live gat render).
    Like a guitarist out of frets below the low string, the note sounds AT the floor.

    With `raga` given, each BEND is seated in the raga: its depth is stamped as
    `bend_st` (the interval to the next enterable swara, `_bend_depth`) so the apex is
    a raga tone, or the bend is stripped (a plain note) when no seat is in reach.
    """
    placed: list[Note] = []
    t = 0.0
    last_was_rest = False
    for rn in pattern:
        if t >= cycle_beats:
            break
        if rn.rest:                                  # a silent beat — advance time, sound nothing
            last_was_rest = True
        else:
            dur = min(rn.dur, cycle_beats - t)
            technique, bend_st = rn.technique, None
            if technique == "bend" and raga is not None:
                bend_st = _bend_depth(rn.swara, raga)
                if bend_st is None:
                    technique = None                 # no reachable seat — the note plays plain
            placed.append(Note(swara=rn.swara, oct=max(register + rn.oct, RHYTHM_FLOOR),
                               start=round(t, 4), dur=round(dur, 4), vel=rn.vel,
                               chord=rn.chord, technique=technique, bend_st=bend_st))
            last_was_rest = False
        t += rn.dur
    # Fill a SHORT cycle so the loop has no accidental gap — UNLESS the pattern ends on a rest,
    # which is an INTENTIONAL silence into the sam (a rest-stab); then the gap is kept.
    if placed and not last_was_rest:
        last = placed[-1]
        if last.start + last.dur < cycle_beats:
            placed[-1] = last.model_copy(update={"dur": round(cycle_beats - last.start, 4)})
    return placed


def place_cycles(cycles: list[list[RiffNote]], *, start: float, cycle_beats: float,
                  register: int, accent_beats: set[float],
                  raga: str | None = None) -> list[Note]:
    """Place a per-bar SEQUENCE of cycles (one RiffNote list per bar), sequencing each onto its
    bar from `start` and locking it to the accent grid. Notes whose onset (within the cycle)
    lands on an accented matra (sam/tali) are punched up — this is how CODE locks the riff to
    the tala so riff and kick interlock, rather than trusting the LLM to have counted beats.
    The primitive behind BOTH the literal repeat (`place_riff`) and the developed riff family
    (`rhythm_layer_from` -> `develop_section`). Pure."""
    notes: list[Note] = []
    for bar, cycle_notes in enumerate(cycles):
        cycle = _sequence_cycle(cycle_notes, cycle_beats, register, raga)
        offset = start + bar * cycle_beats
        for n in cycle:
            vel = min(127, round(n.vel * _RIFF_ACCENT_BOOST)) if n.start in accent_beats else n.vel
            notes.append(n.model_copy(update={"start": round(n.start + offset, 4), "vel": vel}))
    return notes


def place_riff(pattern: list[RiffNote], *, start: float, bars: int, cycle_beats: float,
               register: int, accent_beats: set[float], raga: str | None = None) -> list[Note]:
    """Repeat ONE cycle across `bars` from `start`, locking each bar to the sam — the LITERAL
    (no-variation) placement. `rhythm_layer_from` uses the developed placement (the riff family)
    instead; this stays as the primitive the accent/loop tests target. Pure."""
    return place_cycles([pattern] * bars, start=start, cycle_beats=cycle_beats,
                         register=register, accent_beats=accent_beats, raga=raga)


def _accent_beats(arr: Arrangement) -> set[float]:
    """The within-cycle beats the riff should punch — the sam and the clapped tali."""
    return {a.beat for a in arr.accent_grid if a.kind in _ACCENT_KINDS}


# --------------------------------------------------------------------------- #
# Facts -> prompt text. Pure.                                                  #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class RiffMemo:
    """One already-realized riff SLOT — the library the NEXT distinct riff is written
    against, so a `chorus` riff can deliberately CONTRAST the `main` riff (different
    shape, power chords) instead of drifting into an unrelated figure. Holds the slot
    label and the pattern as the model emitted it (LOCAL octaves)."""
    slot: str
    pattern: RiffPattern


def slot_for(section) -> str:
    """The riff SLOT a section plays — its explicit `riff_slot`, else its kind. Sections
    that resolve to the same slot REPLAY one riff (recurrence); this is where the identity
    that makes the main riff a hook lives, in code, not in the LLM."""
    return slot_of(section)


def _riff_token(note: RiffNote) -> str:
    """One realized riff note — swara with its LOCAL octave and any power chord (`+X`)."""
    tok = note.swara if note.oct == 0 else f"{note.swara}({note.oct:+d})"
    return tok + "+" + "+".join(note.chord) if note.chord else tok


def _render_previous(memory: list[RiffMemo]) -> str:
    """The riff library realized so far — the other slots this new riff should contrast."""
    if not memory:
        return "  (this is the FIRST riff — establish the main riff)"
    return "\n".join(f"  {memo.slot}: {' '.join(_riff_token(n) for n in memo.pattern.notes)}"
                     for memo in memory)


def _lead_line_token(note: LeadNote) -> str:
    """One LeadNote as the RIFF sees it on the shared canvas — swara with its local octave —
    enough for the riff to lock a groove under the lead's phrase."""
    return note.swara if note.oct == 0 else f"{note.swara}({note.oct:+d})"


def _render_mukhada_line(mukhada: LeadPhrase | None, section, anchor: str = "gat_first",
                         accents: str = "") -> str:
    """What the riff is told about the gat HEAD, for a mukhada-role section. Pure.

    The ANCHOR decides the direction. `riff_first`: the riff is composed BEFORE the gat and
    is its source — the sitar's head will quote the swaras it sounds on the sam and tali, so
    those roots must be deliberate, singable raga swaras. `gat_first` (cross-voice seeding —
    Sujit: the riff should almost PLAY the mukhada, with low chugs): the head arrives
    swara-by-swara with durations, and the riff is its RHYTHMIC REDUCTION. Sections outside
    the head get a benign line, so one prompt serves every section."""
    if section.form_role != _MUKHADA_ROLE:
        return "  (this section is not the gat head — groove per your section role above)"
    if anchor == "riff_first":
        return (f"  riff_first — YOU are the source. This is the piece's seed: the sitar's gat "
                f"head is composed AFTER you and QUOTES the swaras you sound on the accented "
                f"beats ({accents}). Make those roots deliberate, strong raga swaras a melody can "
                f"sing (the sam on Sa or a structurally strong swara, never a passing colour), "
                f"and chug between them. A riff the head can quote is a riff people remember.")
    if mukhada is None:
        return "  (this section is not the gat head — groove per your section role above)"
    toks = " ".join("-" if n.rest else f"{n.swara}({n.dur:g})" for n in mukhada.notes)
    return (f"  the sitar's mukhada, ONE avartan, swara(beats): {toks}\n"
            f"  YOUR riff here is that head's RHYTHMIC REDUCTION — the band should hear the "
            f"mukhada IN the riff: quote its accented swaras (above all what lands the sam and "
            f"tali) as your low-string roots, and fill between them with palm-mute chugs on Sa. "
            f"Almost play the head; keep the metal weight.")


def _render_canvas_for_riff(canvas: SectionCanvas | None, move: CanvasMove) -> str:
    """What the riff SEES on this section's shared canvas, rendered for its MOVE. Pure.

    On RESPOND the riff locks a groove under the lead (support the phrase, don't chase the
    melody); on REFINE it tightens its riff against the finished ensemble. When it OPENS the
    section (PROPOSE) or there is no canvas (the solo / non-studio path), it simply
    establishes the main riff — so one prompt serves both the studio and the standalone
    generator."""
    if canvas is None or move is CanvasMove.PROPOSE:
        return "  (you OPEN this section — the canvas is empty; lay down the main groove)"
    lines: list[str] = []
    lead = canvas.lead
    if lead is not None:
        lines.append(f"  the Lead is playing: {' '.join(_lead_line_token(n) for n in lead.notes)}")
    if move is CanvasMove.RESPOND:
        lines.append("  LOCK a groove under the lead — support its phrase and hit the accents it"
                     " leaves open; stay root-driven, do not chase its melody."
                     if lead is not None else
                     "  (no lead on the canvas yet — establish the main riff.)")
    else:  # REFINE
        if canvas.riff is not None:
            lines.append(f"  your current riff: {' '.join(_riff_token(n) for n in canvas.riff.notes)}")
        lines.append("  REFINE your riff to lock tighter with the ensemble above — keep the hook,"
                     " tighten the interplay.")
    return "\n".join(lines)


def render_half_steps(raga: str) -> str:
    """The raga's half-step neighbours as riff vocabulary: the one-fret power-chord moves a
    metal riff grinds on (song A's E5-F5 / C5-B5 in Bhairav). Derived from the allowed swaras
    (`raga.half_step_pairs`); a raga with none is told so, so it reaches for wider moves. Pure."""
    pairs = half_step_pairs(raga)
    if not pairs:
        return ("  (this raga has NO half-step neighbours — its weight comes from wider moves; "
                "shuffle between adjacent roots a whole step or more apart)")
    shapes = ", ".join(f"{low}–{high}" for low, high in pairs)
    return (f"  {shapes} — move the power-chord shape ONE FRET between a pair and back (a fresh "
            f"pick attack each time, never a bend): the grind metal riffs are built on. A "
            f"komal swara falling to its neighbour is also the raga's own resolution. The "
            f"direction rule above still applies to the roots.")


def render_home_root(raga: str) -> str:
    """The riff's HOME root, from the raga's resting notes (`riff_voicing.home_root`). Sa for
    every raga whose Sa is a core rest; otherwise the prompt says WHY not Sa, so the model does
    not drift back to the Western habit of chugging on the tonic. Pure."""
    home = home_root(raga)
    if home == "S":
        return "S (Sa)"
    core = " and ".join(NYAS[raga]["core"])
    return (f"{home} — this raga's Sa is deliberately WEAK (its resting notes are {core}); circle "
            f"{home}, and let Sa arrive only in passing or at the very end")


def _render_repair(feedback: list[str] | None) -> str:
    """The hard verifier's violations, rendered for a targeted RE-ROLL. On a first
    attempt (no feedback) it is a benign line, so one prompt serves both. Code never
    edits the notes — the model recomposes the cycle to fix exactly what failed."""
    if not feedback:
        return "  (first take — nothing to repair)"
    issues = "\n".join(f"    - {v}" for v in feedback)
    return ("  your previous cycle FAILED the hard checks below — recompose it to fix "
            "exactly these:\n" + issues)


class _RiffContext:
    """Assembles a riff turn's prompt inputs. Piece-level facts render once; the
    per-section fields and the realized-so-far MEMORY change per turn. Pure — no I/O.
    `mukhada` (optional) is the sitar's cached gat head — in a `gat_first` piece a
    mukhada-role section's riff is prompted as its rhythmic reduction; in a `riff_first`
    piece it is told it is the source the head will quote (`arr.anchor` decides)."""

    def __init__(self, arr: Arrangement, mukhada: LeadPhrase | None = None) -> None:
        self._arr = arr
        self._mukhada = mukhada
        self._anchor = arr.anchor
        self._head_riff = head_riff(arr, mukhada)   # the head on guitar — starting material
        s = SUBGENRES[arr.subgenre]
        r = RAGAS[arr.raga]
        accents = ", ".join(f"beat {a.beat:g} ({a.kind})"
                            for a in arr.accent_grid if a.kind in _ACCENT_KINDS)
        self._accent_beats = accents
        self._static: dict[str, Any] = {
            "raga": r["display"],
            "allowed": " ".join(r["allowed"]),
            "direction_rule": render_direction_rule(directional_varjya(arr.raga))
                              or "(every swara moves freely both ways)",
            "half_steps": render_half_steps(arr.raga),
            "home_root": render_home_root(arr.raga),
            "power_roots": render_power_roots(arr.raga),
            "pakad": " | ".join(" ".join(p) for p in r["pakad"]),
            "chalan": " | ".join(" ".join(p) for p in r["chalan"]),
            "motif": " ".join(arr.motif),
            "subgenre": s["display"],
            "subgenre_feel": s["feel"],
            "subdivision": s["subdivision"],
            "groove_brief": s["groove_brief"],
            "techniques": ", ".join(s["techniques"]),
            "bpm": arr.bpm,
            "tala": TALAS[arr.tala]["display"],
            "cycle_beats": f"{arr.beats_per_bar:g}",
            "accents": accents,
            "user_request": render_request(arr.request),
            "song_seed": render_song_seed(arr),
            "playability": render_playability(arr),
            "output_schema": _OUTPUT_SCHEMA,
        }

    def inputs_for(self, span: SectionSpan, memory: list[RiffMemo], *,
                   canvas: SectionCanvas | None = None,
                   move: CanvasMove = CanvasMove.PROPOSE,
                   feedback: list[str] | None = None) -> dict[str, Any]:
        section = span.section
        mode = riff_mode_for(section)
        return {
            **self._static,
            "section_kind": section.kind.value,
            "form_role": section.form_role or "free (no gat role set)",
            "riff_slot": slot_for(section),
            "section_intent": section.intent or "(none given — use your judgment for this kind)",
            "section_transition": section.transition or "(none given)",
            "bars": section.bars,
            "riff_mode": mode.value,
            "mode_brief": MODE_BRIEFS[mode],
            "previous": _render_previous(memory),
            "mukhada_line": _render_mukhada_line(self._mukhada, section, self._anchor,
                                                 self._accent_beats),
            "mukhada_riff": render_head_riff(self._head_riff, self._arr, slot_for(section)),
            "move": move.value,
            "canvas": _render_canvas_for_riff(canvas, move),
            "repair": _render_repair(feedback),
        }


# --------------------------------------------------------------------------- #
# Boundary parsing + the legality guardrail. Imperative-ish.                   #
# --------------------------------------------------------------------------- #

def _pattern_from_output(output: Any) -> RiffPattern | None:
    parsed = getattr(output, "pydantic", None)
    if isinstance(parsed, RiffPattern):
        return parsed
    raw = getattr(output, "raw", None)
    try:
        return RiffPattern.model_validate_json(raw) if raw else None
    except ValidationError:
        return None


def riff_grammar_error(pattern: RiffPattern, raga: str) -> str | None:
    """The riff's raga-grammar fault as a retry message, or None. Every SOUNDING pitch faces the
    grammar — the root AND each chord tone stacked on it — and the ROOT line also faces the
    direction rule (a one-directional swara, Bageshree's descent-only P, entered from its own
    side); chord tones stack in one instant, not a melodic entry. Rests are exempt. Pure;
    shared by the riff guardrail and the Composer's seed guardrail."""
    sounded = [n for n in pattern.notes if not n.rest]
    swaras = [n.swara for n in sounded] + [c for n in sounded for c in (n.chord or [])]
    illegal = motif_illegal_in_raga(swaras, raga)
    if illegal:
        allowed = " ".join(RAGAS[raga]["allowed"])
        return (f"swaras {sorted(set(illegal))} are illegal in raga {raga}. "
                f"Use only these swaras (roots AND chord tones): {allowed}. Fix and resend.")
    direction = direction_violations([(n.swara, n.oct) for n in sounded], raga)
    if direction:
        return "; ".join(dict.fromkeys(direction)) + ". Fix the approach and resend."
    return None


def _riff_guardrail(raga: str):
    """The Task guardrail for a given raga: every riff swara must be legal (`riff_grammar_error`).
    Returns (True, RiffPattern) or (False, error). The return annotation is set as a real
    object below because `from __future__ import annotations` would stringify it."""
    def guard(output: Any):
        pattern = _pattern_from_output(output)
        if pattern is None:
            return (False, "Return a single valid RiffPattern JSON object and nothing else.")
        error = riff_grammar_error(pattern, raga)
        return (False, error) if error else (True, pattern)

    guard.__annotations__["return"] = tuple[bool, Any]
    return guard


class _RiffCrew:
    """Runs ONE section's riff generation as an isolated single-agent crew. `agent_key` names
    the agents.yaml persona — "riff" on the legacy path, "composer" when the single Composer
    owns the music (the same musician who wrote the seed develops it)."""

    def __init__(self, agent_key: str = "riff") -> None:
        config_dir = Path(__file__).parent / "config"
        self._agent_config = yaml.safe_load((config_dir / "agents.yaml").read_text())[agent_key]
        self._task_config = yaml.safe_load((config_dir / "tasks.yaml").read_text())["generate_riff"]

    def run(self, raga: str, inputs: dict[str, Any]) -> RiffPattern:
        agent = Agent(config=self._agent_config, llm=generator_llm(),
                      allow_delegation=False, max_iter=GENERATOR_MAX_ITER,
                      max_retry_limit=AGENT_RETRY_LIMIT, verbose=False)
        task = Task(config=self._task_config, agent=agent, **structured_output(RiffPattern),
                    guardrail=_riff_guardrail(raga), guardrail_max_retries=GENERATOR_RETRIES)
        crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)
        pattern = _pattern_from_output(crew.kickoff(inputs=inputs))
        if pattern is None:
            raise ValueError("riff generator returned no parseable RiffPattern")
        return pattern


type RiffFn = Callable[[SectionSpan, Arrangement, list[RiffMemo]], RiffPattern]


class _LLMRiff:
    """The real (LLM-backed) `gen_fn` — holds the crew and the precomputed context.

    Every cycle is generated through `voiced_and_verified`: voiced as power chords, then the
    HARD verifier (fills the cycle, physically playable) drives a bounded feedback re-roll at
    THIS boundary, so the pure loops above stay about recurrence/placement and injected test
    fakes bypass verification entirely."""

    def __init__(self, arr: Arrangement, mukhada: LeadPhrase | None = None,
                 agent_key: str = "riff") -> None:
        self._crew = _RiffCrew(agent_key)
        self._context = _RiffContext(arr, mukhada)

    def __call__(self, span: SectionSpan, arr: Arrangement, memory: list[RiffMemo]) -> RiffPattern:
        slot = span.section.riff_slot or span.section.kind.value
        mode = riff_mode_for(span.section).value

        def gen(fb: list[str] | None) -> RiffPattern:
            if fb is None:
                beat("Riff", f"laying down the '{slot}' riff ({mode})…")
            else:                                     # SHOW WHY the take is being redone
                beat("Riff", f"re-rolling the '{slot}' riff — flagged: {flags(fb)}",
                     data={"violations": fb, "slot": slot, "mode": mode})
            return self._crew.run(arr.raga, self._context.inputs_for(span, memory, feedback=fb))

        return voiced_and_verified(gen, span.section, arr)


def voiced_and_verified(gen: Callable[[list[str] | None], RiffPattern], section,
                        arr: Arrangement) -> RiffPattern:
    """The ONE generation boundary both composition roots share: each take is VOICED (every
    bare stroke becomes a power chord inside the raga — `riff_voicing`) before it is verified,
    so the hard checks and the playability budget see the chords that will actually sound, and
    the finished cycle is voiced again so the texture guarantees' gap-chugs carry weight too.
    Voicing follows each stroke's FUNCTION, so the tala's accent beats are passed in."""
    accents = frozenset(_accent_beats(arr))         # an accented stroke may take a fuller dyad

    def voiced(feedback: list[str] | None) -> RiffPattern:
        return voice_riff(gen(feedback), arr.raga, accents)

    pattern = verified_riff(voiced, section, arr.beats_per_bar, extra_check=playability_check(arr))
    return voice_riff(pattern, arr.raga, accents)


# --------------------------------------------------------------------------- #
# The generator loop — pure control flow, LLM injected via `gen_fn`.           #
# --------------------------------------------------------------------------- #

def _riff_event(span: SectionSpan, pattern: RiffPattern, slot: str,
                cycle_beats: float) -> DebateEvent:
    """A new riff's proposal. It carries the cycle's TEXTURE NOTES and pitch MEASURES — the
    advisory half of the verifier, reported for the judges and the trace, never enforced."""
    mode = riff_mode_for(span.section)
    return DebateEvent(
        type=EventType.PROPOSE, agent="Riff", role=_ROLE_GENERATOR,
        text=f"{slot} riff: {span.section.bars}-bar, {len(pattern.notes)} notes/cycle "
             f"({mode.value} mode)",
        data={"slot": slot, "mode": mode.value,
              "reasoning": pattern.reasoning,
              "swaras": [n.swara for n in pattern.notes],
              "texture_notes": texture_notes(pattern, mode=mode, cycle_beats=cycle_beats),
              "texture_measures": texture_measures(pattern)})


def _reprise_event(span: SectionSpan, slot: str) -> DebateEvent:
    """A section replays an already-written slot — the hook returns. A light INFO beat
    (not a fresh PROPOSE) so the timeline shows the main riff coming back."""
    return DebateEvent(
        type=EventType.INFO, agent="Riff", role=_ROLE_GENERATOR,
        text=f"reprise: the {slot} riff returns ({span.section.kind.value}, "
             f"{span.section.bars} bar{'s' if span.section.bars != 1 else ''})",
        data={"slot": slot, "reprise": True})


def rhythm_layer_from(patterns: dict[int, RiffPattern], arr: Arrangement,
                      head_slots: frozenset[str] = frozenset()) -> Layer | None:
    """Assemble the single rhythm layer from already-generated per-section riffs (section
    index -> the base cycle that plays there).

    Each section's base cycle is DEVELOPED across its bars into the riff family
    (`develop_section`) — so a recurring riff varies (chugged A', thinned under a taan, doubled
    to land the ending) instead of looping unchanged — then placed and accent-locked. A chart
    with no declared gat form is placed literally (variant "base"). A slot in `head_slots` plays
    the HEAD RIFF and develops by statement instead (`develop_statements`: faithful first, then
    heavier, making space under the sitar), its count threaded across its sections. A section
    with no riff is skipped. Returns None when nothing plays. Pure — so the studio reuses it."""
    accents = _accent_beats(arr)
    spans = section_spans(arr)
    playing = [s.index for s in spans if patterns.get(s.index) is not None]
    final_rhythm = playing[-1] if playing else None      # the last section that actually plays a riff
    register = arr.registers[_RHYTHM_ROLE]
    statements: dict[str, int] = {}                     # head slot -> guitar statements so far
    anchor_slot = _riff_first_slot(arr)
    heads_heard = 0                                     # riff_first: mukhada sections so far
    notes: list[Note] = []
    for span in spans:
        pattern = patterns.get(span.index)
        if pattern is None:
            continue
        slot = slot_for(span.section)
        final = span.index == final_rhythm
        if slot in head_slots:
            cycles, statements[slot] = develop_statements(
                pattern.notes, span.section, is_final_rhythm=final,
                first_statement=statements.get(slot, 0), raga=arr.raga,
                accents=frozenset(accents))
        elif slot == anchor_slot:
            cycles = develop_riff_first(pattern.notes, span.section, is_final_rhythm=final,
                                        reprise=heads_heard > 0, raga=arr.raga,
                                        accents=frozenset(accents))
            heads_heard += span.section.form_role == "mukhada"
        else:
            cycles = develop_section(pattern.notes, span.section, is_final_rhythm=final)
        notes.extend(place_cycles(cycles, start=span.start, cycle_beats=arr.beats_per_bar,
                                   register=register, accent_beats=accents, raga=arr.raga))
    if not notes:
        return None
    voice = VOICES[_RHYTHM_ROLE]
    return Layer(role=_RHYTHM_ROLE, instrument=voice.instrument, program=voice.program,
                 channel=voice.channel, pan=voice.pan, notes=notes)


def _riff_first_slot(arr: Arrangement) -> str | None:
    """The slot whose riff the head quotes in a riff_first piece — the first mukhada's — or None
    (gat_first, a song form, or no mukhada that plays a riff)."""
    if arr.anchor != "riff_first":
        return None
    head = next((s for s in arr.sections if s.form_role == "mukhada" and "rhythm" in s.layers),
                None)
    return slot_for(head) if head is not None else None


def _head_take(span: SectionSpan, arr: Arrangement, riff: HeadRiff) -> RiffPattern:
    """The head riff at the shared generation boundary — voiced and texture-finished like any
    take (it already passed the hard checks, so no re-roll can fire)."""
    return voiced_and_verified(lambda feedback: riff.pattern, span.section, arr)


def _head_event(span: SectionSpan, pattern: RiffPattern, slot: str,
                cycle_beats: float) -> DebateEvent:
    event = _riff_event(span, pattern, slot, cycle_beats)
    event.text = f"{slot} riff: derived from the gat head — " + event.text.split(": ", 1)[1]
    event.data["from_head"] = True
    return event


def generate_riff(arr: Arrangement, *, gen_fn: RiffFn,
                  keep: dict[str, RiffPattern] | None = None, head: LeadPhrase | None = None,
                  rework: frozenset[str] = frozenset()) -> tuple[Layer | None, list[DebateEvent]]:
    """Fill the rhythm layer across the arrangement's rhythm-active sections.

    A riff is written ONCE PER SLOT and REUSED wherever that slot recurs — so the main
    riff literally returns as a hook, distinct slots stay distinct, and `gen_fn` fires
    only for a new slot (fewer LLM calls). A recurring section emits a light reprise event
    rather than a fresh proposal. The per-section riffs are then placed/accent-locked into
    one layer via `rhythm_layer_from`. Returns (None, events) when no section uses the
    rhythm guitar. `gen_fn` is injected so this loop is tested with no LLM.

    `keep` (a REVISE): slots already settled — they play as before and count as memory, so
    `gen_fn` fires only for the slots the plan's sections play. The pass always ends with a
    `riff_realized_event`, the library a later revise keeps.

    `head` (a gat_first piece's realised mukhada): the slots that inherit it (`derived_slots`)
    play the HEAD RIFF derived by code — no model call — and develop by statement. A slot in
    `rework` (a revise targeting it), or a head riff that fails the hard checks, goes to `gen_fn`
    instead, whose prompt shows the head riff as its starting material.
    """
    derived = head_riff(arr, head)
    head_slots = derived.slots if derived is not None else frozenset()
    events: list[DebateEvent] = []
    patterns: dict[int, RiffPattern] = {}
    library: dict[str, RiffPattern] = dict(keep or {})   # slot -> its one-cycle riff
    order: list[str] = []                           # slots in first-seen order (the memory)
    seeded = False                                  # has the mukhada's riff been published yet?
    for span in section_spans(arr):
        if _RHYTHM_ROLE not in span.section.layers:
            continue
        slot = slot_for(span.section)
        if slot in library:                         # the hook returns — reuse, don't regenerate
            pattern = library[slot]
            if slot not in order:                   # a slot a revise kept: memory, not news
                order.append(slot)
            else:
                events.append(_reprise_event(span, slot))
        elif (derived is not None and derived.playable and slot in head_slots
              and slot not in rework):              # the guitar takes up the sitar's head
            pattern = _head_take(span, arr, derived)
            library[slot] = pattern
            order.append(slot)
            events.append(_head_event(span, pattern, slot, arr.beats_per_bar))
        else:                                        # a new slot — write a riff that contrasts the rest
            memory = [RiffMemo(s, library[s]) for s in order]
            pattern = gen_fn(span, arr, memory)
            library[slot] = pattern
            order.append(slot)
            events.append(_riff_event(span, pattern, slot, arr.beats_per_bar))
        if span.section.form_role == _MUKHADA_ROLE and not seeded:
            # The head's riff rides the event stream (see `mukhada_riff_from_events`), so a
            # `riff_first` gat — composed AFTER this — can quote it, with no signature churn.
            events[-1].data[_SEED_KEY] = pattern.model_dump(exclude_none=True)
            seeded = True
        patterns[span.index] = pattern

    layer = rhythm_layer_from(patterns, arr, head_slots)
    if layer is None:
        events.append(DebateEvent(type=EventType.INFO, agent="Riff", role=_ROLE_GENERATOR,
                                  text="no rhythm-active sections in this arrangement"))
    events.append(riff_realized_event(library))
    return layer, events


def revise_riff(arr: Arrangement, library: dict[str, RiffPattern], targets: list[int], *,
                agent_key: str = "riff") -> tuple[Layer | None, list[DebateEvent]]:
    """The TARGETED riff revise: re-compose only the slots the targeted sections play, by the same
    persona that wrote them (`composer` on the single-Composer path); every other slot replays.
    A targeted main slot is genuinely re-written — the plan has authority over the seed riff."""
    target_slots = {slot_for(span.section) for span in section_spans(arr) if span.index in targets}
    keep = kept_riffs(library, target_slots)
    head = hook_seed_for_riff(arr)
    return generate_riff(arr, gen_fn=_LLMRiff(arr, head, agent_key), keep=keep, head=head,
                         rework=frozenset(target_slots))


def mukhada_riff_from_events(events: list[DebateEvent]) -> RiffPattern | None:
    """The riff the mukhada section plays, fished back out of a riff run's event stream.

    The `riff_first` seam, the mirror of `lead.mukhada_cell_from_events`: the riff runs FIRST
    and the gat's head must quote its accented roots. None when no mukhada section plays a riff."""
    return riff_from_events(events)


def compose_riff(arr: Arrangement,
                 mukhada: LeadPhrase | None = None) -> tuple[Layer | None, list[DebateEvent]]:
    """Run the real (LLM-backed) riff generation for a chart. `mukhada` (optional) is the
    sitar's cached gat head of a `gat_first` piece — when given, the slots that inherit it play
    the HEAD RIFF derived from it by code (`crew/riff_from_mukhada.py`, no model call), so the
    band hears the head IN the riff, and every other slot's prompt shows it as material. A
    `riff_first` piece runs this BEFORE the lead (no head yet), and its mukhada riff is
    published for the gat to quote (`mukhada_riff_from_events`). With no `mukhada` given, the
    chart's own seed is used (`hook_seed_for_riff`) — so a REVISE of the riff still reduces the
    head instead of being handed nothing."""
    head = mukhada or hook_seed_for_riff(arr)
    return generate_riff(arr, gen_fn=_LLMRiff(arr, head), head=head)


class _SeededRiff:
    """The riff library around a FIXED main riff: the main slot (`main_riff_slot`) IS the
    Composer's seed riff — no call, only voiced by function and hard-checked like any take — and
    every other slot is composed by the same musician (`others`), shown the whole seed."""

    def __init__(self, arr: Arrangement, others: RiffFn) -> None:
        self._main = main_riff_slot(arr)
        self._seed = arr.seed_riff
        self._others = others

    def __call__(self, span: SectionSpan, arr: Arrangement, memory: list[RiffMemo]) -> RiffPattern:
        if self._seed is not None and slot_for(span.section) == self._main:
            seed = self._seed
            return voiced_and_verified(lambda feedback: seed, span.section, arr)
        return self._others(span, arr, memory)


def compose_seeded_riff(arr: Arrangement, *, agent_key: str = "composer",
                        others: RiffFn | None = None) -> tuple[Layer | None, list[DebateEvent]]:
    """The DEVELOP half of the single Composer for the riff: the seed riff plays the main slot,
    the other slots are composed by the `composer` persona. In a gat_first gat the realised head
    (stored as `seed_hook` once the gat call composed it) takes precedence on the slots that
    inherit it: the seed riff was written before the head existed, so it cannot be the head's
    reduction. `others` is injectable for tests."""
    head = hook_seed_for_riff(arr)
    fallback = others or _LLMRiff(arr, head, agent_key)
    return generate_riff(arr, gen_fn=_SeededRiff(arr, fallback), head=head)


def riff_schema() -> str:
    """The RiffPattern JSON shape, as the riff prompt shows it — reused by the Composer's seed."""
    return _OUTPUT_SCHEMA


# A canvas-aware per-section riff call, for the cooperative studio loop: (span, memory,
# canvas, move) -> the section's riff, locked under whatever the lead put on the canvas.
type StudioRiffFn = Callable[[SectionSpan, list[RiffMemo], SectionCanvas, CanvasMove], RiffPattern]


def studio_riff_fn(arr: Arrangement) -> StudioRiffFn:
    """A CANVAS-AWARE riff generator for the studio loop — the per-section counterpart to
    `compose_riff`. Generates ONE section's riff given the shared canvas (the lead's line to
    support) and the move (propose / respond / refine); crew + context built once, reused.
    Voiced and verified the same way as the solo path (`voiced_and_verified`), so both
    composition roots share one boundary."""
    crew = _RiffCrew()
    context = _RiffContext(arr)

    def gen(span: SectionSpan, memory: list[RiffMemo], canvas: SectionCanvas,
            move: CanvasMove) -> RiffPattern:
        slot = span.section.riff_slot or span.section.kind.value

        def attempt(fb: list[str] | None) -> RiffPattern:
            if fb is None:
                beat("Riff", f"'{slot}' riff — {move.value}…")
            else:
                beat("Riff", f"re-rolling the '{slot}' riff — flagged: {flags(fb)}",
                     data={"violations": fb, "slot": slot})
            return crew.run(arr.raga, context.inputs_for(
                span, memory, canvas=canvas, move=move, feedback=fb))

        return voiced_and_verified(attempt, span.section, arr)

    return gen


# --------------------------------------------------------------------------- #
# The imperative edge — a single live confirmation: riff + bass + drone.       #
# --------------------------------------------------------------------------- #

def _riff_demo_arrangement() -> Arrangement:
    """A one-section chart (rhythm + drone) so the live confirmation is ONE LLM call.

    Malkauns/doom: a slow, crushing riff whose bass shadow is easy to hear. Built
    through the real composer contract (no LLM here)."""
    from crew.contracts import ArrangementDraft, CompositionBrief, Section, SectionKind, build_arrangement
    draft = ArrangementDraft(
        raga="malkauns", subgenre="doom", tala="teentaal", bpm=72,
        motif=["d", "n", "S", "m"],
        sections=[Section(kind=SectionKind.RIFF, bars=2, layers=["rhythm", "drone"],
                          foreground="rhythm",
                          intent="a crushing, root-heavy doom riff on Sa and komal Ga")],
    )
    return build_arrangement(draft, CompositionBrief(mood="dark"))


def _run() -> None:
    arr = _riff_demo_arrangement()
    stream = EventStream()
    rhythm, events = compose_riff(arr)
    for event in events:
        stream.emit(event)

    bass = bass_layer(arr, rhythm)
    layers = [drone_layer(arr)] + [x for x in (rhythm, bass) if x is not None]
    comp = assemble_composition(arr, layers)
    payload = comp.model_dump(exclude_none=True)
    violations = validate_composition(payload)
    print(f"riff+bass+drone composition ({len(layers)} layers): "
          f"{len(violations)} grammar violation(s)")

    if shutil.which("fluidsynth") and _SOUNDFONT.exists():
        wav = render_composition(comp, out_dir=_OUT_DIR, name="riff_bass", soundfont=_SOUNDFONT)
        print(f"-> rendered {wav.relative_to(_ROOT)}")
    else:
        print("-> render skipped (fluidsynth or soundfont not found)")


def main(argv: list[str]) -> int:
    load_env()
    from contextlib import nullcontext

    from crew.tracing import traced, tracing_enabled
    ctx = traced("riff-demo") if tracing_enabled() else nullcontext()
    with ctx:
        _run()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
