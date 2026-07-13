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

The cooperative LOOP itself (the LLM turns that actually write on the canvas) lands
in the next sub-step; this module is the deterministic skeleton it walks, fully
unit-tested with no LLM and no cost.
"""

from __future__ import annotations

from dataclasses import dataclass

from crew.config import CANVAS_PASSES
from crew.contracts import CanvasMove, CreativeRole, SectionKind


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
