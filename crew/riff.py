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
guardrail refuses any out-of-raga swara for one bounded retry.

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

from crew.config import GENERATOR_MAX_ITER, GENERATOR_RETRIES, generator_llm, load_env
from crew.contracts import (
    Arrangement,
    CanvasMove,
    DebateEvent,
    EventStream,
    EventType,
    Layer,
    LeadNote,
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
from crew.riff_family import develop_section
from raga import RAGAS, validate_composition
from subgenres import SUBGENRES
from talas import TALAS

_RHYTHM_ROLE: Final = "rhythm"             # the layer role this generator fills
_ROLE_GENERATOR: Final = "generator"
_ACCENT_KINDS: Final = ("sam", "tali")     # the matras a riff should punch
_RIFF_ACCENT_BOOST: Final[float] = 1.12    # velocity multiplier on an accented onset

_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
_SOUNDFONT: Final[Path] = _ROOT / "soundfonts" / "GeneralUser-GS.sf2"
_OUT_DIR: Final[Path] = _ROOT / "out"

_OUTPUT_SCHEMA: Final = """{
  "reasoning": "which raga swaras and part of the motif the riff is built on, its primary + contrast rhythm cell, and how it lands the sam",
  "notes": [
    {"swara": "S", "oct": 0, "dur": 0.5, "vel": 118, "chord": ["S"], "technique": "palm_mute"},
    {"swara": "S", "oct": 0, "dur": 0.25, "technique": "palm_mute"},
    {"swara": "S", "oct": 0, "dur": 0.25, "technique": "palm_mute"},
    {"swara": "g", "oct": 0, "dur": 0.5, "technique": "hammer_on"},
    {"rest": true, "swara": "S", "dur": 0.5},
    {"swara": "S", "oct": 0, "dur": 1.0, "chord": ["S"], "technique": "bend"}
  ]
}
"reasoning" comes FIRST. This is ONE tala cycle; the arrangement repeats AND develops it across the
section (A, A', a stripped or heaviest variant), so write one strong, COMPLETE cycle. "oct" is your
octave (0 = home/low; -1 lower). "vel" is optional. Durations are in beats (0.25 = 16th, 0.5 = 8th,
1 = quarter) and should sum to one full cycle, COUNTING rests.
"chord" (optional) = extra raga swaras sounded WITH the root, each stacked at the lowest octave
ABOVE it and each a LEGAL raga swara: add the note's OWN swara for root+octave power-chord weight
(root "g" + ["g"]); ["P"] adds Pa — a true fifth ONLY above Sa, not above every root; ["g","n"] a
raga-colour voicing. "technique" (optional) = palm_mute (a tight chug — the core texture), slide,
bend, hammer_on, pull_off; omit for a plain picked note. "rest" (optional) = a SILENT beat for
SPACE — set rest:true with any swara (ignored); include at least one per cycle so the tabla and gat breathe."""


# --------------------------------------------------------------------------- #
# Placement: one cycle -> repeated, register-seated, accent-locked notes. Pure. #
# --------------------------------------------------------------------------- #

def _sequence_cycle(pattern: list[RiffNote], cycle_beats: float, register: int) -> list[Note]:
    """Lay one cycle's notes end-to-end from beat 0, seat them in `register`, and make
    them cover EXACTLY one cycle so the riff loops seamlessly.

    A pattern that overruns is clipped at the cycle edge; one that falls SHORT has its
    last note extended to the edge, so there is no silent gap at the downbeat where
    the loop repeats (a gap would limp every bar). The LLM is asked to fill the cycle
    exactly (see the prompt); this is the guarantee behind that ask.
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
            placed.append(Note(swara=rn.swara, oct=register + rn.oct, start=round(t, 4),
                               dur=round(dur, 4), vel=rn.vel,
                               chord=rn.chord, technique=rn.technique))
            last_was_rest = False
        t += rn.dur
    # Fill a SHORT cycle so the loop has no accidental gap — UNLESS the pattern ends on a rest,
    # which is an INTENTIONAL silence into the sam (a rest-stab); then the gap is kept.
    if placed and not last_was_rest:
        last = placed[-1]
        if last.start + last.dur < cycle_beats:
            placed[-1] = last.model_copy(update={"dur": round(cycle_beats - last.start, 4)})
    return placed


def _place_cycles(cycles: list[list[RiffNote]], *, start: float, cycle_beats: float,
                  register: int, accent_beats: set[float]) -> list[Note]:
    """Place a per-bar SEQUENCE of cycles (one RiffNote list per bar), sequencing each onto its
    bar from `start` and locking it to the accent grid. Notes whose onset (within the cycle)
    lands on an accented matra (sam/tali) are punched up — this is how CODE locks the riff to
    the tala so riff and kick interlock, rather than trusting the LLM to have counted beats.
    The primitive behind BOTH the literal repeat (`place_riff`) and the developed riff family
    (`rhythm_layer_from` -> `develop_section`). Pure."""
    notes: list[Note] = []
    for bar, cycle_notes in enumerate(cycles):
        cycle = _sequence_cycle(cycle_notes, cycle_beats, register)
        offset = start + bar * cycle_beats
        for n in cycle:
            vel = min(127, round(n.vel * _RIFF_ACCENT_BOOST)) if n.start in accent_beats else n.vel
            notes.append(n.model_copy(update={"start": round(n.start + offset, 4), "vel": vel}))
    return notes


def place_riff(pattern: list[RiffNote], *, start: float, bars: int, cycle_beats: float,
               register: int, accent_beats: set[float]) -> list[Note]:
    """Repeat ONE cycle across `bars` from `start`, locking each bar to the sam — the LITERAL
    (no-variation) placement. `rhythm_layer_from` uses the developed placement (the riff family)
    instead; this stays as the primitive the accent/loop tests target. Pure."""
    return _place_cycles([pattern] * bars, start=start, cycle_beats=cycle_beats,
                         register=register, accent_beats=accent_beats)


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
    return section.riff_slot or section.kind.value


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


class _RiffContext:
    """Assembles a riff turn's prompt inputs. Piece-level facts render once; the
    per-section fields and the realized-so-far MEMORY change per turn. Pure — no I/O."""

    def __init__(self, arr: Arrangement) -> None:
        s = SUBGENRES[arr.subgenre]
        accents = ", ".join(f"beat {a.beat:g} ({a.kind})"
                            for a in arr.accent_grid if a.kind in _ACCENT_KINDS)
        self._static: dict[str, Any] = {
            "raga": RAGAS[arr.raga]["display"],
            "allowed": " ".join(RAGAS[arr.raga]["allowed"]),
            "motif": " ".join(arr.motif),
            "subgenre": s["display"],
            "subgenre_feel": s["feel"],
            "subdivision": s["subdivision"],
            "techniques": ", ".join(s["techniques"]),
            "bpm": arr.bpm,
            "tala": TALAS[arr.tala]["display"],
            "cycle_beats": f"{arr.beats_per_bar:g}",
            "accents": accents,
            "output_schema": _OUTPUT_SCHEMA,
        }

    def inputs_for(self, span: SectionSpan, memory: list[RiffMemo], *,
                   canvas: SectionCanvas | None = None,
                   move: CanvasMove = CanvasMove.PROPOSE) -> dict[str, Any]:
        section = span.section
        return {
            **self._static,
            "section_kind": section.kind.value,
            "form_role": section.form_role or "free (no gat role set)",
            "riff_slot": slot_for(section),
            "section_intent": section.intent or "(none given — use your judgment for this kind)",
            "bars": section.bars,
            "previous": _render_previous(memory),
            "move": move.value,
            "canvas": _render_canvas_for_riff(canvas, move),
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


def _riff_guardrail(raga: str):
    """The Task guardrail for a given raga: every riff swara must be legal. Returns
    (True, RiffPattern) or (False, error). The return annotation is set as a real
    object below because `from __future__ import annotations` would stringify it."""
    def guard(output: Any):
        pattern = _pattern_from_output(output)
        if pattern is None:
            return (False, "Return a single valid RiffPattern JSON object and nothing else.")
        # Every SOUNDING pitch faces the grammar — the root AND each chord tone stacked
        # on it — so a power chord / extended voicing stays legal by construction. Rests
        # sound nothing, so they are exempt (their swara is an ignored placeholder).
        sounded = [n for n in pattern.notes if not n.rest]
        swaras = [n.swara for n in sounded]
        swaras += [c for n in sounded for c in (n.chord or [])]
        illegal = motif_illegal_in_raga(swaras, raga)
        if illegal:
            allowed = " ".join(RAGAS[raga]["allowed"])
            return (False, f"swaras {sorted(set(illegal))} are illegal in raga {raga}. "
                           f"Use only these swaras (roots AND chord tones): {allowed}. Fix and resend.")
        return (True, pattern)

    guard.__annotations__["return"] = tuple[bool, Any]
    return guard


class _RiffCrew:
    """Runs ONE section's riff generation as an isolated single-agent crew."""

    def __init__(self) -> None:
        config_dir = Path(__file__).parent / "config"
        self._agent_config = yaml.safe_load((config_dir / "agents.yaml").read_text())["riff"]
        self._task_config = yaml.safe_load((config_dir / "tasks.yaml").read_text())["generate_riff"]

    def run(self, raga: str, inputs: dict[str, Any]) -> RiffPattern:
        agent = Agent(config=self._agent_config, llm=generator_llm(),
                      allow_delegation=False, max_iter=GENERATOR_MAX_ITER, verbose=False)
        task = Task(config=self._task_config, agent=agent, output_pydantic=RiffPattern,
                    guardrail=_riff_guardrail(raga), guardrail_max_retries=GENERATOR_RETRIES)
        crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)
        pattern = _pattern_from_output(crew.kickoff(inputs=inputs))
        if pattern is None:
            raise ValueError("riff generator returned no parseable RiffPattern")
        return pattern


