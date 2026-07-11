"""
The composers (agent #2) — Pandit <-> Riffsmith, a BOUNDED dialogue that produces
the Arrangement (the shared chart).

The pattern on show: TWO AGENTS COLLABORATE TO CREATE, with OPPOSED priors. Pandit
argues for the raga's depth, Riffsmith for metal impact; they share one goal. The
tension is deliberate — two neutral agents collapse into agreement-theater with
nothing to watch. Crucially, WE own the loop: the transcript and the evolving
draft live in explicit state and we step turn-by-turn (Pandit proposes ->
Riffsmith responds -> ...), capped by `COMPOSER_TURNS`. That cap — not organic
consensus — is the guaranteed terminator (the Conductor makes the tie-break smart
in step 6; until then, the last draft stands).

Legality stays code's job: each turn's draft is validated at the boundary (the
motif must be legal in the raga) and an illegal draft is bounced back to the
composer with the precise error for ONE bounded retry. The LLM is the composer;
code only holds the hard line (legality) and derives verified facts (the tala's
accent grid), never the music.

Layering follows the repo's pure-core / imperative-shell split:
  * pure           — the `_render_*` functions and `_PromptContext` turn facts into
                     prompt text; `run_dialogue` is pure control flow over an
                     injected `turn_fn` (so the whole loop is tested with no LLM).
  * imperative     — `_ComposerCrew` / `_LLMTurns` make the actual Gemini calls.

Entry point:  uv run python -m crew.composers "a crushing dark metal fusion"
"""

from __future__ import annotations

import itertools
import sys
from collections.abc import Callable
from enum import Enum
from pathlib import Path
from typing import Any, Final

import yaml
from crewai import Agent, Crew, Process, Task
from pydantic import ValidationError

from crew.config import (
    COMPOSER_MAX_ITER,
    COMPOSER_RETRIES,
    COMPOSER_TURNS,
    composer_llm,
    load_env,
)
from crew.contracts import (
    ROLES,
    Arrangement,
    ArrangementDraft,
    CompositionBrief,
    ComposerTurn,
    DebateEvent,
    EventStream,
    EventType,
    SectionKind,
    build_arrangement,
    motif_illegal_in_raga,
)
from crew.interpreter import interpret
from raga import RAGAS
from subgenres import SUBGENRES
from talas import TALAS


class Composer(Enum):
    """One of the two composers. The value is the display name; `config_key`
    indexes the agent's entry in agents.yaml."""
    PANDIT = "Pandit"
    RIFFSMITH = "Riffsmith"

    @property
    def config_key(self) -> str:
        return self.name.lower()


# Pandit opens; then they alternate. This tuple IS the turn order.
_TURN_ORDER: Final[tuple[Composer, ...]] = (Composer.PANDIT, Composer.RIFFSMITH)

# DebateEvent role for a composer turn (the others: "system", "critic", ...).
_ROLE_COMPOSER: Final = "composer"
_ROLE_SYSTEM: Final = "system"

# One-line meaning per section kind — the composer's vocabulary. Keyed by enum
# value so a new SectionKind without a description fails loud here (KeyError in
# `_render_section_kinds`) rather than silently shipping an undocumented kind.
_SECTION_DESC: Final[dict[str, str]] = {
    "alaap": "slow, unmetered raga exposition; lead-led, usually no drums",
    "riff": "the main metal riff statement; rhythm-led",
    "melody": "the motif sung as a theme over the groove",
    "taan": "fast, virtuosic melodic run — the climax",
    "solo": "lead improvisation over the riff",
    "breakdown": "heavy, sparse rhythm + drums crush",
    "outro": "cadential resolution",
}

# One-line meaning per LAYER role (the voices). Keyed by role so a new ROLE without
# a description fails loud in `_render_layers`. Note tabla + drums may coexist.
_LAYER_DESC: Final[dict[str, str]] = {
    "lead": "the melodic voice (sitar-like lead / lead guitar) — the raga line, taans, solos",
    "rhythm": "the metal rhythm guitar — downtuned riffs and power chords",
    "drums": "the metal drum kit (kick/snare/cymbals) — the metal groove",
    "tabla": "Hindustani tabla — lays the tala's theka; may play ALONGSIDE the metal drums",
    "drone": "the tanpura drone — a sustained Sa+Pa pad anchoring the tonality",
}

