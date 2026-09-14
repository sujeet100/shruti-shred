"""
The ARRANGER (agent #8) — "do these two lines coexist?", the third question nobody asked.

The riff composer asks "is this a good metal riff?" and the lead composer asks "is this a
good raga line?". Both can answer yes while the two grind against each other, because
neither ever sees the other's finished performance: the riff is composed before the lead
exists, from the raga and the gat head, not from what the sitar actually sounds on beat 6.5.
This pass runs AFTER both are real and asks only the question they could not.

It is deliberately NOT a re-generation. Regenerating the riff against the melody would
destroy the hook every time the melody changed, so the arranger has LIMITED AUTHORITY: it
chooses, per clash, from a menu of legal local edits to ONE note. It cannot move an attack,
change the cell's rhythm, or touch a section it was not called on — the riff's identity
survives by construction rather than by asking an agent nicely to preserve it.

Three properties keep it safe to run live:

  * WHO MOVES is code (`repairs.right_of_way`) — the anchor's right-of-way rule, never a
    negotiation. Two agents each able to demand changes of the other is a loop with no
    referee.
  * WHAT IS LEGAL is code (`repairs.grind_repairs`) — every offered option is already
    raga-legal, so the agent chooses taste and only taste.
  * IT ALWAYS TERMINATES — one bounded pass, then a deterministic sweep damps whatever the
    agent left grinding. No organic convergence, and a failed or unparseable LLM call costs
    nothing but the fallback.

Cost follows the evidence: a section with no findings is never sent to the model, so a
clean piece spends nothing, and only the worst `_MAX_FINDINGS` clashes of a section are put
to the agent (the rest take the safest legal repair) so one prompt cannot grow without
bound.

Layering follows the repo's pure-core / imperative-shell split:
  * pure       — `arrange` is control flow over an injected `decide_fn` (tested with no LLM);
                 the menu, the repairs and their application are pure (`crew/repairs.py`).
  * imperative — `_ArrangerCrew` / `_LLMArranger` make the actual Gemini call.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Optional

import yaml
from crewai import Agent, Crew, Process, Task
from pydantic import ValidationError

from crew.coexistence import (
    CoexistenceReport,
    SectionCoexistence,
    coexistence_of,
    lead_notes_of,
    riff_notes_of,
)
from crew.config import AGENT_RETRY_LIMIT, CRITIC_MAX_ITER, critic_llm
from crew.contracts import (
    Arrangement,
    ArrangerDecision,
    DebateEvent,
    EventType,
    Layer,
)
from crew.repairs import (
    Repair,
    RepairKind,
    Yielder,
    apply_repairs,
    chase_repairs,
    grind_repairs,
    right_of_way,
    safest_repair,
)

_ROLE_ARRANGER: Final = "arranger"
# Clashes put to the agent per section, worst first. The rest take the safest legal repair:
# a prompt that grows with the damage would cost most exactly where the music is weakest.
_MAX_FINDINGS: Final = 8

_DECISION_SCHEMA: Final = """{
  "reasoning": "what the melody is doing in this section, and what the guitar should therefore be doing under it",
  "choices": [{"finding": 0, "repair": "damp", "reason": "the sitar holds komal ga here; the guitar should not argue with it"}]
}"""


@dataclass(frozen=True)
class Finding:
    """One clash as the agent sees it: a description, and the legal repairs on offer."""
    label: str
    riff_index: int
    lead_index: Optional[int]
    repairs: tuple[Repair, ...]

    def render(self, number: int) -> str:
        options = " | ".join(r.id for r in self.repairs)
        return f"  [{number}] {self.label}\n      repairs: {options}"


def _grind_label(grind, yielder: Yielder) -> str:
    what = "chord tone" if grind.from_chord else "root"
    return (f"beat {grind.beat:g}: the guitar's {what} {grind.riff_swara} sounds a harsh "
            f"interval under the {grind.stability.value} melody note {grind.lead_swara} "
            f"({yielder.value} gives way here)")


def _chase_label(chase) -> str:
    return (f"beat {chase.beat:g}: the guitar's root moves {chase.from_swara} -> "
            f"{chase.to_swara} while the melody is still moving (harmony chasing the tune)")


def _findings_for(section: SectionCoexistence, *, yielder: Yielder, raga: str,
                  riff_notes: list, lead_notes: list) -> list[Finding]:
    """This section's clashes as a menu, worst first — a grind under a HELD melody note
    outranks one under a merely stable note, and grinds outrank chases (a wrong pitch is
    heard before a restless root)."""
    findings = [
        Finding(label=_grind_label(g, yielder), riff_index=g.riff_index,
                lead_index=g.lead_index,
                repairs=tuple(grind_repairs(g, yielder=yielder, raga=raga,
                                            riff_notes=riff_notes, lead_notes=lead_notes)))
        for g in sorted(section.grinds, key=lambda g: g.stability.value)
    ]
    findings += [Finding(label=_chase_label(c), riff_index=c.riff_index, lead_index=None,
                         repairs=tuple(chase_repairs(c))) for c in section.chases]
    return findings


def _chosen_pairs(findings: list[Finding], picks: list[Repair]) -> list[tuple[int, Repair]]:
    """Pair each decided repair with the riff note it edits, dropping the KEEPs."""
    return [(f.riff_index, r) for f, r in zip(findings, picks) if r.kind is not RepairKind.KEEP]


def _lead_targets(findings: list[Finding]) -> dict[int, int]:
    """Which melody note a RESEAT_LEAD on each riff index moves."""
    return {f.riff_index: f.lead_index for f in findings if f.lead_index is not None}


# A decider: given a section's findings, return one repair per finding (same order).
# Injected so the whole pass is tested with no LLM.
type DecideFn = Callable[[SectionCoexistence, list[Finding]], list[Repair]]


def deterministic_decider(_: SectionCoexistence, findings: list[Finding]) -> list[Repair]:
    """Code's own answer — the least damaging legal repair for every clash. Used when no
    agent is wired, for the overflow past `_MAX_FINDINGS`, and as the terminator."""
    return [safest_repair(list(f.repairs)) for f in findings]


def _decide(section: SectionCoexistence, findings: list[Finding],
            decide_fn: DecideFn) -> list[Repair]:
    """The agent decides the worst `_MAX_FINDINGS`; code takes the tail. A decider that
    fails or answers short is topped up deterministically — never a stall."""
    head, tail = findings[:_MAX_FINDINGS], findings[_MAX_FINDINGS:]
    try:
        picks = list(decide_fn(section, head))
    except Exception:                                    # noqa: BLE001 — live safety
        picks = []
    picks = picks[:len(head)]
    picks += deterministic_decider(section, head[len(picks):])
    return picks + deterministic_decider(section, tail)


def _event(section: SectionCoexistence, findings: list[Finding],
           picks: list[Repair]) -> DebateEvent:
    applied = [f"{f.label.split(':')[0]} -> {r.id}" for f, r in zip(findings, picks)]
    return DebateEvent(
        type=EventType.CRITIQUE, agent="Arranger", role=_ROLE_ARRANGER,
        text=(f"section {section.index} ({section.kind}): {len(findings)} clash(es) between "
              f"the guitar and the melody, repaired."),
        data={"section": section.index, "repairs": applied})


def arrange(riff: Optional[Layer], leads: list[Layer], arr: Arrangement, *,
            decide_fn: DecideFn) -> tuple[Optional[Layer], list[Layer], list[DebateEvent]]:
    """Make the riff and the melody coexist: one bounded pass, then a deterministic sweep.

    Returns the repaired layers and the events for the stream. Runs BEFORE the bass and
    double-track derive from the riff, so the whole rhythm section inherits any repair.
    Pure control flow — `decide_fn` is the only thing that could call an LLM.
    """
    report = coexistence_of(riff, leads, arr)
    if report.clean:
        return riff, leads, []
    riff, leads, events = _pass(riff, leads, arr, report, decide_fn)
    return _sweep(riff, leads, arr) + (events,)


def _pass(riff: Optional[Layer], leads: list[Layer], arr: Arrangement,
          report: CoexistenceReport, decide_fn: DecideFn):
    """The agent's one pass over every flagged section."""
    events: list[DebateEvent] = []
    for section in report.flagged:
        findings = _findings_for(section, yielder=right_of_way(arr.sections[section.index],
                                                               arr.anchor),
                                 raga=arr.raga, riff_notes=riff_notes_of(riff),
                                 lead_notes=lead_notes_of(leads))
        if not findings:
            continue
        picks = _decide(section, findings, decide_fn)
        riff, leads = apply_repairs(riff, leads, _chosen_pairs(findings, picks),
                                    lead_targets=_lead_targets(findings))
        events.append(_event(section, findings, picks))
    return riff, leads, events


