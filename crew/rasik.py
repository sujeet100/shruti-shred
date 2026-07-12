"""
Rasik (agent #5, finishing step 5) — the TASTE critic.

The pattern on show: LLM-AS-JUDGE, and the discipline it needs. This is the
deliberate OPPOSITE of Ustad. Legality is a fact, so code owns Ustad's verdict; but
taste — is the raga's soul present, does the line move idiomatically, does it serve
the rasa — is NOT checkable, so here the model genuinely judges. Rasik owns exactly
ONE dimension: RAGA AUTHENTICITY (the uniquely Hindustani questions). Whether the
piece works AS A SONG — structure, motif, dynamics, arrangement — is the Producer's
job, deliberately kept out of Rasik so each critic owns a sharp responsibility.
LLM judges are biased (verbosity, gestalt "vibe" scoring, self-preference), and the
fix is not to take the pen away but to DISCIPLINE the judgment:

  * a FIXED 1-5 rubric with three named authenticity criteria (a bounded scale beats a vibe number);
  * scores GROUNDED in the encoded pakad/chalan/rasa facts — criteria, not vibes;
  * a code-computed pakad hint handed to the judge so its pakad score is anchored;
  * a justification required per criterion (reasoning FIRST, then the numbers).

(Rasik scores ONE composition, so the position-swap countermeasure — for A/B
comparisons — does not apply here; it belongs to the Conductor's later tie-breaks.)

Layering follows the repo's pure-core / imperative-shell split:
  * pure       — `assess` is control flow over an injected `judge_fn` (tested with no
                 LLM); the `_render_*`/`_pakad_presence` helpers turn facts into prompt
                 text and are unit-tested directly.
  * imperative — `_RasikCrew` / `_LLMJudge` make the actual Gemini call.

Entry point (a single, cheap live call on a tiny pakad-quoting composition):
  uv run python -m crew.rasik
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

import yaml
from crewai import Agent, Crew, Process, Task
from pydantic import ValidationError

from crew.config import CRITIC_MAX_ITER, critic_llm, load_env
from crew.contracts import (
    Composition,
    DebateEvent,
    EventType,
    RasikVerdict,
)
from raga import RAGAS

# DebateEvent role for a critic turn (shared with Ustad).
_ROLE_CRITIC: Final = "critic"

# The exact JSON shape we want back, injected as an input so CrewAI's {placeholder}
# interpolation never has to parse these literal braces.
_RUBRIC_SCHEMA: Final = """{
  "reasoning": "criterion by criterion (pakad, idiom, rasa): the evidence in the notes that justifies each score",
  "scores": {"pakad": 4, "idiom": 3, "rasa": 4},
  "notes": "a short 2-3 sentence critique a musician can act on"
}"""


# --------------------------------------------------------------------------- #
# Grounding: the deterministic pakad hint. Whether the raga's signature phrase #
# appears LITERALLY in the lead line is a fact code can compute — so we hand it #
# to the judge to anchor the pakad score (the judge still decides whether it is #
# EVOKED when not literal). "Ground the LLM in facts", made concrete.          #
# --------------------------------------------------------------------------- #

def _lead_swaras(comp: Composition) -> list[str]:
    """The primary lead voice's swaras, in time order (empty if there is no lead)."""
    for layer in comp.layers:
        if layer.role == "lead" and layer.notes:
            return [n.swara for n in sorted(layer.notes, key=lambda note: note.start)]
    return []


def _contains(sequence: list[str], phrase: list[str]) -> bool:
    """True iff `phrase` occurs as a contiguous run inside `sequence` (octave-agnostic)."""
    if not phrase or len(phrase) > len(sequence):
        return False
    return any(sequence[i:i + len(phrase)] == phrase
               for i in range(len(sequence) - len(phrase) + 1))


def pakad_presence(lead: list[str], raga: str) -> list[tuple[list[str], bool]]:
    """For each of the raga's pakad phrases, whether it appears literally in `lead`.

    Pure and testable. A literal contiguous match is the strong signal; a pakad may
    still be present in spirit without a literal quote, which is exactly the judgment
    left to Rasik — code supplies the fact, the LLM supplies the taste.
    """
    return [(phrase, _contains(lead, phrase)) for phrase in RAGAS[raga]["pakad"]]


