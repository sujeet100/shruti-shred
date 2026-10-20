"""
The SECOND LOOK — where two independent reviews meet (fan-out / fan-in, 2026-10-20).

Rasik (the raga) and the Producer (the song) judge the same frozen piece in PARALLEL, neither
seeing the other: when the Producer read Rasik's notes first, 30 of its 36 revision plans copied
Rasik almost word for word, so one critic's view was really two. Their findings meet here, and
only when they need to: if the Producer already asks for a revision, its plan stands (one edit a
round); if it accepts and Rasik flags a raga problem (a score at or below `RASIK_FLAG_SCORE`), the
Producer takes a second look — Rasik's notes beside its own first verdict — and decides whether a
listener would hear the problem. Its first-pass scores stand; only `decision` and `plan` can
change. A failed second look keeps the first verdict (live safety).

Layering: `fan_in` is pure over an injected `look_fn`; `_SecondLookCrew` makes the one call.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

import yaml
from crewai import Agent, Crew, Process, Task

from crew.config import AGENT_RETRY_LIMIT, CRITIC_MAX_ITER, critic_llm, structured_output
from crew.contracts import (
    Arrangement,
    Composition,
    DebateEvent,
    EventType,
    ProducerSecondLook,
    ProducerVerdict,
    RasikVerdict,
)
from crew.producer import _render_lead_line, _render_sections
from crew.user_request import render_request

RASIK_FLAG_SCORE: Final = 2                     # a raga score at or below this is a problem worth a look

_SCHEMA: Final = """{
  "reasoning": "a few sentences: would a listener hear Rasik's problem as something wrong or weak in this piece, and where",
  "decision": "accept",
  "plan": null
}
(On "revise", "plan" is {"voice": "lead", "sections": [2], "instruction": "the problem a listener hears and the effect you want", "preserve": ["the mukhada"]}.)"""


def rasik_flags(rasik: RasikVerdict) -> bool:
    """Did Rasik find a raga problem worth the Producer's second look? Pure."""
    s = rasik.scores
    return min(s.pakad, s.idiom, s.rasa) <= RASIK_FLAG_SCORE


def render_consultation(rasik: RasikVerdict) -> str:
    """Rasik's raga consultation as the Producer reads it on its second look. Pure."""
    s = rasik.scores
    lines = [f"  scores: pakad {s.pakad}, idiom {s.idiom}, rasa {s.rasa} (1-5) — {rasik.notes}"]
    lines += [f"  suggestion: section {x.section}: {x.change} ({x.why})" for x in rasik.suggestions]
    return "\n".join(lines)


def _render_own(producer: ProducerVerdict) -> str:
    plan = producer.plan
    tail = f" Your plan: {plan.voice}, sections {plan.sections}: {plan.instruction}" if plan else ""
    return f"  You decided: {producer.decision}. Your notes: {producer.notes}{tail}"


def second_look_inputs(comp: Composition, arr: Arrangement, producer: ProducerVerdict,
                       rasik: RasikVerdict) -> dict[str, Any]:
    """The reconsider_with_rasik prompt inputs. Pure."""
    return {"sections": _render_sections(arr), "lead_line": _render_lead_line(comp),
            "own_verdict": _render_own(producer), "consultation": render_consultation(rasik),
            "user_request": render_request(arr.request), "output_schema": _SCHEMA}


type LookFn = Callable[[Composition, Arrangement, ProducerVerdict, RasikVerdict], ProducerSecondLook]


def fan_in(comp: Composition, arr: Arrangement, producer: ProducerVerdict, rasik: RasikVerdict, *,
           look_fn: LookFn) -> tuple[ProducerVerdict, list[DebateEvent]]:
    """The two independent reviews, combined. Pure over `look_fn`."""
    if producer.decision == "revise" or not rasik_flags(rasik):
        return producer, []
    try:
        look = look_fn(comp, arr, producer, rasik)
    except Exception as exc:  # noqa: BLE001 — LIVE SAFETY: the first verdict stands
        return producer, [_event(f"second look skipped ({exc}) — the first verdict stands")]
    plan = look.plan if look.decision == "revise" else None
    merged = producer.model_copy(update={"decision": "revise" if plan else "accept", "plan": plan})
    said = (f"After reading Rasik: revise the {plan.voice} — {plan.instruction}" if plan
            else "After reading Rasik: still accept — " + look.reasoning)
    return merged, [_event(said, merged)]


def _event(text: str, verdict: ProducerVerdict | None = None) -> DebateEvent:
    data = ({"decision": verdict.decision, "plan": verdict.plan.model_dump() if verdict.plan else None,
             "second_look": True} if verdict else {"second_look": True})
    return DebateEvent(type=EventType.CRITIQUE, agent="Producer", role="critic", text=text,
                       verdict=verdict.decision if verdict else None, data=data)


class _SecondLookCrew:
    """ONE call: the Producer, its own verdict and Rasik's notes in view. Config read once."""

    def __init__(self) -> None:
        config_dir = Path(__file__).parent / "config"
        self._agent_config = yaml.safe_load((config_dir / "agents.yaml").read_text())["producer"]
        self._task_config = yaml.safe_load((config_dir / "tasks.yaml").read_text())["reconsider_with_rasik"]

    def __call__(self, comp: Composition, arr: Arrangement, producer: ProducerVerdict,
                 rasik: RasikVerdict) -> ProducerSecondLook:
        agent = Agent(config=self._agent_config, llm=critic_llm(), allow_delegation=False,
                      max_iter=CRITIC_MAX_ITER, max_retry_limit=AGENT_RETRY_LIMIT, verbose=False)
        task = Task(config=self._task_config, agent=agent, **structured_output(ProducerSecondLook))
        crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)
        result = crew.kickoff(inputs=second_look_inputs(comp, arr, producer, rasik))
        parsed = getattr(result, "pydantic", None)
        if isinstance(parsed, ProducerSecondLook):
            return parsed
        return ProducerSecondLook.model_validate_json(getattr(result, "raw", "") or "{}")


def second_look(comp: Composition, arr: Arrangement, producer: ProducerVerdict,
                rasik: RasikVerdict) -> tuple[ProducerVerdict, list[DebateEvent]]:
    """The real (LLM-backed) fan-in."""
    return fan_in(comp, arr, producer, rasik, look_fn=_SecondLookCrew())