def _sweep(riff: Optional[Layer], leads: list[Layer], arr: Arrangement):
    """The terminator: whatever still grinds after the agent's pass is damped in code, so
    the pass cannot leave the piece worse than the old deterministic guard did."""
    report = coexistence_of(riff, leads, arr)
    if report.clean:
        return riff, leads
    left = [(g.riff_index, Repair(RepairKind.DAMP))
            for section in report.flagged for g in section.grinds]
    repaired, leads = apply_repairs(riff, leads, left)
    return repaired, leads


# --------------------------------------------------------------------------- #
# The imperative shell — the actual Gemini call.                               #
# --------------------------------------------------------------------------- #

def _decision_from_output(output: Any) -> ArrangerDecision | None:
    parsed = getattr(output, "pydantic", None)
    if isinstance(parsed, ArrangerDecision):
        return parsed
    raw = getattr(output, "raw", None)
    try:
        return ArrangerDecision.model_validate_json(raw) if raw else None
    except ValidationError:
        return None


def _picks_from_decision(decision: ArrangerDecision | None,
                         findings: list[Finding]) -> list[Repair]:
    """Map the agent's answer back onto the menu. An id it was never offered, a finding
    number that does not exist, or a finding it skipped all fall back to the safest legal
    repair — the menu is the authority, not the reply."""
    chosen: dict[int, Repair] = {}
    for choice in (decision.choices if decision else []):
        if choice.finding >= len(findings):
            continue
        offered = {r.id: r for r in findings[choice.finding].repairs}
        if choice.repair in offered:
            chosen[choice.finding] = offered[choice.repair]
    return [chosen.get(i, safest_repair(list(f.repairs))) for i, f in enumerate(findings)]


