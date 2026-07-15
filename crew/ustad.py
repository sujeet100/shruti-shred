"""
Ustad (agent #4, step 5) — the LEGALITY critic.

The pattern on show: CODE DECIDES THE CHECKABLE, THE LLM NARRATES IT. Whether a
composition stays inside its raga is a grammar fact, not a matter of taste, so the
deterministic `raga.validate_composition` owns the verdict — the LLM never does.
Ustad's only job is to CALL that check (handed to him as a visible tool) and turn
its dry list of violations into a musician's explanation. This is why the type split
matters: his LLM output (`UstadNarration`) has no verdict field it *could* fill; the
shell pairs his explanation with the tool's authoritative result to assemble the
`UstadVerdict`, so the headline can never be a hallucination.

`validate_composition` is thus used the two ways CLAUDE.md prescribes: as the hard
guardrail on generator output (already wired in the generators), and — here — as a
TOOL Ustad calls mid-reasoning so he can *explain* a violation, not just flag it.

Layering follows the repo's pure-core / imperative-shell split:
  * pure       — `assess` is control flow over an injected `judge_fn` (tested with
                 no LLM); the `_render_*` helpers turn facts into prompt text; the
                 verdict is derived from `validate_composition` in code.
  * imperative — `_UstadCrew` / `_LLMJudge` make the actual Gemini call and bind the
                 validator tool to the piece under review.

Entry point (a single, cheap live critic call on a tiny planted composition):
  uv run python -m crew.ustad
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

import yaml
from crewai import Agent, Crew, Process, Task
from crewai.tools import BaseTool
from pydantic import BaseModel, ValidationError

from crew.config import CRITIC_MAX_ITER, critic_llm, load_env
from crew.contracts import (
    Composition,
    DebateEvent,
    EventType,
    UstadNarration,
    UstadVerdict,
    Violation,
)
from raga import RAGAS, SWARAS, validate_composition

# DebateEvent role for a critic turn (the others: "composer", "system", ...).
_ROLE_CRITIC: Final = "critic"

# The exact JSON shape we want back, injected as an input so CrewAI's {placeholder}
# interpolation never has to parse these literal braces. Note: no verdict field —
# Ustad explains, the tool decides.
_NARRATION_SCHEMA: Final = """{
  "reasoning": "what the validate_composition tool returned — how many violations and in which voices",
  "explanation": "a short musician's account: name any illegal swara and its voice and what the raga allows instead; or confirm the piece is clean"
}"""


# --------------------------------------------------------------------------- #
# The tool: a THIN adapter over the pure core. The real logic and its tests    #
# live in src/raga.py; this just binds the piece under review and hands the    #
# violations back to Ustad. Deterministic -> no cache (a zero-arg call must not #
# return a PRIOR composition's cached result). Returns a dict, not prose.       #
# --------------------------------------------------------------------------- #

class _ValidateInput(BaseModel):
    """No arguments: the tool validates the composition bound at construction.
    Ustad just calls it to SEE the grammar violations for the piece under review."""


class ValidateCompositionTool(BaseTool):
    """`validate_composition` as an agent tool — checks the bound composition against
    its raga's grammar and returns the violations (empty == fully legal)."""

    name: str = "validate_composition"
    description: str = (
        "Check the composition under review against its raga's grammar. Takes no "
        "arguments. Returns {'violations': [...]} — one entry per illegal note, each "
        "giving the voice (layer), the offending swara, its start beat, what it is "
        "(note / grace / meend-target), and why it is illegal (including the swaras "
        "the raga allows). An empty list means the piece is fully legal. This is the "
        "authoritative legality check — trust it over your ear."
    )
    args_schema: type[BaseModel] = _ValidateInput
    composition: dict  # the piece under review, bound at construction

    def _run(self, *args: Any, **kwargs: Any) -> dict:
        return {"violations": validate_composition(self.composition)}


def _never_cache(*args: Any, **kwargs: Any) -> bool:
    """Cache policy for the validator tool: never. A module-level function (not a
    lambda) so pydantic can serialize the tool without warning."""
    return False


def _validator_tool(payload: dict) -> ValidateCompositionTool:
    """Build the validator tool bound to `payload`, with caching OFF: the call takes
    no args, so a cache would key every composition to the same (empty) key and hand
    back a stale verdict — exactly the bug no-cache prevents for a deterministic tool."""
    return ValidateCompositionTool(composition=payload, cache_function=_never_cache)


