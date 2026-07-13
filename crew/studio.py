"""
The studio session — bounded COOPERATIVE collaboration on a shared canvas.

This is the talk's SECOND named multi-agent pattern, beside the critique loop.
Where the critique loop is ADVERSARIAL (critics argue, a referee rules), the studio
session is COOPERATIVE (the band builds a section together on a shared blackboard,
the `SectionCanvas`): the leader seeds the section, the follower answers what it
hears, then a bounded number of refinement turns integrate the two.

This sub-step is the BANDLEADER + CLOCK — pure code that decides WHO leads each
section and WHEN the session stops, so the collaboration stays visible and always
terminates (the project's thesis: orchestrated L2/L3, never autonomous L4 where the
agents choose the turn order or when to quit).

  * WHO leads is fixed by the section's KIND (`leader_for`), a code rule, not a
    runtime choice — a rhythm-driven kind is led by the Riff, a melodic/expository
    kind by the Lead. The leader ROTATES across a piece (because the kinds do), so
    the collaboration varies section to section while each kind's session stays
    deterministic and stage-repeatable.
  * WHEN it stops is a fixed turn budget (`collaboration_schedule`, capped by
    `CANVAS_PASSES`) — the guaranteed terminator, never organic consensus.

The cooperative LOOP now lives here too (`run_studio`): a pure driver that walks the
schedule section by section, filling each `SectionCanvas`, with the actual note-writing
INJECTED as a `contribute` callback — so the loop is unit-tested with no LLM and no
cost, exactly like the Flow's injected `Stages`. The LLM-backed contributors (the Lead
and Riff writing real lines on the canvas) and the wiring into the Flow land next.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from crew.config import CANVAS_PASSES
from crew.contracts import (
    Arrangement,
    CanvasMove,
    CreativeRole,
    DebateEvent,
    EventType,
    Section,
    SectionCanvas,
    SectionKind,
)
from crew.generators import SectionSpan, section_spans


# --------------------------------------------------------------------------- #
# WHO leads — the bandleader rule, in CODE. Fixed by section kind (DESIGN.md's #
# rotation): the rhythm-driven kinds open with the Riff; every melodic or       #
# expository kind opens with the Lead. Not chosen at runtime — that would be    #
# the autonomous L4 we deliberately avoid.                                      #
# --------------------------------------------------------------------------- #

_LEADER_BY_KIND: dict[SectionKind, CreativeRole] = {
    SectionKind.RIFF: "rhythm",         # the main riff — the Riff opens, the Lead answers sparsely
    SectionKind.BREAKDOWN: "rhythm",    # heavy, sparse crush — rhythm-led
    SectionKind.ALAAP: "lead",          # unmetered raga exposition — the sitar leads, the riff lays out
    SectionKind.MELODY: "lead",         # the theme — the Lead states it, the Riff supports
    SectionKind.TAAN: "lead",           # the melodic climax — the Lead drives, the Riff beds it
    SectionKind.SOLO: "lead",           # lead improvisation over the riff
    SectionKind.OUTRO: "lead",          # the Lead resolves; the Riff winds down
}
_DEFAULT_LEADER: CreativeRole = "lead"


def leader_for(kind: SectionKind) -> CreativeRole:
    """Which creative voice OPENS this section — the bandleader's call, in code."""
    return _LEADER_BY_KIND.get(kind, _DEFAULT_LEADER)


def follower_of(role: CreativeRole) -> CreativeRole:
    """The other creative voice — the one who answers the leader."""
    return "rhythm" if role == "lead" else "lead"


# --------------------------------------------------------------------------- #
# WHEN it stops — the clock. A fixed, bounded turn plan the loop walks.         #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Turn:
    """One contribution in a section's studio session — a voice and what it does.
    Immutable: the schedule is a fixed plan the loop reads, not mutable state."""
    role: CreativeRole
    move: CanvasMove


def collaboration_schedule(kind: SectionKind, *, passes: int = CANVAS_PASSES) -> list[Turn]:
    """The bounded turn plan for a section's canvas — the CLOCK, in code.

    The leader PROPOSES onto the empty canvas, the follower RESPONDS to what it
    hears, then the two alternate REFINE turns (each reworking its own line given
    the now-populated ensemble). The plan is truncated to `passes` turns — the
    guaranteed terminator, so a session can never run away on stage. `passes` is
    the studio's bound (defaults to `CANVAS_PASSES`); a smaller value is the
    live-safe "fast mode".

        passes >= 3 -> [leader:propose, follower:respond, leader:refine, follower:refine, ...]
        passes == 2 -> [leader:propose, follower:respond]   (the pure seed exchange)
        passes == 1 -> [leader:propose]                     (leader only — degenerate)

    Note: at passes == 1 the follower never plays, so it is not really a
    collaboration (the follower would fall back to solo generation). The intended
    live-safe floor is 2 (a full seed exchange — both voices contribute once); the
    default 3 adds one integrating refine. Kept configurable so the wiring step can
    choose the fast-mode value.
    """
    leader = leader_for(kind)
    follower = follower_of(leader)
    plan: list[Turn] = [Turn(leader, CanvasMove.PROPOSE), Turn(follower, CanvasMove.RESPOND)]
    voices = (leader, follower)                      # refine turns alternate, leader first
    while len(plan) < passes:
        plan.append(Turn(voices[(len(plan) - 2) % 2], CanvasMove.REFINE))
    return plan[:passes]


