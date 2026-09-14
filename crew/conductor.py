"""
The Conductor (agent #6, step 6) — the ARBITER with a clock. The talk's money moment.

The pattern on show: DISAGREEMENT -> BOUNDED DEBATE -> A REFEREE'S VERDICT. But the
debate is only a real contest if the two sides have a real stake. By the time a debate
opens the piece is already LEGAL (triage forces a revise on anything illegal), so the
legality critic Ustad has NOTHING aesthetic to argue — "it lacks soul" vs "but it's
legal" is a non-contest. So Ustad EXITS here (its job ended at triage) and the genuine
argument is SOUL vs IMPACT: Rasik (tradition -> revise) against a Producer (momentum ->
ship, a revise risks the drive). Someone still has to decide, on a clock. That someone
is the Conductor.

Two things make this safe and legible rather than "autonomous magic":

  1. CODE settles what code can. Legality is non-negotiable, so an ILLEGAL piece is
     revised with NO debate (the guardrail wins); a legal piece with sound aesthetics is
     accepted with NO debate. The LLM debate fires ONLY on the genuine judgment call —
     legal, but Rasik flags a real aesthetic weakness — so we never spend model budget on
     a decision code already owns. `detect_conflict` is that pure (HYBRID) triage: a
     critical criterion (pakad/idiom) low, OR the overall mean low.
  2. WE own the loop. The Rasik<->Producer debate is stepped turn-by-turn in explicit
     state (exactly like the composer dialogue), bounded by `MAX_ROUNDS`, and the
     Conductor ALWAYS rules at the cap. The round cap — not organic consensus — is the
     guaranteed terminator. The referee and the clock, in code.

The ruling names ONE layer so the Flow's SURGICAL revise (step 6b) can regenerate just
that voice; executing the revise loop and rendering is the next step. Here we produce
the DECISION and stream the debate.

Layering follows the repo's pure-core / imperative-shell split:
  * pure       — `detect_conflict` and `arbitrate` (control flow over injected
                 `debate_fn`/`rule_fn`), the `_render_*` helpers and event builders;
                 all tested with no LLM.
  * imperative — `_ConductorCrew` / `_LLMArbiter` make the actual Gemini calls.

Entry point (a single cheap live run on a planted legal-but-weak conflict):
  uv run python -m crew.conductor
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
from pydantic import BaseModel, ValidationError

from crew.config import (
    AGENT_RETRY_LIMIT,
    CRITIC_MAX_ITER,
    MAX_ROUNDS,
    RASIK_OVERALL_FLOOR,
    RASIK_PASS_SCORE,
    conductor_llm,
    critic_llm,
    load_env,
)
from crew.contracts import (
    Composition,
    ConductorRuling,
    DebateEvent,
    DebateTurn,
    EventType,
    ProducerVerdict,
    RasikVerdict,
    UstadVerdict,
    repair_operation,
)


class Critic(Enum):
    """A DEBATING critic. Ustad is NOT here — its legality job ends at triage, so it does
    not debate (an already-legal piece gives it no aesthetic stake). The two aesthetic
    critics debate: Rasik (raga soul) vs the Producer (does it work as a song). The value
    is the display name; `config_key` indexes the agent in agents.yaml (both reuse the
    shared debate_turn task, their bias living in their backstories)."""
    RASIK = "Rasik"
    PRODUCER = "Producer"

    @property
    def config_key(self) -> str:
        return self.name.lower()


class Conflict(Enum):
    """The triage outcome — which of the three situations the critics leave us in."""
    FORCED_REVISE = "forced_revise"   # illegal — legality is non-negotiable, no debate
    NONE = "none"                     # legal and Rasik is satisfied — accept, no debate
    AESTHETIC = "aesthetic"           # legal but Rasik flags a weakness — DEBATE


# Rasik opens the debate (soul first); then they alternate with the Producer.
_DEBATE_ORDER: Final[tuple[Critic, ...]] = (Critic.RASIK, Critic.PRODUCER)

_ROLE_CRITIC: Final = "critic"
_ROLE_CONDUCTOR: Final = "conductor"
_ROLE_SYSTEM: Final = "system"

_DEBATE_SCHEMA: Final = """{
  "reasoning": "your read of the other side and the evidence",
  "argument": "your point in one or two sentences, in character",
  "stance": "revise",
  "target_layer": "lead"
}
"target_layer" is required only when stance is "revise"; use null otherwise."""

_RULING_SCHEMA: Final = """{
  "reasoning": "weigh both sides against the evidence, then decide",
  "directive": "revise",
  "operation": "regenerate_lead",
  "reason": "a short surgical directive the generator can act on"
}
"operation" is required only when directive is "revise"; use null otherwise."""

# The repairs the Conductor may call for, as the prompt lists them. Kept beside the schema
# so the ask and what the Flow can actually dispatch never drift apart.
_OPERATIONS_BRIEF: Final = """      - regenerate_lead: the RAGA LINE itself is weak — it does not sound like the raga,
        or the phrasing is dull. Compose the melody again with your directive.
      - regenerate_riff: the RIFF itself is weak — unmemorable, not heavy, no hook.
        Compose the rhythm guitar again with your directive.
      - regenerate_orchestra: the orchestration is wrong — too thick, too thin, doubling
        instead of answering. Re-score it around the unchanged band.
      - arrange_riff_against_lead: the two parts are each GOOD but they FIGHT — the guitar
        clashes with the sitar, its chords feel random under the melody, or it argues where
        it should hold a floor. Nothing is regenerated: the guitar's voicing, articulation
        and sustain are re-decided against THIS lead. Choose this whenever the complaint is
        about how the parts sit TOGETHER rather than about one part being bad — regenerating
        a good voice to fix a relationship throws the good voice away."""


# --------------------------------------------------------------------------- #
# Pure triage: which situation are we in? CODE settles what code can; the LLM  #
# debate fires only on the genuine aesthetic judgment call — HYBRID, over BOTH  #
# aesthetic critics (Rasik authenticity + Producer craft).                     #
# --------------------------------------------------------------------------- #

# Each aesthetic critic's rubric, and the CRITICAL sub-set whose weakness alone opens a
# debate (the raga's soul for Rasik; the two biggest songwriting omissions for Producer).
_RASIK_CRITERIA: Final = ("pakad", "idiom", "rasa")
_RASIK_CRITICAL: Final = ("pakad", "idiom")
_PRODUCER_CRITERIA: Final = ("structure", "dynamics", "climax", "motif", "hook",
                             "balance", "independence", "mood_fit", "repetition")
_PRODUCER_CRITICAL: Final = ("structure", "motif")


def _below(scores: Any, criteria: tuple[str, ...], pass_score: int) -> list[str]:
    """The rubric criteria scored BELOW the passing line (empty == all acceptable)."""
    return [name for name in criteria if getattr(scores, name) < pass_score]


def _mean(scores: Any, criteria: tuple[str, ...]) -> float:
    return sum(getattr(scores, name) for name in criteria) / len(criteria)


def _dissatisfied(scores: Any, criteria: tuple[str, ...], critical: tuple[str, ...], *,
                  pass_score: int, floor: float) -> bool:
    """HYBRID rule for one aesthetic critic: it objects if a CRITICAL criterion is below
    the pass line OR its OVERALL mean is below the floor. The critical prong protects the
    essentials; the mean prong catches broad mediocrity — so a lone weak NON-critical
    criterion, with everything else strong, does not on its own open a debate."""
    return bool(_below(scores, critical, pass_score)) or _mean(scores, criteria) < floor


def detect_conflict(ustad: UstadVerdict, rasik: RasikVerdict, producer: ProducerVerdict, *,
                    pass_score: int = RASIK_PASS_SCORE,
                    floor: float = RASIK_OVERALL_FLOOR) -> Conflict:
    """Triage the three verdicts. Illegality forces a revise (code owns legality). A legal
    piece opens the AESTHETIC debate if EITHER aesthetic critic is dissatisfied (the hybrid
    rule above) — Rasik on the raga's soul, or the Producer on the song's craft. Otherwise
    both are content and the piece is accepted with no LLM spend."""
    if ustad.verdict == "illegal":
        return Conflict.FORCED_REVISE
    rasik_bad = _dissatisfied(rasik.scores, _RASIK_CRITERIA, _RASIK_CRITICAL,
                              pass_score=pass_score, floor=floor)
    producer_bad = _dissatisfied(producer.scores, _PRODUCER_CRITERIA, _PRODUCER_CRITICAL,
                                 pass_score=pass_score, floor=floor)
    if rasik_bad or producer_bad:
        return Conflict.AESTHETIC
    return Conflict.NONE


def _flagged(rasik: RasikVerdict, producer: ProducerVerdict, *,
             pass_score: int = RASIK_PASS_SCORE) -> str:
    """A human summary of what each critic scored below the pass line — for the debate
    opening and the prompt context (empty prongs are omitted)."""
    parts = []
    r = _below(rasik.scores, _RASIK_CRITERIA, pass_score)
    p = _below(producer.scores, _PRODUCER_CRITERIA, pass_score)
    if r:
        parts.append("Rasik: " + ", ".join(r))
    if p:
        parts.append("Producer: " + ", ".join(p))
    return "; ".join(parts) or "broad mediocrity (low overall)"


# --------------------------------------------------------------------------- #
# Pure renderers + event builders. Wording lives here; the loop body stays     #
# about CONTROL.                                                               #
# --------------------------------------------------------------------------- #

def _scores_str(rasik: RasikVerdict) -> str:
    s = rasik.scores
    return f"pakad={s.pakad} idiom={s.idiom} rasa={s.rasa}"


def _producer_scores_str(producer: ProducerVerdict) -> str:
    s = producer.scores
    return (f"structure={s.structure} dynamics={s.dynamics} climax={s.climax} motif={s.motif} "
            f"hook={s.hook} balance={s.balance} independence={s.independence} "
            f"mood_fit={s.mood_fit} repetition={s.repetition}")


def _render_ustad_summary(ustad: UstadVerdict) -> str:
    if ustad.verdict == "legal":
        return f"LEGAL — no grammar violations. {ustad.explanation}".strip()
    return f"ILLEGAL — {len(ustad.violations)} violation(s). {ustad.explanation}".strip()


def _render_rasik_summary(rasik: RasikVerdict) -> str:
    return f"{_scores_str(rasik)} (1-5). {rasik.notes}".strip()


def _render_producer_summary(producer: ProducerVerdict) -> str:
    return f"{_producer_scores_str(producer)} (1-5). {producer.notes}".strip()


def _render_voices(comp: Composition) -> str:
    return ", ".join(layer.role for layer in comp.layers)


def _render_lead_line(comp: Composition) -> str:
    """The lead voice's swaras in time order, so a critic can point to specifics in the
    debate (empty if there is no lead)."""
    for layer in comp.layers:
        if layer.role == "lead" and layer.notes:
            ordered = sorted(layer.notes, key=lambda note: note.start)
            return " ".join(n.swara if n.oct == 0 else f"{n.swara}({n.oct:+d})" for n in ordered)
    return "(no lead voice)"


def _render_transcript(transcript: list[tuple[str, str]]) -> str:
    if not transcript:
        return "  (nothing yet — you speak first)"
    return "\n".join(f"  {who}: {argument}" for who, argument in transcript)


def _system_event(text: str, *, round_no: int | None = None) -> DebateEvent:
    return DebateEvent(type=EventType.INFO, agent="System", role=_ROLE_SYSTEM,
                       text=text, round=round_no)


def _debate_event(critic: Critic, turn: DebateTurn, round_no: int) -> DebateEvent:
    return DebateEvent(type=EventType.DEBATE, agent=critic.value, role=_ROLE_CRITIC,
                       text=turn.argument, verdict=turn.stance, round=round_no,
                       data={"reasoning": turn.reasoning, "target_layer": turn.target_layer})


def _ruling_event(ruling: ConductorRuling) -> DebateEvent:
    return DebateEvent(type=EventType.VERDICT, agent="Conductor", role=_ROLE_CONDUCTOR,
                       text=ruling.reason, verdict=ruling.directive,
                       data={"reasoning": ruling.reasoning, "layer": ruling.layer,
                             "operation": repair_operation(ruling)})


# --------------------------------------------------------------------------- #
# The bounded arbitration — pure control flow, LLM injected via debate_fn /     #
# rule_fn. ALWAYS terminates: the two no-debate branches return immediately,    #
# and the debate branch is capped by max_rounds with a guaranteed final ruling. #
# --------------------------------------------------------------------------- #

# Injected providers: given the speaker + running transcript, the next debate turn;
# and given the full transcript, the Conductor's ruling. (Context is bound by the
# real implementations, so these signatures stay minimal — as with the composers.)
type DebateFn = Callable[[Critic, list[tuple[str, str]]], DebateTurn]
type RuleFn = Callable[[list[tuple[str, str]]], ConductorRuling]


def _forced_revise_ruling(ustad: UstadVerdict) -> ConductorRuling:
    """Code's ruling when the piece is illegal — no debate, legality is non-negotiable."""
    first = ustad.violations[0] if ustad.violations else None
    return ConductorRuling(
        directive="revise",
        operation="regenerate_lead" if first and first.layer == "lead" else "regenerate_riff",
        layer=first.layer if first else None,
        reason=f"Illegal in the raga — {first.reason}" if first else "Illegal in the raga.",
        reasoning="Legality is non-negotiable; code forces the revise with no debate.")