# --------------------------------------------------------------------------- #
# Pure renderers: FACTS -> prompt text. Rasik needs the raga's full character   #
# (to judge idiom/rasa) plus the actual lead line (to judge pakad). The ensemble #
# view belongs to the PRODUCER now (balance/independence), not here. The single  #
# source of truth stays in raga.py; the prompt quotes it. (The composers render  #
# a similar raga block; a shared facts->prompt module is the natural refactor     #
# once step 6 settles — deferred to avoid churn now.)                            #
# --------------------------------------------------------------------------- #

def _render_raga_facts(raga: str) -> str:
    """The raga's encoded character — the criteria Rasik judges idiom and mood against."""
    r = RAGAS[raga]
    lines = [
        f"  {raga}: {r['display']} — {r['western_mode']}; allowed: {' '.join(r['allowed'])}",
        f"  aroha: {' '.join(r['aroha'])}   avaroha: {' '.join(r['avaroha'])}",
        f"  pakad: {' | '.join(' '.join(p) for p in r['pakad'])}",
        f"  chalan: {' | '.join(' '.join(p) for p in r['chalan'])}",
        f"  vadi {r['vadi']}, samvadi {r['samvadi']}; rasa/samay: {r['samay']}",
    ]
    if r.get("andolan"):
        lines.append(f"  andolan (swaras that oscillate — idiomatic): {' '.join(r['andolan'])}")
    return "\n".join(lines)


def _render_pakad_hint(comp: Composition) -> str:
    lead = _lead_swaras(comp)
    if not lead:
        return "  (no lead voice in this piece — score pakad from whatever melodic content exists)"
    lines = []
    for phrase, present in pakad_presence(lead, comp.raga):
        mark = "appears literally" if present else "not found literally (may still be evoked)"
        lines.append(f"  - {' '.join(phrase)}: {mark}")
    return "\n".join(lines)


def _swara_with_oct(swara: str, oct_: int) -> str:
    return swara if oct_ == 0 else f"{swara}({oct_:+d})"


def _render_lead_line(comp: Composition) -> str:
    for layer in comp.layers:
        if layer.role == "lead" and layer.notes:
            ordered = sorted(layer.notes, key=lambda note: note.start)
            return "  " + " ".join(_swara_with_oct(n.swara, n.oct) for n in ordered)
    return "  (no lead voice in this piece)"


# --------------------------------------------------------------------------- #
# Boundary parsing. output_pydantic targets RasikVerdict; this recovers it (or  #
# None) so the shell fails loud on an unparseable answer.                       #
# --------------------------------------------------------------------------- #

def _verdict_from_output(output: Any) -> RasikVerdict | None:
    parsed = getattr(output, "pydantic", None)
    if isinstance(parsed, RasikVerdict):
        return parsed
    raw = getattr(output, "raw", None)
    try:
        return RasikVerdict.model_validate_json(raw) if raw else None
    except ValidationError:
        return None


class _RasikCrew:
    """Runs ONE taste critique as an isolated, single-agent crew.

    No tool: unlike Ustad, Rasik judges from the prompt (the raga facts, the lead
    line, the pakad hint, the ensemble) — taste is not a lookup. Structured output is
    CrewAI's job (`output_pydantic=RasikVerdict`); the rubric's fixed scale is what
    disciplines the judgment. Config is read once at construction.
    """

    def __init__(self) -> None:
        config_dir = Path(__file__).parent / "config"
        self._agent_config = yaml.safe_load((config_dir / "agents.yaml").read_text())["rasik"]
        self._task_config = yaml.safe_load((config_dir / "tasks.yaml").read_text())["assess_taste"]

    def run(self, comp: Composition) -> RasikVerdict:
        agent = Agent(config=self._agent_config, llm=critic_llm(),
                      allow_delegation=False, max_iter=CRITIC_MAX_ITER, verbose=False)
        task = Task(config=self._task_config, agent=agent, output_pydantic=RasikVerdict)
        crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)
        result = crew.kickoff(inputs={
            "raga": comp.raga,
            "raga_facts": _render_raga_facts(comp.raga),
            "pakad_hint": _render_pakad_hint(comp),
            "lead_line": _render_lead_line(comp),
            "output_schema": _RUBRIC_SCHEMA,
        })
        verdict = _verdict_from_output(result)
        if verdict is None:
            raise ValueError("Rasik returned no parseable RasikVerdict")
        return verdict


