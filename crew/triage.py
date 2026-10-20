"""
The final call on a critiqued piece — pure CODE, no referee agent (the redesign, 2026-10-11).

There used to be a Conductor: it triaged, ran a bounded Rasik↔Producer debate on any aesthetic
conflict, and ruled. The debate added no musical information (two verdicts already on the
table, re-argued in character), and its accept-in-round-0 on a piece a single bare model call
beat showed the arbitration was not where quality came from. So the decision is now two rules:

  * LEGALITY IS NON-NEGOTIABLE — an illegal piece is a forced revise of the voice holding the
    most violations, decided by code, no LLM;
  * A SILENT LEAD IS A PHYSICAL FAULT — a lead-spotlight section the sitar is heard in for under
    `LEAD_STARVED_COVERAGE` of its beats (a plucked note fades, so a long hold is silence) is a
    forced lead revise of those sections. The Producer reads a score, where a 48-beat note looks
    like melody, and scored such a piece's balance 4-5 three times; the fault is measurable, so
    code owns it (it needs the composition + chart, so it runs only when the caller passes them);
  * otherwise THE PRODUCER DECIDES — it has read Rasik's consultation and the measurements, and
    its `decision` + `plan` stand (a revise with no plan is nothing actionable: accept).

The Flow's round cap is still the terminator (crew/flow.py). Pure: no LLM, no I/O.
"""

from __future__ import annotations

from collections import Counter
from typing import Final, Optional

from crew.contracts import (
    Arrangement,
    Composition,
    DebateEvent,
    EventType,
    ProducerVerdict,
    RevisionPlan,
    RevisionVoice,
    UstadVerdict,
    Violation,
)
from crew.metrics import LEAD_STARVED_COVERAGE, LeadCoverage, lead_coverage

_ORCH_PREFIX: Final = "orch_"
# Composition layer roles -> the creative voice that produces them. Bass and the double-tracked
# guitar derive from the riff; drone and the clean guitar are code and are not revisable.
_ROLE_VOICE: Final[dict[str, RevisionVoice]] = {"lead": "lead", "rhythm": "riff", "bass": "riff"}
_STARVED_INSTRUCTION: Final = (
    "the lead is barely heard here — a plucked sitar note fades a few beats after its stroke, so "
    "a long held note sounds as silence. Fill the section with phrases: keep the line moving, "
    "re-strike any swara you want to sustain, and hold no note longer than about 4 beats")

type Call = tuple[Optional[RevisionPlan], list[DebateEvent]]


def _voice_of(layer: str) -> Optional[RevisionVoice]:
    if layer.startswith(_ORCH_PREFIX):
        return "orchestra"
    return _ROLE_VOICE.get(layer)


def legality_plan(violations: list[Violation]) -> Optional[RevisionPlan]:
    """The forced revise for an illegal piece: the revisable voice with the most violations,
    told exactly which swaras left the raga. None when no revisable voice holds one (an
    illegal DERIVED voice is a code bug, not something a regeneration can fix). Pure."""
    voices = Counter(v for v in (_voice_of(x.layer) for x in violations) if v is not None)
    if not voices:
        return None
    voice = voices.most_common(1)[0][0]
    swaras = sorted({x.swara for x in violations if _voice_of(x.layer) == voice})
    return RevisionPlan(voice=voice, instruction=(
        f"use only the raga's swaras — the notes {', '.join(swaras)} are outside it"))


def _decision_event(agent: str, plan: Optional[RevisionPlan], text: str) -> DebateEvent:
    decision = "revise" if plan is not None else "accept"
    return DebateEvent(type=EventType.VERDICT, agent=agent, role="critic", text=text,
                       verdict=decision,
                       data={"decision": decision,
                             "plan": plan.model_dump() if plan is not None else None})


def starved_lead_plan(coverage: list[LeadCoverage]) -> Optional[RevisionPlan]:
    """The forced revise for a silent lead: the lead, in exactly the lead-spotlight sections it
    is heard in for under `LEAD_STARVED_COVERAGE` of the time. None when every one sounds. Pure."""
    starved = [row.index for row in coverage if row.starved]
    if not starved:
        return None
    return RevisionPlan(voice="lead", sections=starved, instruction=_STARVED_INSTRUCTION)


def _forced_legality(ustad: UstadVerdict) -> Optional[Call]:
    plan = legality_plan(ustad.violations) if ustad.verdict == "illegal" else None
    if plan is None:
        return None
    return plan, [_decision_event(
        "Ustad", plan, f"Illegal notes — the {plan.voice} is reworked: {plan.instruction}.")]


def _forced_physical(comp: Optional[Composition], arr: Optional[Arrangement]) -> Optional[Call]:
    if comp is None or arr is None:
        return None
    plan = starved_lead_plan(lead_coverage(comp, arr))
    if plan is None:
        return None
    numbers = ", ".join(str(i) for i in plan.sections)         # as THE STRUCTURE numbers them
    return plan, [_decision_event(
        "Producer", plan, f"The lead is barely audible in section(s) {numbers} (under "
        f"{LEAD_STARVED_COVERAGE:.0%} of the time) — the lead is reworked: {plan.instruction}.")]


def _producer_call(ustad: UstadVerdict, producer: ProducerVerdict) -> Call:
    if ustad.verdict == "illegal":                 # illegal, but only in a code-derived voice
        return None, [_decision_event(
            "Ustad", None, "Illegal notes in a code-derived voice that no agent can rewrite — stopping; the "
            "final check decides what ships.")]
    plan = producer.plan if producer.decision == "revise" else None
    text = (f"Revise the {plan.voice}: {plan.instruction}" if plan
            else "The Producer accepts the piece.")
    return plan, [_decision_event("Producer", plan, text)]


def decide(ustad: UstadVerdict, producer: ProducerVerdict,
           comp: Optional[Composition] = None, arr: Optional[Arrangement] = None) -> Call:
    """The final call: (the plan to carry out, or None to accept) + one VERDICT event. In order:
    legality (forced), a starved lead (forced; needs `comp` + `arr`), then the Producer. Pure."""
    return (_forced_legality(ustad) or _forced_physical(comp, arr)
            or _producer_call(ustad, producer))