def _accept_ruling() -> ConductorRuling:
    return ConductorRuling(
        directive="accept",
        reason="Legal, and both Rasik and the Producer find it sound — nothing to arbitrate.",
        reasoning="Both aesthetic critics are satisfied; there is no conflict to debate.")


def arbitrate(ustad: UstadVerdict, rasik: RasikVerdict, producer: ProducerVerdict,
              comp: Composition, *, debate_fn: DebateFn, rule_fn: RuleFn,
              max_rounds: int = MAX_ROUNDS) -> tuple[ConductorRuling, list[DebateEvent]]:
    """Rule accept | revise on a critiqued composition, running the bounded debate only
    on a genuine (aesthetic) conflict.

    Always-terminating and bounded: the illegal and no-conflict branches return with no
    LLM call; the aesthetic branch steps the critics turn-by-turn for `max_rounds` turns
    (Rasik opens, Producer answers, alternate) and the Conductor ALWAYS rules at the cap.
    `debate_fn` and `rule_fn` are injected so the whole flow is tested with no LLM.
    """
    if max_rounds < 1:
        raise ValueError("max_rounds must be at least 1")

    events = [_system_event(
        f"Conductor reviews the verdicts — Ustad: {ustad.verdict}; "
        f"Rasik: {_scores_str(rasik)}; Producer: {_producer_scores_str(producer)}.")]
    conflict = detect_conflict(ustad, rasik, producer)

    if conflict is Conflict.FORCED_REVISE:
        events.append(_system_event(
            "Illegal — legality is non-negotiable, so a revise is forced without debate."))
        ruling = _forced_revise_ruling(ustad)
        events.append(_ruling_event(ruling))
        return ruling, events

    if conflict is Conflict.NONE:
        ruling = _accept_ruling()
        events.append(_ruling_event(ruling))
        return ruling, events

    # AESTHETIC conflict -> the bounded debate (the money moment).
    events.append(_system_event(
        f"Legal, but flagged ({_flagged(rasik, producer)}) — opening a bounded "
        f"Rasik vs Producer debate ({max_rounds} turns)."))
    transcript: list[tuple[str, str]] = []
    speakers = itertools.cycle(_DEBATE_ORDER)  # Rasik opens, then alternate with the Producer
    for round_no in range(1, max_rounds + 1):
        critic = next(speakers)
        turn = debate_fn(critic, list(transcript))
        transcript.append((critic.value, turn.argument))
        events.append(_debate_event(critic, turn, round_no))

    ruling = rule_fn(list(transcript))
    events.append(_ruling_event(ruling))
    return ruling, events