# The exact JSON shape we want back, injected as an input so CrewAI's {placeholder}
# interpolation never has to parse these literal braces.
_OUTPUT_SCHEMA: Final = """{
  "reasoning": "your private monologue: one thing you respect in your counterpart's last turn, one you push back on",
  "draft": {
    "raga": "malkauns",
    "subgenre": "doom",
    "tala": "teentaal",
    "bpm": 72,
    "motif": ["d", "n", "S", "m"],
    "sections": [
      {"kind": "alaap", "bars": 2, "layers": ["lead", "tabla", "drone"], "foreground": "lead", "intent": "unfold the raga slowly over soft tabla", "transition": "tabla drops out; a 2-beat silence before the riff"},
      {"kind": "riff", "bars": 4, "layers": ["rhythm", "drums", "tabla", "drone"], "foreground": "rhythm", "intent": "tabla theka under the heavy downtuned groove", "transition": "a shared tihai lands on the sam into the taan"}
    ],
    "registers": {"lead": 0, "rhythm": -3, "drone": -3}
  },
  "note": "one or two sentences arguing your change, in character",
  "agree": false
}
"reasoning" comes FIRST. "registers" is OPTIONAL — omit it to use sensible defaults. "intent" and "transition" are short free-text hints and may be empty."""


# --------------------------------------------------------------------------- #
# Pure renderers: FACTS (raga/tala/subgenre data) -> prompt text. Never inline #
# prose — the single source of truth stays in raga.py / talas.py / subgenres.py.#
# --------------------------------------------------------------------------- #

def _render_brief(brief: CompositionBrief) -> str:
    """Spell out what the user FIXED (honor exactly) vs. what is OPEN (compose)."""
    lines = [
        f"  raga: FIXED = {brief.raga} (use this raga)" if brief.raga
        else "  raga: OPEN — you choose (let the mood guide you)",
        f"  subgenre: FIXED = {brief.subgenre}" if brief.subgenre
        else "  subgenre: OPEN — you choose",
        f"  key/Sa: FIXED = {brief.key} (Sa={brief.sa})" if brief.key
        else "  key/Sa: OPEN — a sensible default is applied",
        f"  bpm: FIXED = {brief.bpm}" if brief.bpm else "  bpm: OPEN — you choose",
        "  tala: OPEN — you always choose the rhythmic cycle",
    ]
    if brief.mood:
        lines.append(f"  mood to honor: {brief.mood}")
    if brief.instruments:
        lines.append(f"  instruments the user mentioned: {', '.join(brief.instruments)}")
    return "\n".join(lines)


def _render_raga_line(key: str) -> str:
    r = RAGAS[key]
    return (f"  - {key}: {r['display']} — {r['western_mode']}; "
            f"allowed swaras: {' '.join(r['allowed'])}; vadi {r['vadi']}, samvadi {r['samvadi']}; "
            f"{r['samay']}")


def _render_raga_block(key: str) -> str:
    """Full facts for a FIXED raga — enough to compose idiomatically."""
    r = RAGAS[key]
    lines = [
        _render_raga_line(key),
        f"    aroha: {' '.join(r['aroha'])}   avaroha: {' '.join(r['avaroha'])}",
        f"    pakad: {' | '.join(' '.join(p) for p in r['pakad'])}",
        f"    chalan: {' | '.join(' '.join(p) for p in r['chalan'])}",
    ]
    if r.get("andolan"):
        lines.append(f"    andolan (swaras that oscillate — idiomatic): {' '.join(r['andolan'])}")
    return "\n".join(lines)


def _render_ragas(brief: CompositionBrief) -> str:
    """The fixed raga's full facts, or a compact line for each supported raga."""
    if brief.raga:
        return _render_raga_block(brief.raga)
    return "\n".join(_render_raga_line(key) for key in RAGAS)


def _render_talas() -> str:
    lines = []
    for key, t in TALAS.items():
        vibhags = "+".join(str(v) for v in t["vibhags"])
        lines.append(f"  - {key}: {t['display']} — {t['matras']} matras in {vibhags}; "
                     f"sam {t['sam']}, tali {t['tali']}, khali {t['khali']}")
    return "\n".join(lines)