type RiffFn = Callable[[SectionSpan, Arrangement, list[RiffMemo]], RiffPattern]


class _LLMRiff:
    """The real (LLM-backed) `gen_fn` — holds the crew and the precomputed context."""

    def __init__(self, arr: Arrangement) -> None:
        self._crew = _RiffCrew()
        self._context = _RiffContext(arr)

    def __call__(self, span: SectionSpan, arr: Arrangement, memory: list[RiffMemo]) -> RiffPattern:
        return self._crew.run(arr.raga, self._context.inputs_for(span, memory))


# --------------------------------------------------------------------------- #
# The generator loop — pure control flow, LLM injected via `gen_fn`.           #
# --------------------------------------------------------------------------- #

def _riff_event(span: SectionSpan, pattern: RiffPattern, slot: str) -> DebateEvent:
    return DebateEvent(
        type=EventType.PROPOSE, agent="Riff", role=_ROLE_GENERATOR,
        text=f"{slot} riff: {span.section.bars}-bar, {len(pattern.notes)} notes/cycle",
        data={"slot": slot, "reasoning": pattern.reasoning,
              "swaras": [n.swara for n in pattern.notes]})


def _reprise_event(span: SectionSpan, slot: str) -> DebateEvent:
    """A section replays an already-written slot — the hook returns. A light INFO beat
    (not a fresh PROPOSE) so the timeline shows the main riff coming back."""
    return DebateEvent(
        type=EventType.INFO, agent="Riff", role=_ROLE_GENERATOR,
        text=f"reprise: the {slot} riff returns ({span.section.kind.value}, "
             f"{span.section.bars} bar{'s' if span.section.bars != 1 else ''})",
        data={"slot": slot, "reprise": True})