# --------------------------------------------------------------------------- #
# The real (LLM-backed) arbiter. Holds one crew + the debate context across the #
# turns and the ruling; exposes .debate / .rule as the injected fns.           #
# --------------------------------------------------------------------------- #

def _parse(output: Any, model: type[BaseModel]) -> Any:
    parsed = getattr(output, "pydantic", None)
    if isinstance(parsed, model):
        return parsed
    raw = getattr(output, "raw", None)
    try:
        return model.model_validate_json(raw) if raw else None
    except ValidationError:
        return None


class _DebateContext:
    """The debate's constant inputs (the three verdicts, the flagged weaknesses, the
    voices), rendered ONCE; only the speaker, turn number and transcript change per turn.
    Ustad's legality is shown as a settled FACT both debaters can cite — it does not
    debate. Pure."""

    def __init__(self, ustad: UstadVerdict, rasik: RasikVerdict, producer: ProducerVerdict,
                 comp: Composition, *, max_turns: int) -> None:
        self._static: dict[str, Any] = {
            "max_turns": max_turns,
            "ustad_summary": _render_ustad_summary(ustad),
            "rasik_summary": _render_rasik_summary(rasik),
            "producer_summary": _render_producer_summary(producer),
            "flagged": _flagged(rasik, producer),
            "raga": comp.raga,
            "voices": _render_voices(comp),
            "lead_line": _render_lead_line(comp),
        }

    def turn_inputs(self, critic: Critic, turn_no: int,
                    transcript: list[tuple[str, str]]) -> dict[str, Any]:
        return {**self._static, "critic": critic.value, "turn_no": turn_no,
                "transcript": _render_transcript(transcript), "output_schema": _DEBATE_SCHEMA}

    def rule_inputs(self, transcript: list[tuple[str, str]]) -> dict[str, Any]:
        return {**self._static, "transcript": _render_transcript(transcript),
                "operations": _OPERATIONS_BRIEF, "output_schema": _RULING_SCHEMA}