def _render_subgenre_line(key: str) -> str:
    s = SUBGENRES[key]
    lo, hi = s["bpm"]
    reg_lo, reg_hi = s["register"]
    return (f"  - {key}: {s['display']} — {lo}-{hi} bpm; {s['feel']}; "
            f"register octaves [{reg_lo}, {reg_hi}] (lower = heavier)")


def _render_subgenres(brief: CompositionBrief) -> str:
    if brief.subgenre:
        return _render_subgenre_line(brief.subgenre)
    return "\n".join(_render_subgenre_line(key) for key in SUBGENRES)


def _render_section_kinds() -> str:
    return "\n".join(f"  - {kind.value}: {_SECTION_DESC[kind.value]}" for kind in SectionKind)


def _render_layers() -> str:
    return "\n".join(f"  - {role}: {_LAYER_DESC[role]}" for role in sorted(ROLES))


def _render_pakad_seeds(brief: CompositionBrief) -> str:
    keys = [brief.raga] if brief.raga else list(RAGAS)
    return "\n".join(f"  - {key}: {' '.join(phrase)}"
                     for key in keys for phrase in RAGAS[key]["pakad"])


def _render_transcript(transcript: list[tuple[str, str]]) -> str:
    if not transcript:
        return "  (nothing yet — you are speaking first)"
    return "\n".join(f"  {who}: {note}" for who, note in transcript)


def _render_draft(draft: ArrangementDraft | None) -> str:
    if draft is None:
        return "  (no draft yet — propose one)"
    sections = "; ".join(
        f"{s.kind.value}[{s.bars}b, {'+'.join(s.layers)}, fg={s.foreground}]" for s in draft.sections)
    registers = f"\n  registers: {draft.registers}" if draft.registers else ""
    return (f"  raga={draft.raga}, subgenre={draft.subgenre}, tala={draft.tala}, bpm={draft.bpm}\n"
            f"  motif: {' '.join(draft.motif)}\n"
            f"  sections: {sections}{registers}")


def _render_arrangement(arr: Arrangement) -> str:
    form = " -> ".join(s.kind.value for s in arr.sections)
    return (f"{arr.raga} x {arr.subgenre} in {arr.tala} @ {arr.bpm}bpm (Sa={arr.sa}); "
            f"motif {' '.join(arr.motif)}; form: {form}")


def _draft_summary(draft: ArrangementDraft) -> dict[str, Any]:
    """A compact draft snapshot for the DebateEvent payload the UI renders."""
    return {"raga": draft.raga, "subgenre": draft.subgenre, "tala": draft.tala,
            "bpm": draft.bpm, "motif": draft.motif,
            "sections": [s.kind.value for s in draft.sections]}


class _PromptContext:
    """Assembles a composer turn's prompt inputs from the facts.

    The brief-derived context (what's fixed vs. open, the raga/subgenre/seed facts)
    is CONSTANT across a dialogue, so it is rendered ONCE at construction; only the
    turn number, transcript and evolving draft change per turn. Pure — no I/O.
    """

    def __init__(self, brief: CompositionBrief, *, max_turns: int) -> None:
        self._static: dict[str, Any] = {
            "max_turns": max_turns,
            "brief_context": _render_brief(brief),
            "raga_context": _render_ragas(brief),
            "tala_context": _render_talas(),
            "subgenre_context": _render_subgenres(brief),
            "section_kinds": _render_section_kinds(),
            "layer_roles": _render_layers(),
            "seed_context": _render_pakad_seeds(brief),
            "output_schema": _OUTPUT_SCHEMA,
        }

    def inputs_for(self, speaker: Composer, turn_no: int, draft: ArrangementDraft | None,
                   transcript: list[tuple[str, str]]) -> dict[str, Any]:
        return {
            **self._static,
            "composer": speaker.value,
            "turn_no": turn_no,
            "transcript": _render_transcript(transcript),
            "current_draft": _render_draft(draft),
        }


# --------------------------------------------------------------------------- #
# Boundary parsing + the guardrail (the hard legality line). Imperative-ish.   #
# --------------------------------------------------------------------------- #