class _ArrangerCrew:
    """Runs ONE section's arrangement decision as an isolated, single-agent crew."""

    def __init__(self) -> None:
        config_dir = Path(__file__).parent / "config"
        self._agent_config = yaml.safe_load((config_dir / "agents.yaml").read_text())["arranger"]
        self._task_config = yaml.safe_load(
            (config_dir / "tasks.yaml").read_text())["arrange_against_lead"]

    def run(self, section: SectionCoexistence, findings: list[Finding]) -> ArrangerDecision | None:
        agent = Agent(config=self._agent_config, llm=critic_llm(), allow_delegation=False,
                      max_iter=CRITIC_MAX_ITER, max_retry_limit=AGENT_RETRY_LIMIT, verbose=False)
        task = Task(config=self._task_config, agent=agent, output_pydantic=ArrangerDecision)
        crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)
        return _decision_from_output(crew.kickoff(inputs={
            "section_kind": section.kind,
            "form_role": section.form_role or "(none)",
            "findings": "\n".join(f.render(i) for i, f in enumerate(findings)),
            "output_schema": _DECISION_SCHEMA,
        }))


class _LLMArranger:
    """The real (LLM-backed) `decide_fn` — holds the crew across sections."""

    def __init__(self) -> None:
        self._crew = _ArrangerCrew()

    def __call__(self, section: SectionCoexistence, findings: list[Finding]) -> list[Repair]:
        return _picks_from_decision(self._crew.run(section, findings), findings)


def arrange_against_lead(riff: Optional[Layer], leads: list[Layer], arr: Arrangement):
    """Run the real (LLM-backed) arranger. A clean piece makes no call at all."""
    return arrange(riff, leads, arr, decide_fn=_LLMArranger())