class _ConductorCrew:
    """Runs a debate turn (as the named critic) or the Conductor's ruling as an
    isolated single-agent crew. We own the loop, so each is an explicit call with the
    shared state injected. Config is read once at construction."""

    def __init__(self) -> None:
        config_dir = Path(__file__).parent / "config"
        self._agents = yaml.safe_load((config_dir / "agents.yaml").read_text())
        self._tasks = yaml.safe_load((config_dir / "tasks.yaml").read_text())

    def debate_turn(self, critic: Critic, inputs: dict[str, Any]) -> DebateTurn:
        agent = Agent(config=self._agents[critic.config_key], llm=critic_llm(),
                      allow_delegation=False, max_iter=CRITIC_MAX_ITER,
                      max_retry_limit=AGENT_RETRY_LIMIT, verbose=False)
        task = Task(config=self._tasks["debate_turn"], agent=agent, output_pydantic=DebateTurn)
        result = Crew(agents=[agent], tasks=[task], process=Process.sequential,
                      verbose=False).kickoff(inputs=inputs)
        turn = _parse(result, DebateTurn)
        if turn is None:
            raise ValueError(f"critic {critic.value} returned no parseable DebateTurn")
        return turn

    def rule(self, inputs: dict[str, Any]) -> ConductorRuling:
        agent = Agent(config=self._agents["conductor"], llm=conductor_llm(),
                      allow_delegation=False, max_iter=CRITIC_MAX_ITER,
                      max_retry_limit=AGENT_RETRY_LIMIT, verbose=False)
        task = Task(config=self._tasks["arbitrate"], agent=agent, output_pydantic=ConductorRuling)
        result = Crew(agents=[agent], tasks=[task], process=Process.sequential,
                      verbose=False).kickoff(inputs=inputs)
        ruling = _parse(result, ConductorRuling)
        if ruling is None:
            raise ValueError("Conductor returned no parseable ConductorRuling")
        return ruling


