"""
The studio session, wired to the LLM (step 3) — the COOPERATIVE half of the pipeline.

`crew/studio.py` owns the pure LOOP (who leads, how many turns, the memory threading);
this module is the imperative SHELL that plugs the two canvas-aware generators into it.
`make_contributor` builds the `contribute` callback the loop calls each turn — it hands the
right voice the shared canvas (what the other voice just played) plus the cross-section
memory, writes the returned line back onto the canvas, PRESERVES the riff-slot recurrence
(a returning hook reprises without an LLM call), and emits the collaboration events.
`compose_studio` runs the whole loop and assembles the filled canvases into the exact
(lead layers, rhythm, events) shape the band assembly and the Flow already consume.

Layering: the generation is INJECTED (studio_lead_fn / studio_riff_fn, or fakes), so
`make_contributor` and `compose_studio` are unit-tested with no LLM (tests/test_studio_session.py);
the real generators are the lazy default. The pure loop and the deterministic voices are
untouched — this only changes HOW the two creative lines are produced (together on a shared
canvas, not in isolation).
"""

from __future__ import annotations

from typing import Any, Optional

from crew.config import CANVAS_PASSES
from crew.contracts import (
    Arrangement,
    CanvasMove,
    CreativeRole,
    DebateEvent,
    EventType,
    Layer,
    RiffPattern,
    SectionCanvas,
)
from crew.generators import SectionSpan, section_spans
from crew.lead import LeadMemo, StudioLeadFn, lead_layers_from, studio_lead_fn
from crew.riff import RiffMemo, StudioRiffFn, rhythm_layer_from, slot_for, studio_riff_fn
from crew.studio import Contribute, run_studio

_ROLE_GENERATOR = "generator"
_LEAD_ROLE: CreativeRole = "lead"
_RHYTHM_ROLE: CreativeRole = "rhythm"

# A creative contribution maps to an existing event type (a refine IS a rework -> REVISE);
# the exact move always rides along in the event's `data` so the stream stays legible.
_MOVE_TYPE = {CanvasMove.PROPOSE: EventType.PROPOSE,
              CanvasMove.RESPOND: EventType.PROPOSE,
              CanvasMove.REFINE: EventType.REVISE}
_MOVE_VERB = {CanvasMove.PROPOSE: "proposes", CanvasMove.RESPOND: "responds",
              CanvasMove.REFINE: "refines"}


def _contribution_event(agent: str, move: CanvasMove, span: SectionSpan, summary: str,
                        **data: Any) -> DebateEvent:
    """One voice's turn on the canvas, as a stream event (the collaboration made visible)."""
    return DebateEvent(type=_MOVE_TYPE[move], agent=agent, role=_ROLE_GENERATOR,
                       text=f"{span.section.kind.value} — {agent} {_MOVE_VERB[move]}: {summary}",
                       data={"move": move.value, "index": span.index, **data})


def _reprise_event(span: SectionSpan, slot: str) -> DebateEvent:
    """A returning hook replays on the canvas — a light INFO beat, not a fresh proposal."""
    return DebateEvent(type=EventType.INFO, agent="Riff", role=_ROLE_GENERATOR,
                       text=f"{span.section.kind.value} — the '{slot}' riff returns (reprise)",
                       data={"move": "reprise", "index": span.index, "slot": slot, "reprise": True})


def _lead_memory(done: list[SectionCanvas]) -> list[LeadMemo]:
    """The lead's cross-section memory, sourced from the completed canvases — the realized
    prior lead lines in order (the same LeadMemo the fan-out threads)."""
    return [LeadMemo(c.kind.value, c.lead) for c in done if c.lead is not None]


def make_contributor(arr: Arrangement, *, lead_fn: StudioLeadFn,
                     riff_fn: StudioRiffFn) -> Contribute:
    """Build the LLM-backed `contribute` for `run_studio` (generation INJECTED for tests).

    Each turn dispatches to the voice, hands it the canvas (what the other voice just
    played) plus the cross-section memory, writes its line back, and emits the event. The
    riff keeps a SLOT LIBRARY so a returning hook reprises (no LLM call) and holds its shape
    across refine turns — the recurrence that makes the main riff a hook, now applied inside
    the collaboration rather than only in the fan-out.
    """
    spans = {s.index: s for s in section_spans(arr)}
    library: dict[str, RiffPattern] = {}            # slot -> its established riff
    order: list[str] = []                           # slots first-seen (the riff memory)
    reprised: set[int] = set()                      # section indices that replay a returning hook

    def _lead_turn(span: SectionSpan, canvas: SectionCanvas, done: list[SectionCanvas],
                   move: CanvasMove) -> list[DebateEvent]:
        phrase = lead_fn(span, _lead_memory(done), canvas, move)
        canvas.lead = phrase
        return [_contribution_event("Lead", move, span, f"{len(phrase.notes)} notes",
                                    swaras=[n.swara for n in phrase.notes])]

    def _riff_turn(span: SectionSpan, canvas: SectionCanvas,
                   move: CanvasMove) -> list[DebateEvent]:
        slot = slot_for(span.section)
        if canvas.riff is None and slot in library:     # a returning hook — replay, no LLM
            canvas.riff = library[slot]
            reprised.add(span.index)
            return [_reprise_event(span, slot)]
        if span.index in reprised:                       # a reprised riff holds across refines
            return []
        memory = [RiffMemo(s, library[s]) for s in order if s != slot]
        pattern = riff_fn(span, memory, canvas, move)
        if slot not in library:
            order.append(slot)
        library[slot] = pattern
        canvas.riff = pattern
        return [_contribution_event("Riff", move, span, f"{len(pattern.notes)} notes, '{slot}'",
                                    slot=slot, swaras=[n.swara for n in pattern.notes])]

    def contribute(role: CreativeRole, move: CanvasMove, canvas: SectionCanvas,
                   done: list[SectionCanvas]) -> list[DebateEvent]:
        span = spans[canvas.index]
        return (_lead_turn(span, canvas, done, move) if role == _LEAD_ROLE
                else _riff_turn(span, canvas, move))

    return contribute