# --------------------------------------------------------------------------- #
# The cooperative LOOP — a pure driver over the schedule. The actual           #
# note-writing (LLM or a test fake) is INJECTED as `contribute`, the same seam #
# the Flow uses for its `Stages`, so the whole loop is tested with no LLM.      #
# --------------------------------------------------------------------------- #

# One voice's turn at the canvas: it READS the canvas (the other voice's line +
# the shared intent) and the completed prior sections (the cross-section memory),
# WRITES its own line/intent back IN PLACE, and returns the events for that turn.
type Contribute = Callable[
    [CreativeRole, CanvasMove, SectionCanvas, list[SectionCanvas]],
    list[DebateEvent]]


def active_roles(section: Section) -> list[CreativeRole]:
    """The creative voices that actually play this section, LEADER FIRST.

    A voice is active only if its role is one of the section's `layers`; one that is
    not LAYS OUT — silence is a valid contribution (an alaap's riff, say). Leader-first
    is the order the session runs them, so the caller reads it as [leader, follower].
    """
    leader = leader_for(section.kind)
    return [r for r in (leader, follower_of(leader)) if r in section.layers]


def section_turns(section: Section, *, passes: int = CANVAS_PASSES) -> list[Turn]:
    """The bounded turn plan for a section, honouring which voices are active.

      * BOTH creative voices active -> the full `collaboration_schedule` (leader
        proposes, follower responds, then bounded refines) — a real session;
      * exactly ONE active -> a single solo PROPOSE (no counterpart to answer, so no
        respond/refine) — a genuine solo, e.g. a sitar alaap with the riff laid out;
      * NONE active -> [] (no creative voice; the deterministic rhythm section carries it).

    Bounded either way — the terminator is `collaboration_schedule`'s `passes` cap.
    """
    roles = active_roles(section)
    if not roles:
        return []
    if len(roles) == 1:
        return [Turn(roles[0], CanvasMove.PROPOSE)]
    return collaboration_schedule(section.kind, passes=passes)


def session_canvas(span: SectionSpan) -> SectionCanvas:
    """A fresh blackboard for a section — its window and leader/follower fixed by CODE
    (the section's position on the grid + the bandleader rule); the intent and the note
    lines start empty and are filled by the session."""
    leader = leader_for(span.section.kind)
    return SectionCanvas(index=span.index, kind=span.section.kind,
                         start=span.start, end=span.end,
                         leader=leader, follower=follower_of(leader))


@dataclass(frozen=True)
class StudioResult:
    """The outcome of a studio run — every section's FILLED canvas plus the event
    stream (the session framing + each voice's contribution), in order."""
    canvases: list[SectionCanvas]
    events: list[DebateEvent]


def _session_event(canvas: SectionCanvas, turns: list[Turn]) -> DebateEvent:
    """A framing INFO beat announcing a section's session — silent, solo, or a full
    leader/follower collaboration — so the stream (and the audience) can see who is
    about to build this section before the notes arrive."""
    common = {"index": canvas.index, "passes": len(turns)}
    if not turns:
        return DebateEvent(type=EventType.INFO, agent="Studio", role="system",
                           text=f"{canvas.kind.value}: no creative voice — "
                                f"the deterministic rhythm section carries it",
                           data=common)
    if len(turns) == 1:
        return DebateEvent(type=EventType.INFO, agent="Studio", role="system",
                           text=f"{canvas.kind.value}: {turns[0].role} solo "
                                f"(the other voice lays out)",
                           data={**common, "leader": turns[0].role})
    return DebateEvent(type=EventType.INFO, agent="Studio", role="system",
                       text=f"{canvas.kind.value}: {canvas.leader} leads, "
                            f"{canvas.follower} follows ({len(turns)} passes)",
                       data={**common, "leader": canvas.leader, "follower": canvas.follower})


def run_studio(arr: Arrangement, *, contribute: Contribute,
               passes: int = CANVAS_PASSES) -> StudioResult:
    """Walk the whole arrangement as a sequence of bounded studio sessions.

    For each section, in order: build a fresh `SectionCanvas`, then run its turn plan
    (`section_turns`) — leader proposes, follower responds, bounded refines — calling
    `contribute` for each turn. Every COMPLETED canvas is handed to later sections as
    the piece's realized memory (both voices, cross-section), so the band builds ON what
    came before instead of composing blind.

    Pure control flow: `contribute` does the actual writing (LLM or a test fake), so the
    loop is unit-tested with no LLM — the terminator (`passes`) and the order (the
    bandleader rule) are guaranteed in CODE, never chosen by the agents.
    """
    canvases: list[SectionCanvas] = []
    events: list[DebateEvent] = []
    for span in section_spans(arr):
        canvas = session_canvas(span)
        turns = section_turns(span.section, passes=passes)
        events.append(_session_event(canvas, turns))
        for turn in turns:
            events.extend(contribute(turn.role, turn.move, canvas, list(canvases)))
        canvases.append(canvas)
    return StudioResult(canvases=canvases, events=events)