# A judge provider: given the composition, return Rasik's verdict. Injected so
# `assess` is tested with no LLM.
type JudgeFn = Callable[[Composition], RasikVerdict]


class _LLMJudge:
    """The real (LLM-backed) `judge_fn` — holds the crew across calls."""

    def __init__(self) -> None:
        self._crew = _RasikCrew()

    def __call__(self, comp: Composition) -> RasikVerdict:
        return self._crew.run(comp)


# --------------------------------------------------------------------------- #
# The critique — thin, because the verdict is the LLM's (the contrast with      #
# Ustad, where code assembled the verdict). We stream the rubric as scores on   #
# the CRITIQUE event; the Conductor interprets a low score in step 6.           #
# --------------------------------------------------------------------------- #

def _verdict_event(verdict: RasikVerdict) -> DebateEvent:
    s = verdict.scores
    return DebateEvent(
        type=EventType.CRITIQUE, agent="Rasik", role=_ROLE_CRITIC,
        text=verdict.notes,
        scores={"pakad": float(s.pakad), "idiom": float(s.idiom), "rasa": float(s.rasa)},
        data={"reasoning": verdict.reasoning})


def assess(comp: Composition, *, judge_fn: JudgeFn) -> tuple[RasikVerdict, list[DebateEvent]]:
    """Judge a composition's taste on the fixed rubric and stream it as one CRITIQUE.

    The verdict IS the model's (taste is not checkable) — the shell only renders the
    grounded prompt, wraps the result, and emits the event. `judge_fn` is injected so
    this plumbing is tested with no LLM.
    """
    verdict = judge_fn(comp)
    return verdict, [_verdict_event(verdict)]


def critique_taste(comp: Composition) -> tuple[RasikVerdict, list[DebateEvent]]:
    """Run the real (LLM-backed) Rasik critique on a composition."""
    return assess(comp, judge_fn=_LLMJudge())


# --------------------------------------------------------------------------- #
# Entry point — a single cheap live call on a tiny composition whose lead QUOTES #
# the raga's pakad, so the grounding hint fires and Rasik has real music to score.#
# --------------------------------------------------------------------------- #

def _demo_composition(raga: str = "darbari") -> Composition:
    """A hand-built drone + lead piece whose lead line literally quotes the raga's
    pakad phrases — small, legal by construction, and enough for one cheap live score."""
    from crew.contracts import Layer, Note
    lead_swaras = [sw for phrase in RAGAS[raga]["pakad"] for sw in phrase]
    lead = [Note(swara=sw, oct=0, start=float(i), dur=1.0) for i, sw in enumerate(lead_swaras)]
    total = float(len(lead_swaras))
    drone = Note(swara=RAGAS[raga]["allowed"][0], oct=-2, start=0.0, dur=total)
    return Composition(
        raga=raga, sa=62, bpm=90, tala={"name": "teentaal", "beats_per_bar": 16.0},
        layers=[Layer(role="drone", notes=[drone]), Layer(role="lead", notes=lead)])


def _run() -> None:
    from crew.contracts import EventStream
    comp = _demo_composition()
    stream = EventStream()
    verdict, events = critique_taste(comp)
    for event in events:
        stream.emit(event)
    s = verdict.scores
    print(f"\nRasik scores: pakad={s.pakad} idiom={s.idiom} rasa={s.rasa}")
    print(f"  notes: {verdict.notes}")


def main(argv: list[str]) -> int:
    load_env()  # entry point loads .env
    from contextlib import nullcontext

    from crew.tracing import traced, tracing_enabled
    ctx = traced("rasik-demo") if tracing_enabled() else nullcontext()
    with ctx:
        _run()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