# --------------------------------------------------------------------------- #
# Pure renderers: FACTS -> prompt text. The single source of truth stays in    #
# raga.py; Ustad's prompt only quotes it.                                      #
# --------------------------------------------------------------------------- #

def _render_raga_facts(raga: str) -> str:
    """The one fact Ustad needs to name what a raga allows instead of a foreign note."""
    r = RAGAS[raga]
    return f"  {raga}: {r['display']} — allowed swaras: {' '.join(r['allowed'])}"


def _render_composition_summary(comp: Composition) -> str:
    """A compact roster of the voices under review — enough to orient Ustad without
    dumping every note (the note-level detail comes THROUGH the tool, not the prompt)."""
    parts = []
    for layer in comp.layers:
        count = len(layer.notes) if layer.notes else len(layer.hits or [])
        unit = "notes" if layer.notes else "hits"
        parts.append(f"{layer.role} ({count} {unit})")
    return (f"  raga={comp.raga}, tala={comp.tala.get('name')}, {comp.bpm} bpm; "
            f"voices: {', '.join(parts)}")


# --------------------------------------------------------------------------- #
# Boundary parsing. output_pydantic already targets UstadNarration; this just  #
# recovers it (or None) so the shell can fail loud on an unparseable answer.    #
# --------------------------------------------------------------------------- #

def _narration_from_output(output: Any) -> UstadNarration | None:
    parsed = getattr(output, "pydantic", None)
    if isinstance(parsed, UstadNarration):
        return parsed
    raw = getattr(output, "raw", None)
    try:
        return UstadNarration.model_validate_json(raw) if raw else None
    except ValidationError:
        return None


class _UstadCrew:
    """Runs ONE legality critique as an isolated, single-agent crew.

    The validator tool is bound to the piece under review and handed to the agent, so
    Ustad discovers the violations by CALLING it (a visible tool step in the trace),
    not by inspecting a prompt dump. Structured output is CrewAI's job
    (`output_pydantic=UstadNarration`); there is no hand-rolled JSON parsing. Config
    is read once at construction.
    """

    def __init__(self) -> None:
        config_dir = Path(__file__).parent / "config"
        self._agent_config = yaml.safe_load((config_dir / "agents.yaml").read_text())["ustad"]
        self._task_config = yaml.safe_load((config_dir / "tasks.yaml").read_text())["assess_legality"]

    def run(self, comp: Composition, payload: dict) -> UstadNarration:
        agent = Agent(config=self._agent_config, llm=critic_llm(),
                      tools=[_validator_tool(payload)], allow_delegation=False,
                      max_iter=CRITIC_MAX_ITER, verbose=False)
        task = Task(config=self._task_config, agent=agent, output_pydantic=UstadNarration)
        crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)
        result = crew.kickoff(inputs={
            "raga": comp.raga,
            "raga_facts": _render_raga_facts(comp.raga),
            "composition_summary": _render_composition_summary(comp),
            "output_schema": _NARRATION_SCHEMA,
        })
        narration = _narration_from_output(result)
        if narration is None:
            raise ValueError("Ustad returned no parseable UstadNarration")
        return narration


# A judge provider: given the composition (and its render-payload for the tool),
# return Ustad's narration. Injected so `assess` is tested with no LLM.
type JudgeFn = Callable[[Composition, dict], UstadNarration]


class _LLMJudge:
    """The real (LLM-backed) `judge_fn` — holds the crew across calls."""

    def __init__(self) -> None:
        self._crew = _UstadCrew()

    def __call__(self, comp: Composition, payload: dict) -> UstadNarration:
        return self._crew.run(comp, payload)


# --------------------------------------------------------------------------- #
# The critique — pure. Code runs the authoritative check and OWNS the verdict; #
# the LLM only narrates. The type split (UstadNarration -> UstadVerdict) makes  #
# "code decides the checkable" structural, not merely a convention.            #
# --------------------------------------------------------------------------- #

def _verdict_event(verdict: UstadVerdict) -> DebateEvent:
    return DebateEvent(
        type=EventType.CRITIQUE, agent="Ustad", role=_ROLE_CRITIC,
        text=verdict.explanation, verdict=verdict.verdict,
        data={"violations": [v.model_dump() for v in verdict.violations],
              "reasoning": verdict.reasoning})


