"""
The seed debate's model calls — the imperative edge of `crew/seed_debate.py`.

  * a DEBATE TURN is the `compose_seed` task with the debate block appended (`debate_seed` in
    tasks.yaml): the same `composer` persona, facts, schemas and hard rules it composed with, plus
    its own seed and the rival's, rendered with code's measurements. Its seed passes the same seed
    guardrail as a fresh one.
  * the SELECTOR is a short `select_seed` task on the `seed_judge` persona at the judge tier;
    its guardrail only checks the label names a candidate.

Lazy crewai imports keep the module importable with no key; the pure arms never import it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final

import yaml

from crew.composer import SeedContext, seed_errors
from crew.contracts import CompositionBrief, DebateTurn, SeedChoice, SongSeed
from crew.user_request import render_request

_CONFIG: Final = Path(__file__).parent / "config"


def _yaml(name: str) -> dict[str, Any]:
    return yaml.safe_load((_CONFIG / name).read_text())


def _parsed(output: Any, model: type) -> Any:
    parsed = getattr(output, "pydantic", None)
    if isinstance(parsed, model):
        return parsed
    raw = getattr(output, "raw", None)
    try:
        return model.model_validate_json(raw) if raw else None
    except ValueError:
        return None


def turn_guardrail(brief: CompositionBrief):
    """(True, DebateTurn) or (False, the faults): the revised seed answers to the seed's hard lines."""
    def guardrail(output: Any):
        turn = _parsed(output, DebateTurn)
        if turn is None:
            return (False, "Return a single valid DebateTurn JSON object and nothing else.")
        errors = seed_errors(turn.seed, brief)
        return (False, "; ".join(errors) + ". Fix and resend.") if errors else (True, turn)
    guardrail.__annotations__["return"] = tuple[bool, Any]
    return guardrail


def choice_guardrail(count: int):
    """(True, SeedChoice) or (False, why): the choice must name one of the `count` candidates."""
    def guardrail(output: Any):
        choice = _parsed(output, SeedChoice)
        if choice is None or not 1 <= choice.choice <= count:
            return (False, f"Return a SeedChoice whose choice is a label from 1 to {count}.")
        return (True, choice)
    guardrail.__annotations__["return"] = tuple[bool, Any]
    return guardrail


def _debate_task_config() -> dict[str, Any]:
    """`compose_seed` with the debate block appended and the turn's expected output."""
    tasks = _yaml("tasks.yaml")
    seed, block = tasks["compose_seed"], tasks["debate_seed"]
    return {**seed, "description": seed["description"] + block["addendum"],
            "expected_output": block["expected_output"]}


def _run(agent_key: str, llm: Any, task_config: dict[str, Any], model: type, guardrail: Any,
         retries: int, inputs: dict[str, Any]) -> Any:
    from crewai import Agent, Crew, Process, Task

    from crew.config import AGENT_RETRY_LIMIT, COMPOSER_MAX_ITER, structured_output
    agent = Agent(config=_yaml("agents.yaml")[agent_key], llm=llm, allow_delegation=False,
                  max_iter=COMPOSER_MAX_ITER, max_retry_limit=AGENT_RETRY_LIMIT, verbose=False)
    task = Task(config=task_config, agent=agent, **structured_output(model), guardrail=guardrail,
                guardrail_max_retries=retries)
    crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)
    result = _parsed(crew.kickoff(inputs=inputs), model)
    if result is None:
        raise ValueError(f"the {agent_key} returned no parseable {model.__name__}")
    return result


def llm_turn(brief: CompositionBrief, own: SongSeed, rival: SongSeed, both: str) -> DebateTurn:
    """One composer's debate turn, live."""
    from crew.config import SEED_RETRIES, composer_llm
    inputs = {**SeedContext(brief).inputs(), "debate": both}
    return _run("composer", composer_llm(), _debate_task_config(), DebateTurn,
                turn_guardrail(brief), SEED_RETRIES, inputs)


def llm_select(brief: CompositionBrief, candidates: str, count: int) -> SeedChoice:
    """The selector's choice, live."""
    from crew.config import critic_llm
    inputs = {"user_request": render_request(brief.request), "candidates": candidates,
              "count": count}
    return _run("seed_judge", critic_llm(), _yaml("tasks.yaml")["select_seed"], SeedChoice,
                choice_guardrail(count), 1, inputs)


def llm_seed(brief: CompositionBrief, approach: str) -> SongSeed:
    """A fresh seed, live, nudged by `approach`."""
    from crew.composer import _LLMSeed
    return _LLMSeed()(brief, approach)