def _assemble_from(canvases: list[SectionCanvas],
                   arr: Arrangement) -> tuple[list[Layer], Optional[Layer]]:
    """Place/voice the filled canvases into (lead layers, rhythm) — reused by the initial
    compose and the canvas-aware revise, so both assemble a run identically."""
    lead_phrases = {c.index: c.lead for c in canvases if c.lead is not None}
    riff_patterns = {c.index: c.riff for c in canvases if c.riff is not None}
    return lead_layers_from(lead_phrases, arr), rhythm_layer_from(riff_patterns, arr)


def compose_studio(arr: Arrangement, *, passes: int = CANVAS_PASSES,
                   lead_fn: Optional[StudioLeadFn] = None,
                   riff_fn: Optional[StudioRiffFn] = None
                   ) -> tuple[list[Layer], Optional[Layer], list[DebateEvent], list[SectionCanvas]]:
    """Run the whole cooperative session and assemble it into the band's voice shape.

    The two creative lines are composed TOGETHER on the shared canvas (not in isolation),
    then placed/voiced into the (lead layers, rhythm, events) the Flow's `_generate` returns
    — PLUS the filled canvases, which the Flow keeps in state so a surgical revise can stay
    canvas-aware (`regenerate_layer`). `lead_fn`/`riff_fn` default to the real generators;
    inject fakes to test with no LLM.
    """
    contribute = make_contributor(arr, lead_fn=lead_fn or studio_lead_fn(arr),
                                  riff_fn=riff_fn or studio_riff_fn(arr))
    result = run_studio(arr, contribute=contribute, passes=passes)
    lead_layers, rhythm = _assemble_from(result.canvases, arr)
    return lead_layers, rhythm, result.events, result.canvases


def regenerate_layer(arr: Arrangement, canvases: list[SectionCanvas], layer: str, *,
                     lead_fn: Optional[StudioLeadFn] = None,
                     riff_fn: Optional[StudioRiffFn] = None
                     ) -> tuple[list[Layer], Optional[Layer], list[DebateEvent], list[SectionCanvas]]:
    """CANVAS-AWARE surgical revise: regenerate ONLY the flagged voice, each section still
    seeing the OTHER voice's current line on the retained canvas — so the collaboration
    survives the revise instead of being overwritten by an isolated regeneration.

    `arr` is the REVISED arrangement (the Conductor's directive already threaded into the
    flagged sections' intent). The regenerated voice plays a REFINE move — reworking against
    the ensemble it can see — and the riff keeps its slot recurrence (a returning hook is
    regenerated once and reprised). Mutates the canvases in place and returns the reassembled
    (lead layers, rhythm, events, canvases). A non-creative flagged layer regenerates nothing.
    """
    spans = {s.index: s for s in section_spans(arr)}
    events: list[DebateEvent] = []
    if layer == _LEAD_ROLE:
        lead = lead_fn or studio_lead_fn(arr)
        memory: list[LeadMemo] = []
        for canvas in canvases:
            span = spans[canvas.index]
            if _LEAD_ROLE not in span.section.layers:
                continue
            canvas.lead = lead(span, list(memory), canvas, CanvasMove.REFINE)
            events.append(_contribution_event("Lead", CanvasMove.REFINE, span,
                          f"{len(canvas.lead.notes)} notes",
                          swaras=[n.swara for n in canvas.lead.notes]))
            memory.append(LeadMemo(canvas.kind.value, canvas.lead))
    elif layer == _RHYTHM_ROLE:
        riff = riff_fn or studio_riff_fn(arr)
        library: dict[str, RiffPattern] = {}
        order: list[str] = []
        for canvas in canvases:
            span = spans[canvas.index]
            if _RHYTHM_ROLE not in span.section.layers:
                continue
            slot = slot_for(span.section)
            if slot in library:                          # a returning hook — reprise the regen
                canvas.riff = library[slot]
                events.append(_reprise_event(span, slot))
                continue
            memory = [RiffMemo(s, library[s]) for s in order]
            canvas.riff = riff(span, memory, canvas, CanvasMove.REFINE)
            library[slot] = canvas.riff
            order.append(slot)
            events.append(_contribution_event("Riff", CanvasMove.REFINE, span,
                          f"{len(canvas.riff.notes)} notes, '{slot}'", slot=slot,
                          swaras=[n.swara for n in canvas.riff.notes]))
    lead_layers, rhythm = _assemble_from(canvases, arr)
    return lead_layers, rhythm, events, canvases
