"""
DRAFT OR REVISION? — the critique loop's decision, made by comparison (2026-10-18).

Measured across every recorded run (TALK.md "The Producer, measured across every run"), the
Producer's 1-5 scores could not steer the loop: 87% were 4 or 5, and after an edit the mean rose
as often as it fell. In the one blind ear test, the shipped revision was worse than the first draft
its own judge had already scored higher. So a revision no longer replaces the version before it on
the strength of a new score: the judge sees BOTH versions and is asked which is the better song,
twice with the order swapped (an LLM judge favours a position). The revision wins only if it is
chosen both times; a split, a "same", or a failed call keeps the earlier version — the original
wins ties.

Pure apart from the injected `choose` call; the live call is `_LLMChoose`.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

import yaml

from crew.contracts import Arrangement, Composition, DebateEvent, EventType, VersionChoice
from crew.producer import _render_ensemble, _render_lead_line, _render_riff_line, _render_sections, _render_subgenre
from crew.user_request import render_request

_TASK: Final = "compare_versions"
_AGENT: Final = "producer"

# (subgenre facts, timeline, request, version A, version B) -> "A" | "B" | "same"
type ChooseFn = Callable[[dict[str, Any]], str]


def render_version(comp: Composition, arr: Arrangement) -> str:
    """One version of the piece as the judge reads it: the main riff, the lead, the ensemble."""
    return (f"  THE MAIN RIFF:\n{_render_riff_line(comp, arr)}\n  THE LEAD:\n{_render_lead_line(comp)}\n"
            f"  THE ENSEMBLE:\n{_render_ensemble(comp)}")


def compare_inputs(first: Composition, second: Composition, arr: Arrangement) -> dict[str, Any]:
    """The comparison prompt's inputs, `first` shown as version A."""
    return {"subgenre_facts": _render_subgenre(arr), "sections": _render_sections(arr),
            "user_request": render_request(arr.request),
            "version_a": render_version(first, arr), "version_b": render_version(second, arr),
            "output_schema": '{"reasoning": "<what a listener hears in each>", "better": "A" | "B" | "same"}'}


def revision_wins(draft: Composition, revision: Composition, arr: Arrangement, *,
                  choose: ChooseFn) -> tuple[bool, list[DebateEvent]]:
    """True only when the judge prefers the revision in BOTH orders. A failed call counts as a
    vote for the draft, so the comparison can never ship an unjudged revision. Returns the result
    and one event saying what happened."""
    votes: list[str] = []
    for first, second, revision_label in ((draft, revision, "B"), (revision, draft, "A")):
        try:
            picked = choose(compare_inputs(first, second, arr))
        except Exception:  # noqa: BLE001 — LIVE SAFETY: an unjudged revision never ships
            picked = "failed"
        votes.append("revision" if picked == revision_label else ("same" if picked == "same" else "draft"))
    wins = votes == ["revision", "revision"]
    text = ("The revision is the better song in both orders — keeping it." if wins else
            f"Draft or revision? The judge said {votes[0]}, then {votes[1]} with the order swapped — "
            "keeping the earlier version.")
    return wins, [DebateEvent(type=EventType.VERDICT, agent="Producer", role="critic", text=text,
                              data={"votes": votes, "revision_kept": wins})]


class _LLMChoose:
    """The live `choose`: the Producer persona, one comparison task, a structured answer."""

    def __init__(self) -> None:
        config_dir = Path(__file__).parent / "config"
        self._agent_config = yaml.safe_load((config_dir / "agents.yaml").read_text())[_AGENT]
        self._task_config = yaml.safe_load((config_dir / "tasks.yaml").read_text())[_TASK]

    def __call__(self, inputs: dict[str, Any]) -> str:
        from crewai import Agent, Crew, Process, Task

        from crew.config import AGENT_RETRY_LIMIT, CRITIC_MAX_ITER, critic_llm, structured_output
        agent = Agent(config=self._agent_config, llm=critic_llm(), allow_delegation=False,
                      max_iter=CRITIC_MAX_ITER, max_retry_limit=AGENT_RETRY_LIMIT, verbose=False)
        task = Task(config=self._task_config, agent=agent, **structured_output(VersionChoice))
        result = Crew(agents=[agent], tasks=[task], process=Process.sequential,
                      verbose=False).kickoff(inputs=inputs)
        parsed = getattr(result, "pydantic", None)
        if not isinstance(parsed, VersionChoice):
            raw = getattr(result, "raw", "") or ""
            parsed = VersionChoice.model_validate_json(raw[raw.index("{"): raw.rindex("}") + 1])
        return parsed.better


def compare_versions(draft: Composition, revision: Composition,
                     arr: Arrangement) -> tuple[bool, list[DebateEvent]]:
    """The live comparison stage the Flow wires in."""
    return revision_wins(draft, revision, arr, choose=_LLMChoose())