def rhythm_layer_from(patterns: dict[int, RiffPattern], arr: Arrangement) -> Layer | None:
    """Assemble the single rhythm layer from already-generated per-section riffs (section
    index -> the base cycle that plays there).

    Each section's base cycle is DEVELOPED across its bars into the riff family
    (`develop_section`) — so a recurring riff varies (chugged A', thinned under a taan, doubled
    to land the ending) instead of looping unchanged — then placed and accent-locked. A chart
    with no declared gat form is placed literally (variant "base"). A section with no riff is
    skipped. Returns None when nothing plays. Pure — so the studio reuses it."""
    accents = _accent_beats(arr)
    spans = section_spans(arr)
    playing = [s.index for s in spans if patterns.get(s.index) is not None]
    final_rhythm = playing[-1] if playing else None      # the last section that actually plays a riff
    register = arr.registers[_RHYTHM_ROLE]
    notes: list[Note] = []
    for span in spans:
        pattern = patterns.get(span.index)
        if pattern is None:
            continue
        cycles = develop_section(pattern.notes, span.section,
                                 is_final_rhythm=(span.index == final_rhythm))
        notes.extend(_place_cycles(cycles, start=span.start, cycle_beats=arr.beats_per_bar,
                                   register=register, accent_beats=accents))
    if not notes:
        return None
    voice = VOICES[_RHYTHM_ROLE]
    return Layer(role=_RHYTHM_ROLE, instrument=voice.instrument, program=voice.program,
                 channel=voice.channel, pan=voice.pan, notes=notes)