def _turn_from_output(output: Any) -> ComposerTurn | None:
    """The ComposerTurn CrewAI parsed via output_pydantic (or None if parsing failed)."""
    parsed = getattr(output, "pydantic", None)
    if isinstance(parsed, ComposerTurn):
        return parsed
    raw = getattr(output, "raw", None)
    try:
        return ComposerTurn.model_validate_json(raw) if raw else None
    except ValidationError:
        return None


def _validate_turn(output: Any):
    """Task guardrail — the ONE domain rule kept out of the schema: the composer's
    motif must be legal in its raga. `output_pydantic` already guarantees the SHAPE;
    this checks the raga grammar and, on a violation, returns the precise error so
    CrewAI re-runs the turn (a bounded retry, not a loop).

    Contract: returns (True, ComposerTurn) or (False, error-message). CrewAI inspects
    this guardrail's RETURN ANNOTATION and requires the literal object tuple[bool, Any];
    this module's `from __future__ import annotations` would stringify a normal hint
    and CrewAI rejects the string — so it is attached as a real object below the def.
    """
    turn = _turn_from_output(output)
    if turn is None:
        return (False, "Return a single valid ComposerTurn JSON object and nothing else.")
    illegal = motif_illegal_in_raga(turn.draft.motif, turn.draft.raga)
    if illegal:
        allowed = " ".join(RAGAS[turn.draft.raga]["allowed"])
        return (False, f"motif swaras {illegal} are illegal in raga {turn.draft.raga}. "
                       f"Use only these swaras: {allowed}. Fix the motif and resend.")
    return (True, turn)


_validate_turn.__annotations__["return"] = tuple[bool, Any]


class _ComposerCrew:
    """Runs ONE composer turn as an isolated, single-agent crew.

    We own the loop, so each turn is an explicit call with the shared state injected
    as inputs — not CrewAI's autonomous delegation. Structured output is CrewAI's job
    (`output_pydantic=ComposerTurn`), so there is no hand-rolled JSON parsing; the
    guardrail adds only the domain (legality) check. Config is read once at construction.
    """

    def __init__(self) -> None:
        config_dir = Path(__file__).parent / "config"
        self._agent_configs = yaml.safe_load((config_dir / "agents.yaml").read_text())
        self._task_config = yaml.safe_load((config_dir / "tasks.yaml").read_text())["compose_turn"]

    def run(self, speaker: Composer, inputs: dict[str, Any]) -> ComposerTurn:
        task = self._build_task(speaker)
        crew = Crew(agents=[task.agent], tasks=[task], process=Process.sequential, verbose=False)
        result = crew.kickoff(inputs=inputs)
        turn = _turn_from_output(result)
        if turn is None:
            raise ValueError(f"composer {speaker.value} returned no parseable ComposerTurn")
        return turn

    def _build_task(self, speaker: Composer) -> Task:
        # allow_delegation=False: WE drive the turn order, not autonomous delegation.
        # max_iter: a modest per-turn circuit-breaker beneath our across-turn cap.
        # output_pydantic: CrewAI parses+validates the SHAPE into a ComposerTurn;
        # the guardrail adds the raga-legality domain check with a bounded retry.
        agent = Agent(config=self._agent_configs[speaker.config_key], llm=composer_llm(),
                      allow_delegation=False, max_iter=COMPOSER_MAX_ITER, verbose=False)
        return Task(config=self._task_config, agent=agent, output_pydantic=ComposerTurn,
                    guardrail=_validate_turn, guardrail_max_retries=COMPOSER_RETRIES)


# A turn provider: given the speaker and the shared state, return their turn.
type TurnFn = Callable[[Composer, ArrangementDraft | None, list[tuple[str, str]]], ComposerTurn]


class _LLMTurns:
    """The real (LLM-backed) `turn_fn`. Holds the crew and the precomputed prompt
    context across the dialogue's turns."""

    def __init__(self, brief: CompositionBrief, *, max_turns: int) -> None:
        self._crew = _ComposerCrew()
        self._context = _PromptContext(brief, max_turns=max_turns)

    def __call__(self, speaker: Composer, draft: ArrangementDraft | None,
                 transcript: list[tuple[str, str]]) -> ComposerTurn:
        turn_no = len(transcript) + 1
        return self._crew.run(speaker, self._context.inputs_for(speaker, turn_no, draft, transcript))


