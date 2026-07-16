"""
Interpreter (agent #1) — free-text query -> validated CompositionBrief.

The pattern on show: STRUCTURED EXTRACTION + VALIDATION AT THE BOUNDARY. The LLM
does only the fuzzy natural-language part (extract a RawIntent — what the user
said), and deterministic code (`resolve_brief`) validates it. It invents NOTHING:
the raga must be supported (boundary check), and everything the user didn't state
is left OPEN for the composers to decide. The Interpreter deliberately makes no
creative choices (subgenre, tempo, instrumentation) — that's the composers' job.

Entry point:  uv run python -m crew.interpreter "metal fusion in Malkauns, key of D"
"""

from __future__ import annotations

import sys

from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from crew.config import AGENT_RETRY_LIMIT, extractor_llm, load_env
from crew.contracts import (
    CompositionBrief,
    DebateEvent,
    EventStream,
    EventType,
    RawIntent,
    resolve_brief,
)


@CrewBase
class InterpreterCrew:
    """A one-agent crew that extracts a RawIntent from the user's query."""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def interpreter(self) -> Agent:
        return Agent(config=self.agents_config["interpreter"], llm=extractor_llm(),
                     max_retry_limit=AGENT_RETRY_LIMIT, verbose=False)

    @task
    def interpret_query(self) -> Task:
        return Task(config=self.tasks_config["interpret_query"],
                    agent=self.interpreter(), output_pydantic=RawIntent)

    @crew
    def crew(self) -> Crew:
        return Crew(agents=self.agents, tasks=self.tasks, process=Process.sequential, verbose=False)


def _extract_intent(query: str) -> RawIntent:
    """Run the LLM crew and coerce its output to a RawIntent (defensively)."""
    result = InterpreterCrew().crew().kickoff(inputs={"query": query})
    if getattr(result, "pydantic", None) is not None:
        return result.pydantic
    return RawIntent.model_validate_json(result.raw)


def _fmt_brief(b: CompositionBrief) -> str:
    """Render a brief showing what's fixed vs. left OPEN for the composers."""
    parts = [f"raga={b.raga}" if b.raga else "raga=OPEN"]
    parts.append(f"key={b.key}(Sa={b.sa})" if b.key else "key=OPEN")
    parts.append(f"subgenre={b.subgenre}" if b.subgenre else "subgenre=OPEN")
    parts.append(f"bpm={b.bpm}" if b.bpm else "bpm=OPEN")
    parts.append(f"instruments={b.instruments}" if b.instruments else "instruments=OPEN")
    if b.mood:
        parts.append(f"mood={b.mood}")
    return " | ".join(parts)


def interpret(query: str) -> tuple[CompositionBrief, list[DebateEvent]]:
    """Query -> (brief, events). Always succeeds — nothing is required of the user.

    Emits INFO events for what was heard, any extraction notes, and the resolved
    brief with unstated dimensions shown as OPEN (the composers decide those,
    including the raga itself when the user only gave a mood).
    """
    intent = _extract_intent(query)
    brief = resolve_brief(intent)

    events: list[DebateEvent] = [DebateEvent(
        type=EventType.INFO, agent="Interpreter", role="system",
        text=f"heard: {intent.model_dump(exclude_none=True)}")]
    for note in brief.notes:
        events.append(DebateEvent(type=EventType.INFO, agent="Interpreter",
                                  role="system", text=f"note: {note}"))
    events.append(DebateEvent(type=EventType.INFO, agent="Interpreter",
                              role="system", text=f"brief: {_fmt_brief(brief)}"))
    return brief, events


def main(argv: list[str]) -> int:
    load_env()  # entry point loads .env
    query = " ".join(argv) or "Generate a metal raag fusion in Malkauns, in the key of D"
    stream = EventStream()
    _, events = interpret(query)
    for event in events:
        stream.emit(event)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
