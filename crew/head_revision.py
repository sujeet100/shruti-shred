"""
ONE measured self-revision of the gat head — self-correction from code, applied to craft
(decided 2026-10-19 from the head-debate control; TALK.md "The rival added nothing").

The head is the piece's identity (it sounds on every sam), and its first draft reliably ignores a
fact the prompt states: ten drafts were told to dwell below Sa in Darbari, none spent more than 19%
there. What moved them was a MEASUREMENT of their own draft, with or without a rival composer. So
after the head passes its checks, code measures it against the raga's facts (`head_report`); when
a fact is missed, the composer sees its head beside the measurements and may revise ONCE. Code
keeps the revision only when it is still a sound head (the same hard checks), keeps the head's
first note (the manjha, antara and amad are built to land on it), and fixes a missed fact without
missing one the draft met (`revision_kept`). Anything else — no change, a dead call, a traded
fault — keeps the draft. A head that meets every fact never reaches the model.

`revise_head_once` is pure control flow (the reviser is injected, so it is tested with no LLM);
`LLMHeadReviser` is the live one (the `revise_head` task).
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

import yaml

from crew.contracts import Arrangement, DebateEvent, EventType, HeadTurn, LeadPhrase
from crew.gat_verifier import CellChecks
from crew.head_report import head_findings, render_head_report, revision_kept, unmet

_AGENT = "Lead"


class HeadReviser(Protocol):
    """Shown its head and code's report on it, the composer keeps it or revises it once. `verify`
    is the head's own verification — the reviser's guardrail holds a revision to it, so a fault the
    keep rule would refuse is sent back for the retry instead of costing the whole revision."""

    def __call__(self, arr: Arrangement, head: LeadPhrase, report: str,
                 verify: Callable[[LeadPhrase], CellChecks]) -> HeadTurn: ...


def revise_head_once(arr: Arrangement, head: LeadPhrase, *, verify: Callable[[LeadPhrase], CellChecks],
                     reviser: HeadReviser, events: list[DebateEvent]) -> LeadPhrase:
    """The head that plays: the draft, or its one revision when code keeps it. Appends one event
    whenever the reviser is asked (what was missed, what it did, kept or not, and why)."""
    draft = head_findings(head, arr.raga, arr.bpm)
    missed = unmet(draft)
    if not missed:
        return head
    try:
        turn = reviser(arr, head, render_head_report(draft), verify)
    except Exception as exc:  # noqa: BLE001 — LIVE SAFETY: the draft is a sound head; keep it
        events.append(_event(missed, kept=False, why=f"the revision call failed ({exc})"))
        return head
    why = _refusal(head, turn, verify, draft, arr)
    events.append(_event(missed, kept=why is None, why=why or "fixed a missed fact, broke none",
                         argument=turn.argument, revised=turn.head if turn.changed else None))
    return turn.head if why is None else head


def _refusal(draft: LeadPhrase, turn: HeadTurn, verify: Callable[[LeadPhrase], CellChecks],
             draft_findings: list, arr: Arrangement) -> str | None:
    """Why the revision is NOT kept, or None when it is."""
    if not turn.changed:
        return "the composer kept its draft"
    hard = list(verify(turn.head).hard)
    if hard:
        return f"the revision fails the head's checks: {'; '.join(hard)}"
    if _first(turn.head) != _first(draft):
        return "the revision moved the head's first note, which the other gat parts land on"
    if not revision_kept(draft_findings, head_findings(turn.head, arr.raga, arr.bpm)):
        return "the revision traded one missed fact for another (or fixed none)"
    return None


def _first(head: LeadPhrase) -> tuple[str, int] | None:
    return next(((n.swara, n.oct) for n in head.notes if not n.rest), None)


def _event(missed: list, *, kept: bool, why: str, argument: str = "",
           revised: LeadPhrase | None = None) -> DebateEvent:
    names = ", ".join(f.name for f in missed)
    return DebateEvent(
        type=EventType.INFO, agent=_AGENT, role="generator",
        text=f"head self-revision ({names} missed): {'revision kept' if kept else 'draft kept'} — {why}",
        data={"head_revision": True, "missed": [f.name for f in missed], "kept": kept, "why": why,
              "argument": argument, "revised": [n.swara for n in revised.notes] if revised else None})


# --------------------------------------------------------------------------- #
# The live reviser.                                                           #
# --------------------------------------------------------------------------- #

def head_turn_guardrail(arr: Arrangement, verify: Callable[[LeadPhrase], CellChecks] | None = None,
                        first: tuple[str, int] | None = None):
    """(True, HeadTurn) or (False, the faults): the head answers to the hard lines of any gat head —
    one avartan exactly, legal swaras in their legal direction, the head's hard checks. With
    `verify` (the production revision) it answers to the head's FULL verification instead — the
    same lines `revise_head_once` keeps it by — and, with `first`, keeps the head's first note.
    (2026-10-19, the first live revision: the composer fixed the register but ended on Ni; the old
    guardrail never checked the ending, so the revision was thrown away instead of repaired.)"""
    from crew.lead import _head_checks, phrase_grammar_error
    from gats import frame_for_bpm
    cycle, frame = arr.beats_per_bar, frame_for_bpm(arr.bpm)

    def guardrail(output: Any):
        turn = _parsed(output)
        if turn is None:
            return (False, "Return a single valid HeadTurn JSON object and nothing else.")
        filled = sum(n.dur for n in turn.head.notes)
        errors = [f"the head fills {filled:g} beats; it must fill exactly {cycle:g}"] if abs(filled - cycle) > 1e-6 else []
        grammar = phrase_grammar_error(turn.head, arr.raga)
        errors += [grammar] if grammar else []
        checks = verify(turn.head) if verify is not None else _head_checks(turn.head, cycle_beats=cycle, frame=frame,
                                                                           raga=arr.raga)
        errors += list(checks.hard)
        if first is not None and turn.changed and _first(turn.head) != first:
            errors.append(f"keep the head's first note ({first[0]}, octave {first[1]}): the other gat parts land on it")
        return (False, "; ".join(errors) + ". Fix and resend.") if errors else (True, turn)
    guardrail.__annotations__["return"] = tuple[bool, Any]
    return guardrail


def _parsed(output: Any) -> HeadTurn | None:
    parsed = getattr(output, "pydantic", None)
    if isinstance(parsed, HeadTurn):
        return parsed
    raw = getattr(output, "raw", None)
    try:
        return HeadTurn.model_validate_json(raw) if raw else None
    except ValueError:
        return None


def revise_inputs(arr: Arrangement, approach: str, your_head: str, *, round_: int = 1,
                  rounds: int = 1) -> dict[str, Any]:
    """The `revise_head` task's inputs — shared by the production pass and the debate's control."""
    from crew.user_request import render_request
    from crew.lead import _render_bol_frame, _render_raga_facts, phrase_schema
    from gats import frame_for_bpm
    from talas import TALAS
    return {"raga_block": _render_raga_facts(arr.raga, arr.bpm), "bpm": arr.bpm,
            "tala": TALAS[arr.tala]["display"], "cycle_beats": f"{arr.beats_per_bar:g}",
            "bol_frame": _render_bol_frame(frame_for_bpm(arr.bpm)), "user_request": render_request(arr.request),
            "output_schema": phrase_schema(), "approach": approach, "your_head": your_head,
            "round": round_, "rounds": rounds}


def _config(name: str) -> dict[str, Any]:
    return yaml.safe_load((Path(__file__).parent / "config" / name).read_text())


def render_your_head(head: LeadPhrase, report: str) -> str:
    from crew.anchor import lead_tokens
    return f"  notes: {lead_tokens(head.notes)}\n  measured against the raga's facts:\n{report}"


class LLMHeadReviser:
    """The live reviser: the head's own composer (`agent_key`), one `revise_head` call."""

    def __init__(self, agent_key: str = "composer") -> None:
        self._agent_key = agent_key

    def __call__(self, arr: Arrangement, head: LeadPhrase, report: str,
                 verify: Callable[[LeadPhrase], CellChecks]) -> HeadTurn:
        from crewai import Agent, Crew, Process, Task

        from crew.config import (AGENT_RETRY_LIMIT, GENERATOR_MAX_ITER, GENERATOR_RETRIES, composer_llm,
                                 structured_output)
        approach = (f"the head's idea: {arr.seed_head.idea}" if arr.seed_head is not None
                    else "the gat head you wrote for this piece")
        agent = Agent(config=_config("agents.yaml")[self._agent_key], llm=composer_llm(),
                      allow_delegation=False, max_iter=GENERATOR_MAX_ITER, max_retry_limit=AGENT_RETRY_LIMIT,
                      verbose=False)
        task = Task(config=_config("tasks.yaml")["revise_head"], agent=agent, **structured_output(HeadTurn),
                    guardrail=head_turn_guardrail(arr, verify, _first(head)),
                    guardrail_max_retries=GENERATOR_RETRIES)
        crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)
        turn = _parsed(crew.kickoff(inputs=revise_inputs(arr, approach, render_your_head(head, report))))
        if turn is None:
            raise ValueError("the head revision returned no parseable HeadTurn")
        return turn
