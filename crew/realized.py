"""
What each creative voice REALIZED, carried on the event stream — so a revise re-composes only the
sections its plan names and replays the rest.

The 2026-10-11 run paid for nine lead calls per revise round and kept one or two of them: the
whole voice was regenerated and `revision.splice_layers` then discarded every section outside the
plan. Now each pass ends with ONE event holding the material it settled on — the lead's phrase per
section (and its taan fills), the riff's one cycle per slot — and the revise hands the kept part
back to the generator, which calls the model only for what is left. The event stream is the seam
because it already travels to every caller (the same reason the gat head rides it, `crew.anchor`).

Pure: no LLM, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from crew.contracts import DebateEvent, EventType, LeadPhrase, RiffPattern

REALIZED_LEAD_KEY: Final = "realized_lead"
REALIZED_RIFF_KEY: Final = "realized_riff"
_ROLE: Final = "generator"


@dataclass(frozen=True)
class KeptLead:
    """The lead material a revise keeps: section index -> its phrase, and the taan fills the
    long mukhada sections cut in (kept with the head they were verified against)."""
    phrases: dict[int, LeadPhrase]
    fills: list[LeadPhrase] = field(default_factory=list)


def lead_realized_event(phrases: dict[int, LeadPhrase], fills: list[LeadPhrase]) -> DebateEvent:
    """The lead pass's closing beat: the phrase it settled on in every section. Pure."""
    return DebateEvent(
        type=EventType.INFO, agent="Lead", role=_ROLE,
        text=f"the lead line is set across {len(phrases)} section(s)",
        data={REALIZED_LEAD_KEY: {
            "phrases": {str(i): p.model_dump(exclude_none=True) for i, p in phrases.items()},
            "fills": [f.model_dump(exclude_none=True) for f in fills]}})


def riff_realized_event(library: dict[str, RiffPattern]) -> DebateEvent:
    """The riff pass's closing beat: the one cycle it settled on for every slot. Pure."""
    return DebateEvent(
        type=EventType.INFO, agent="Riff", role=_ROLE,
        text=f"the riff library is set: {', '.join(library) or 'empty'}",
        data={REALIZED_RIFF_KEY: {s: p.model_dump(exclude_none=True) for s, p in library.items()}})


def _latest(events: list[DebateEvent], key: str) -> dict | None:
    return next(((e.data or {})[key] for e in reversed(events) if (e.data or {}).get(key)
                 is not None), None)


def realized_lead(events: list[DebateEvent]) -> KeptLead | None:
    """The LATEST lead pass's material (a revise appends a newer one), or None when no pass has
    published one. Pure."""
    data = _latest(events, REALIZED_LEAD_KEY)
    if data is None:
        return None
    return KeptLead(phrases={int(i): LeadPhrase.model_validate(p) for i, p in data["phrases"].items()},
                    fills=[LeadPhrase.model_validate(f) for f in data.get("fills", [])])


def realized_riffs(events: list[DebateEvent]) -> dict[str, RiffPattern] | None:
    """The LATEST riff pass's slot library, or None when no pass has published one. Pure."""
    data = _latest(events, REALIZED_RIFF_KEY)
    if data is None:
        return None
    return {slot: RiffPattern.model_validate(p) for slot, p in data.items()}


def kept_lead(kept: KeptLead, targets: list[int]) -> KeptLead:
    """What a lead revise keeps: every section but the targets. The fills ride with the head —
    `generate_lead` replays them while the head is kept and writes new ones with a new head. Pure."""
    phrases = {i: p for i, p in kept.phrases.items() if i not in targets}
    return KeptLead(phrases=phrases, fills=kept.fills)


def kept_riffs(library: dict[str, RiffPattern], target_slots: set[str]) -> dict[str, RiffPattern]:
    """What a riff revise keeps: every slot no targeted section plays. Pure."""
    return {slot: p for slot, p in library.items() if slot not in target_slots}
