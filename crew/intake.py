"""
Interpreter (agent #1) — free-text query -> validated CompositionBrief.

The pattern on show: STRUCTURED EXTRACTION + VALIDATION AT THE BOUNDARY. The LLM
does only the fuzzy natural-language part (extract a RawIntent — what the user
said), and deterministic code (`resolve_brief`) does the authoritative part
(validate against the raga/subgenre libraries, fill grounded defaults). The model
never gets to invent a bpm or an illegal raga — same "code decides the checkable"
discipline as the rest of the system, applied to intake.

Entry point:  uv run python -m crew.intake "metal fusion in Malkauns, key of D"
"""

from __future__ import annotations

import sys

from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from crew.config import extractor_llm, load_env
from crew.contracts import (
    CompositionBrief,
    DebateEvent,
    EventStream,
    EventType,
    RawIntent,
    resolve_brief,
)


@CrewBase
class IntakeCrew:
    """A one-agent crew that extracts a RawIntent from the user's query."""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def interpreter(self) -> Agent:
        return Agent(config=self.agents_config["interpreter"], llm=extractor_llm(), verbose=False)

    @task
    def interpret_query(self) -> Task:
        return Task(config=self.tasks_config["interpret_query"],
                    agent=self.interpreter(), output_pydantic=RawIntent)

    @crew
    def crew(self) -> Crew:
        return Crew(agents=self.agents, tasks=self.tasks, process=Process.sequential, verbose=False)


def _extract_intent(query: str) -> RawIntent:
    """Run the LLM crew and coerce its output to a RawIntent (defensively)."""
    result = IntakeCrew().crew().kickoff(inputs={"query": query})
    if getattr(result, "pydantic", None) is not None:
        return result.pydantic
    return RawIntent.model_validate_json(result.raw)


def interpret(query: str) -> tuple[CompositionBrief | None, list[str], list[DebateEvent]]:
    """Query -> (brief, problems, events). Never raises on an unresolvable brief.

    Emits INFO events describing what was heard and every grounded default, so the
    Interpreter surfaces its assumptions instead of blocking (DESIGN.md).
    """
    intent = _extract_intent(query)
    brief, problems = resolve_brief(intent)

    events: list[DebateEvent] = [DebateEvent(
        type=EventType.INFO, agent="Interpreter", role="system",
        text=f"heard: {intent.model_dump(exclude_none=True)}")]

    if brief is not None:
        for note in brief.assumptions:
            events.append(DebateEvent(type=EventType.INFO, agent="Interpreter",
                                      role="system", text=f"assumption: {note}"))
        events.append(DebateEvent(
            type=EventType.INFO, agent="Interpreter", role="system",
            text=(f"brief: {brief.raga} x {brief.subgenre} @ Sa={brief.sa} "
                  f"{brief.bpm}bpm, {', '.join(brief.instruments)}")))
    else:
        for problem in problems:
            events.append(DebateEvent(type=EventType.INFO, agent="Interpreter",
                                      role="system", text=f"cannot proceed: {problem}"))
    return brief, problems, events


def main(argv: list[str]) -> int:
    load_env()  # entry point loads .env
    query = " ".join(argv) or "Generate a metal raag fusion in Malkauns, in the key of D"
    stream = EventStream()
    _, problems, events = interpret(query)
    for event in events:
        stream.emit(event)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