class _LLMArbiter:
    """The real debate_fn/rule_fn pair — one crew and one precomputed context, shared
    across the debate turns and the final ruling."""

    def __init__(self, ustad: UstadVerdict, rasik: RasikVerdict, producer: ProducerVerdict,
                 comp: Composition, *, max_turns: int) -> None:
        self._crew = _ConductorCrew()
        self._context = _DebateContext(ustad, rasik, producer, comp, max_turns=max_turns)

    def debate(self, critic: Critic, transcript: list[tuple[str, str]]) -> DebateTurn:
        turn_no = len(transcript) + 1
        return self._crew.debate_turn(critic, self._context.turn_inputs(critic, turn_no, transcript))

    def rule(self, transcript: list[tuple[str, str]]) -> ConductorRuling:
        return self._crew.rule(self._context.rule_inputs(transcript))


def conduct(ustad: UstadVerdict, rasik: RasikVerdict, producer: ProducerVerdict,
            comp: Composition, *,
            max_rounds: int = MAX_ROUNDS) -> tuple[ConductorRuling, list[DebateEvent]]:
    """Run the real (LLM-backed) arbitration: triage, the bounded Rasik vs Producer debate
    on a conflict, and the Conductor's final ruling."""
    arbiter = _LLMArbiter(ustad, rasik, producer, comp, max_turns=max_rounds)
    return arbitrate(ustad, rasik, producer, comp, debate_fn=arbiter.debate,
                     rule_fn=arbiter.rule, max_rounds=max_rounds)