# --------------------------------------------------------------------------- #
# The bounded dialogue loop — pure control flow, LLM injected via `turn_fn`.    #
# The DebateEvent builders below keep the loop body about CONTROL, not wording. #
# --------------------------------------------------------------------------- #

_OPENING_ROUND: Final = 1  # round 1 is a proposal; there is nothing yet to argue with


def _system_event(text: str, *, round_no: int | None = None) -> DebateEvent:
    return DebateEvent(type=EventType.INFO, agent="System", role=_ROLE_SYSTEM,
                       text=text, round=round_no)


def _turn_event(speaker: Composer, turn: ComposerTurn, round_no: int) -> DebateEvent:
    kind = EventType.PROPOSE if round_no == _OPENING_ROUND else EventType.DEBATE
    return DebateEvent(type=kind, agent=speaker.value, role=_ROLE_COMPOSER,
                       text=turn.note, round=round_no,
                       data={"draft": _draft_summary(turn.draft), "reasoning": turn.reasoning})


def _agreement_event(speaker: Composer, round_no: int) -> DebateEvent:
    return DebateEvent(type=EventType.INFO, agent=speaker.value, role=_ROLE_COMPOSER,
                       text="agrees — the chart serves both sides.", round=round_no)


def run_dialogue(brief: CompositionBrief, *, turn_fn: TurnFn,
                 max_turns: int = COMPOSER_TURNS) -> tuple[Arrangement, list[DebateEvent]]:
    """Step Pandit and Riffsmith turn-by-turn to a shared Arrangement.

    Bounded and always-terminating: it stops when a RESPONDING composer AGREES, or
    when the turn cap is hit (the guaranteed terminator — the Conductor makes the
    un-agreed tie-break smart in step 6; here the last draft stands). Emits a
    DebateEvent per turn (the streamed transcript) plus setup/verdict INFO events.
    `turn_fn` is injected so the loop is tested with no LLM.
    """
    if max_turns < 1:
        raise ValueError("max_turns must be at least 1")

    events = [_system_event(f"Composers open on brief: {_render_brief(brief).strip()}")]
    transcript: list[tuple[str, str]] = []
    draft: ArrangementDraft | None = None
    speakers = itertools.cycle(_TURN_ORDER)  # Pandit opens, then they alternate
    agreed = False

    for round_no in range(_OPENING_ROUND, max_turns + 1):
        speaker = next(speakers)
        turn = turn_fn(speaker, draft, list(transcript))
        draft = turn.draft
        transcript.append((speaker.value, turn.note))
        events.append(_turn_event(speaker, turn, round_no))

        if turn.agree and round_no > _OPENING_ROUND:  # an opener has nothing to agree with
            agreed = True
            events.append(_agreement_event(speaker, round_no))
            break

    if not agreed:
        events.append(_system_event(
            f"Turn cap ({max_turns}) reached — last draft stands "
            f"(the Conductor will arbitrate in step 6).", round_no=len(transcript)))

    arrangement = build_arrangement(draft, brief)  # draft is set: max_turns >= 1
    events.append(_system_event(f"Arrangement: {_render_arrangement(arrangement)}"))
    return arrangement, events


def compose(brief: CompositionBrief, *,
            max_turns: int = COMPOSER_TURNS) -> tuple[Arrangement, list[DebateEvent]]:
    """Run the real (LLM-backed) composer dialogue for a brief."""
    return run_dialogue(brief, turn_fn=_LLMTurns(brief, max_turns=max_turns), max_turns=max_turns)


def _run(query: str) -> None:
    """Interpret the query, run the composer dialogue, stream both event sets."""
    stream = EventStream()
    brief, intake_events = interpret(query)
    for event in intake_events:
        stream.emit(event)
    _, dialogue_events = compose(brief)
    for event in dialogue_events:
        stream.emit(event)


def main(argv: list[str]) -> int:
    load_env()  # entry point loads .env
    query = " ".join(argv) or "a crushing, dark metal fusion"
    # Trace by default — every live run is captured for the portal (RMA_TRACE=0 opts out).
    from contextlib import nullcontext

    from crew.tracing import traced, tracing_enabled
    ctx = traced(query) if tracing_enabled() else nullcontext()
    with ctx:
        _run(query)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