def generate_riff(arr: Arrangement, *, gen_fn: RiffFn) -> tuple[Layer | None, list[DebateEvent]]:
    """Fill the rhythm layer across the arrangement's rhythm-active sections.

    A riff is written ONCE PER SLOT and REUSED wherever that slot recurs — so the main
    riff literally returns as a hook, distinct slots stay distinct, and `gen_fn` fires
    only for a new slot (fewer LLM calls). A recurring section emits a light reprise event
    rather than a fresh proposal. The per-section riffs are then placed/accent-locked into
    one layer via `rhythm_layer_from`. Returns (None, events) when no section uses the
    rhythm guitar. `gen_fn` is injected so this loop is tested with no LLM.
    """
    events: list[DebateEvent] = []
    patterns: dict[int, RiffPattern] = {}
    library: dict[str, RiffPattern] = {}            # slot -> its one-cycle riff
    order: list[str] = []                           # slots in first-seen order (the memory)
    for span in section_spans(arr):
        if _RHYTHM_ROLE not in span.section.layers:
            continue
        slot = slot_for(span.section)
        if slot in library:                         # the hook returns — reuse, don't regenerate
            pattern = library[slot]
            events.append(_reprise_event(span, slot))
        else:                                        # a new slot — write a riff that contrasts the rest
            memory = [RiffMemo(s, library[s]) for s in order]
            pattern = gen_fn(span, arr, memory)
            library[slot] = pattern
            order.append(slot)
            events.append(_riff_event(span, pattern, slot))
        patterns[span.index] = pattern

    layer = rhythm_layer_from(patterns, arr)
    if layer is None:
        events.append(DebateEvent(type=EventType.INFO, agent="Riff", role=_ROLE_GENERATOR,
                                  text="no rhythm-active sections in this arrangement"))
    return layer, events


def compose_riff(arr: Arrangement) -> tuple[Layer | None, list[DebateEvent]]:
    """Run the real (LLM-backed) riff generation for a chart."""
    return generate_riff(arr, gen_fn=_LLMRiff(arr))


# A canvas-aware per-section riff call, for the cooperative studio loop: (span, memory,
# canvas, move) -> the section's riff, locked under whatever the lead put on the canvas.
type StudioRiffFn = Callable[[SectionSpan, list[RiffMemo], SectionCanvas, CanvasMove], RiffPattern]


def studio_riff_fn(arr: Arrangement) -> StudioRiffFn:
    """A CANVAS-AWARE riff generator for the studio loop — the per-section counterpart to
    `compose_riff`. Generates ONE section's riff given the shared canvas (the lead's line to
    support) and the move (propose / respond / refine); crew + context built once, reused."""
    crew = _RiffCrew()
    context = _RiffContext(arr)

    def gen(span: SectionSpan, memory: list[RiffMemo], canvas: SectionCanvas,
            move: CanvasMove) -> RiffPattern:
        return crew.run(arr.raga, context.inputs_for(span, memory, canvas=canvas, move=move))

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