# --------------------------------------------------------------------------- #
# Entry point — a single cheap live run on a PLANTED conflict: a legal piece    #
# Rasik marks weak on idiom (revise the lead) but the Producer finds it works   #
# as a song (ship it) — a genuine SOUL-vs-WORKS contest, so the debate fires and #
# the Conductor rules. Verdicts are constructed directly, so the only live cost  #
# is the debate + the ruling.                                                    #
# --------------------------------------------------------------------------- #

def _demo_case() -> tuple[UstadVerdict, RasikVerdict, ProducerVerdict, Composition]:
    from crew.contracts import ProducerScores, RasikScores
    from crew.rasik import _demo_composition
    comp = _demo_composition("darbari")           # legal drone + pakad-quoting lead
    ustad = UstadVerdict(verdict="legal", violations=[],
                         explanation="Every swara is legal in Darbari.")
    rasik = RasikVerdict(
        scores=RasikScores(pakad=4, idiom=2, rasa=3),   # idiom is weak (< 3) — a critical criterion
        notes=("The pakad is present, but the lead stays merely in-scale — it never leans "
               "into Darbari's andolan on komal ga and dha, so the raga's soul is thin."))
    producer = ProducerVerdict(
        scores=ProducerScores(structure=4, dynamics=4, climax=4, motif=4, hook=4,
                              balance=4, independence=4, mood_fit=4, repetition=4,
                              performance=4),
        notes="As a song it moves — the riff hooks, the arc builds; a lead revise risks the drive.")
    return ustad, rasik, producer, comp


def _run() -> None:
    from crew.contracts import EventStream
    ustad, rasik, producer, comp = _demo_case()
    stream = EventStream()
    ruling, events = conduct(ustad, rasik, producer, comp)
    for event in events:
        stream.emit(event)
    layer = f" layer={ruling.layer}" if ruling.layer else ""
    print(f"\nConductor ruling: {ruling.directive}{layer} — {ruling.reason}")


def main(argv: list[str]) -> int:
    load_env()  # entry point loads .env
    from contextlib import nullcontext

    from crew.tracing import traced, tracing_enabled
    ctx = traced("conductor-demo") if tracing_enabled() else nullcontext()
    with ctx:
        _run()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