def assess(comp: Composition, *, judge_fn: JudgeFn) -> tuple[UstadVerdict, list[DebateEvent]]:
    """Judge a composition's raga-legality: the deterministic check decides, Ustad explains.

    Code runs `validate_composition` for the authoritative `verdict`/`violations`,
    then `judge_fn` supplies the human explanation (the real one runs the tool itself
    so its account is grounded in the same result). The two are assembled into an
    `UstadVerdict` and streamed as one CRITIQUE event. `judge_fn` is injected so this
    control flow is tested with no LLM.
    """
    payload = comp.model_dump(exclude_none=True)
    violations = [Violation(**v) for v in validate_composition(payload)]
    if violations:
        # A real violation to EXPLAIN — this is where the LLM (its ReAct tool call) earns its keep:
        # it calls validate_composition and narrates WHY the piece is illegal, in a musician's terms.
        narration = judge_fn(comp, payload)
        explanation, reasoning = narration.explanation, narration.reasoning
    else:
        # CLEAN piece: SKIP the LLM entirely (Sujit, 2026-07-16 — "do things programmatically instead
        # of the ReAct loop"). Code already OWNS the "legal" verdict, and a ReAct pass would only
        # re-state "it's clean" at the cost of a critic call. Since the generators' pitch guardrail
        # gates illegal notes before assembly, LEGAL is the common path — so this removes an LLM call
        # from almost every run. The pattern is intact: the model still narrates when there IS a
        # violation; it just doesn't narrate the absence of one.
        explanation = f"All notes sit inside {RAGAS[comp.raga]['display']} — the piece is legal in the raga."
        reasoning = "validate_composition returned no violations: every sounding swara is legal in the raga."
    verdict = UstadVerdict(
        verdict="illegal" if violations else "legal",
        violations=violations,
        explanation=explanation,
        reasoning=reasoning)
    return verdict, [_verdict_event(verdict)]


def critique_legality(comp: Composition) -> tuple[UstadVerdict, list[DebateEvent]]:
    """Run the real (LLM-backed) Ustad critique on a composition."""
    return assess(comp, judge_fn=_LLMJudge())


# --------------------------------------------------------------------------- #
# Entry point — a single cheap live call on a tiny planted composition, so the #
# confirmation costs ONE critic call, not a full generate-then-critique run.    #
# --------------------------------------------------------------------------- #

def _an_illegal_swara(raga: str) -> str:
    """A sargam symbol that is NOT legal in `raga` — for planting a known violation."""
    allowed = set(RAGAS[raga]["allowed"])
    return next(sw for sw in SWARAS if sw not in allowed)


def _demo_composition(raga: str = "bhairav") -> Composition:
    """A hand-built two-voice piece with ONE planted illegal note in the lead — small
    enough that critiquing it is a single, cheap live call. No LLM, no generators."""
    from crew.contracts import Layer, Note
    root = RAGAS[raga]["allowed"][0]          # Sa — always legal
    foreign = _an_illegal_swara(raga)         # a swara the raga forbids
    return Composition(
        raga=raga, sa=62, bpm=90, tala={"name": "teentaal", "beats_per_bar": 16.0},
        layers=[
            Layer(role="drone", notes=[Note(swara=root, oct=-2, start=0.0, dur=16.0)]),
            Layer(role="lead", notes=[
                Note(swara=root, oct=0, start=0.0, dur=1.0),
                Note(swara=foreign, oct=0, start=1.0, dur=1.0),   # the planted violation
            ]),
        ])


def _run() -> None:
    from crew.contracts import EventStream
    comp = _demo_composition()
    stream = EventStream()
    verdict, events = critique_legality(comp)
    for event in events:
        stream.emit(event)
    print(f"\nUstad verdict: {verdict.verdict} ({len(verdict.violations)} violation(s))")
    for v in verdict.violations:
        print(f"  - {v.layer}: {v.swara} @ beat {v.start_beat} ({v.kind})")


def main(argv: list[str]) -> int:
    load_env()  # entry point loads .env
    from contextlib import nullcontext

    from crew.tracing import traced, tracing_enabled
    ctx = traced("ustad-demo") if tracing_enabled() else nullcontext()
    with ctx:
        _run()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
