"""
Ustad — the LEGALITY critic, now pure CODE (the redesign, 2026-10-11).

Whether a composition stays inside its raga is a grammar fact, not a matter of taste, so the
deterministic `raga.validate_composition` has always owned the verdict. The LLM only ever
NARRATED it, and on a clean piece (the common path, since the generators' guardrails gate
illegal notes) it was already skipped. A narration of a fact is rendered just as well by code,
for free and identically every time, so Ustad no longer calls a model at all: the verdict,
the violations and the explanation all come from the validator. The redesign's principle in
its smallest form — an agent earns its place only where the judgment is not checkable.

`critique_legality(comp)` keeps its signature and its CRITIQUE event, so the Flow and the UI
stream are unchanged. Pure: no LLM, no I/O.
"""

from __future__ import annotations

from collections import Counter
from typing import Final

from crew.contracts import Composition, DebateEvent, EventType, UstadVerdict, Violation
from raga import RAGAS, validate_composition

_ROLE_CRITIC: Final = "critic"
_MAX_LISTED: Final = 3          # violations named in the explanation before "and N more"


def _explain(raga: str, violations: list[Violation]) -> str:
    """A musician's one-paragraph account of the validator's result. Pure."""
    display = RAGAS[raga]["display"]
    if not violations:
        return f"All notes sit inside {display} — the piece is legal in the raga."
    by_voice = Counter(v.layer for v in violations)
    voices = ", ".join(f"{layer} ({n})" for layer, n in by_voice.most_common())
    listed = "; ".join(f"{v.layer} plays {v.swara} at beat {v.start_beat:g} ({v.kind})"
                       for v in violations[:_MAX_LISTED])
    more = f", and {len(violations) - _MAX_LISTED} more" if len(violations) > _MAX_LISTED else ""
    allowed = " ".join(RAGAS[raga]["allowed"])
    return (f"{len(violations)} note(s) leave {display} — by voice: {voices}. {listed}{more}. "
            f"The raga allows only {allowed}.")


def _verdict_event(verdict: UstadVerdict) -> DebateEvent:
    return DebateEvent(
        type=EventType.CRITIQUE, agent="Ustad", role=_ROLE_CRITIC,
        text=verdict.explanation, verdict=verdict.verdict,
        data={"violations": [v.model_dump() for v in verdict.violations],
              "reasoning": verdict.reasoning})


def assess(comp: Composition) -> tuple[UstadVerdict, list[DebateEvent]]:
    """Judge a composition's raga-legality: the deterministic validator decides AND explains.
    Returns the verdict and its one CRITIQUE event. Pure."""
    payload = comp.model_dump(exclude_none=True)
    violations = [Violation(**v) for v in validate_composition(payload)]
    verdict = UstadVerdict(
        verdict="illegal" if violations else "legal",
        violations=violations,
        explanation=_explain(comp.raga, violations),
        reasoning=f"validate_composition returned {len(violations)} violation(s).")
    return verdict, [_verdict_event(verdict)]


def critique_legality(comp: Composition) -> tuple[UstadVerdict, list[DebateEvent]]:
    """The Flow's legality stage — code only (kept as the stable entry point)."""
    return assess(comp)
