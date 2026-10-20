"""
The NOTES DEBATE's live players (`crew/notes_debate.py` is the pure loop): the sitarist on Gemini
(the Composer's model and effort), the guitarist on OpenAI's `gpt-6-luna` at medium effort (Sujit,
2026-10-19: a different model for one debater, so the two are not one mind twice). Every answer
passes a guardrail that runs the debate's own checks — an impossible rewrite goes back once with
the exact fault. Prompts: `crew/config/notes_debate.yaml`.
"""
from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any, Final

import yaml

from crew.notes_debate import (Critique, Players, RiffRevision, RiffRewrite, SitarRevision, SitarRewrite, Song,
                               riff_errors, riff_sections, sitar_errors)

GUITARIST_MODEL: Final = "openai/gpt-6-luna"
GUITARIST_EFFORT: Final = "medium"
TIMEOUT_S: Final = 360
RETRIES: Final = 1
_PATH: Final = Path(__file__).parent / "config" / "notes_debate.yaml"


@cache
def _config() -> dict:
    return yaml.safe_load(_PATH.read_text())


def _llm(player: str):
    from crew.config import build_llm, composer_llm
    if player == "guitarist":
        return build_llm(GUITARIST_MODEL, effort=GUITARIST_EFFORT, timeout_s=TIMEOUT_S)
    return composer_llm(timeout_s=TIMEOUT_S)


def _parsed(output: Any, model: type) -> Any:
    parsed = getattr(output, "pydantic", None)
    if isinstance(parsed, model):
        return parsed
    raw = getattr(output, "raw", None)
    try:
        return model.model_validate_json(raw) if raw else None
    except ValueError:
        return None


def _guard(model: type, check):
    """(True, answer) or (False, the faults): the answer parses and passes `check`."""
    def guardrail(output: Any):
        answer = _parsed(output, model)
        if answer is None:
            return (False, f"Return a single valid {model.__name__} JSON object and nothing else.")
        errors = check(answer)
        return (False, "; ".join(errors) + ". Fix exactly that and resend.") if errors else (True, answer)
    guardrail.__annotations__["return"] = tuple[bool, Any]
    return guardrail


def _run(player: str, task_key: str, model: type, check, inputs: dict[str, Any]) -> Any:
    from crewai import Agent, Crew, Process, Task

    from crew.config import AGENT_RETRY_LIMIT, structured_output
    config = _config()
    task = dict(config["tasks"][task_key])
    task["description"] = task["description"].replace("{common}", config["common"])
    agent = Agent(**config["agents"][player], llm=_llm(player), allow_delegation=False, max_iter=3,
                  max_retry_limit=AGENT_RETRY_LIMIT, verbose=False)
    crew = Crew(agents=[agent], tasks=[Task(config=task, agent=agent, **structured_output(model),
                                            guardrail=_guard(model, check), guardrail_max_retries=RETRIES)],
                process=Process.sequential, verbose=False)
    answer = _parsed(crew.kickoff(inputs=inputs), model)
    if answer is None:
        raise ValueError(f"the {player} returned no parseable {model.__name__}")
    return answer


_NO_CONCERN: Final = "(no specific concern was raised — find where the music is weakest)"


def _inputs(song: Song, piece: str, concern: str = "") -> dict[str, Any]:
    from crew.lead import _render_raga_facts, phrase_schema
    from crew.user_request import render_request
    from talas import TALAS
    arr = song.arr
    return {"raga_block": _render_raga_facts(arr.raga, arr.bpm), "bpm": arr.bpm, "tala": TALAS[arr.tala]["display"],
            "cycle_beats": f"{arr.beats_per_bar:g}", "user_request": render_request(arr.request), "piece": piece,
            "phrase_schema": phrase_schema(), "concern": concern or _NO_CONCERN,
            "riff_sections": ", ".join(str(s) for s in riff_sections(arr.rhythm_section))}



def players(song: Song, concern: str = "") -> Players:
    """The live players for `song`, each answer held to the debate's checks; `concern` is the
    reviewers' words that called the debate (empty for a standalone run)."""

    def propose_sitar(piece: str) -> SitarRewrite:
        return _run("sitarist", "propose_sitar", SitarRewrite,
                    lambda a: sitar_errors(song, a.part, a.phrase), _inputs(song, piece, concern))

    def propose_riff(piece: str) -> RiffRewrite:
        return _run("guitarist", "propose_riff", RiffRewrite,
                    lambda a: riff_errors(song, a.section, a.cycles)[1], _inputs(song, piece, concern))

    def critique(critic: str, piece: str, rewrite: str) -> Critique:
        return _run(critic, "critique", Critique, lambda a: [],
                    {**_inputs(song, piece, concern), "critic": critic, "rewrite": rewrite})

    def revise_sitar(piece: str, rewrite: str, said: str) -> SitarRevision:
        part = _part_of(rewrite)
        return _run("sitarist", "revise_sitar", SitarRevision,
                    lambda a: _revision_errors(a.decision, a.phrase, lambda p: sitar_errors(song, part, p)),
                    {**_inputs(song, piece, concern), "rewrite": rewrite, "critique": said})

    def revise_riff(piece: str, rewrite: str, said: str) -> RiffRevision:
        section = _section_of(rewrite)
        return _run("guitarist", "revise_riff", RiffRevision,
                    lambda a: _revision_errors(a.decision, a.cycles, lambda c: riff_errors(song, section, c)[1]),
                    {**_inputs(song, piece, concern), "rewrite": rewrite, "critique": said})

    return Players(propose_sitar, propose_riff, critique, revise_sitar, revise_riff)


def _revision_errors(decision: str, new, check) -> list[str]:
    if decision != "revise":
        return []
    if not new:
        return ["you chose to revise: write the revised notes in full"]
    return check(new)


def _part_of(rewrite: str) -> str:
    """The sitar part a `describe_sitar` text names ("rewrites the HEAD ...")."""
    return rewrite.split("rewrites the ", 1)[1].split(" ", 1)[0].lower()


def _section_of(rewrite: str) -> int:
    """The section a `describe_riff` text names ("the riff of SECTION 4.")."""
    return int(rewrite.split("SECTION ", 1)[1].split(".", 1)[0])
