"""
The SEED DEBATE experiment — does letting two composers hear and argue with each other produce a
better musical identity than simply giving one composer more attempts? (Decided 2026-10-12:
build the Debator pattern only if it measurably fits.)

Three arms over the same brief, the two contenders at an EQUAL call budget:
  * SINGLE  — one seed (the baseline, 1 call);
  * BEST_OF — four independent seeds, then the selector (4 + 2 = 6 calls);
  * DEBATE  — two independent seeds; each composer reads the rival's seed and code's measurements
              of both, argues, and returns its OWN seed revised or kept (one round, no forced
              consensus); then the selector (2 + 2 + 2 = 6 calls).
Both contenders alternate the same two starting nudges (riff first / gat head first), so the only
difference between them is the debate. If BEST_OF matches DEBATE by ear, the gain came from more
candidates, not from the argument.

The SELECTOR runs twice with the candidates in reverse order; a disagreement is position bias, not
a preference, and code breaks the tie (fewest measured problems, then the first). Who wins is
finally Sujit's ear, blind (`crew/audition.py`) — an LLM judging whether LLM debate helps would
carry the very biases the debate literature warns about.

Pure control flow: every model call is injected, so all three arms are tested with no key.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final

from crew.contracts import CompositionBrief, DebateEvent, DebateTurn, EventType, SeedChoice, SongSeed
from crew.seed_measures import measure_seed, render_seed

RIFF_FIRST: Final = ("Lean toward the RIFF: conceive the main riff first and let the hook answer "
                     "it (anchor riff_first).")
GAT_FIRST: Final = ("Lean toward the GAT HEAD: conceive the sitar's head first and let the riff "
                    "reduce it (anchor gat_first).")
APPROACHES: Final = (RIFF_FIRST, GAT_FIRST)
BEST_OF_N: Final = 4
_ROLE: Final = "composer"

# (brief, approach) -> a seed that passed the seed guardrail
type SeedFn = Callable[[CompositionBrief, str], SongSeed]
# (brief, own seed, rival seed, both rendered with measurements) -> the composer's turn
type TurnFn = Callable[[CompositionBrief, SongSeed, SongSeed, str], DebateTurn]
# (brief, the labelled candidates rendered, how many) -> the selector's choice
type SelectFn = Callable[[CompositionBrief, str, int], SeedChoice]


@dataclass(frozen=True)
class ArmResult:
    """One arm's outcome: the chosen seed, every candidate it weighed, the independent DRAFTS it
    started from (for the debate, the seeds before the argument), its events, its calls."""
    arm: str
    seed: SongSeed
    candidates: list[SongSeed]
    events: list[DebateEvent] = field(default_factory=list)
    calls: int = 0
    drafts: list[SongSeed] = field(default_factory=list)


def _event(agent: str, text: str, kind: EventType = EventType.INFO, **data) -> DebateEvent:
    return DebateEvent(type=kind, agent=agent, role=_ROLE, text=text, data=data)


def _seeds(brief: CompositionBrief, count: int, seed_fn: SeedFn) -> list[SongSeed]:
    """`count` independent seeds, alternating the two starting nudges."""
    return [seed_fn(brief, APPROACHES[i % len(APPROACHES)]) for i in range(count)]


def render_candidates(brief: CompositionBrief, seeds: list[SongSeed]) -> str:
    """The candidates as the selector reads them, labelled 1..K in the given order. Pure."""
    return "\n\n".join(render_seed(str(i + 1), s, brief) for i, s in enumerate(seeds))


def _problems(seed: SongSeed, brief: CompositionBrief) -> int:
    m = measure_seed(seed, brief)
    return len(m.frame_notes) + len(m.head_notes) + len(m.long_scalar_runs)


def _vote(choice: SeedChoice | None, order: list[int]) -> int | None:
    """The candidate index a choice names in `order`, or None when it names no candidate."""
    if choice is None or not 1 <= choice.choice <= len(order):
        return None
    return order[choice.choice - 1]


def select(brief: CompositionBrief, seeds: list[SongSeed], *,
           select_fn: SelectFn) -> tuple[int, list[DebateEvent]]:
    """The index of the strongest seed: the selector asked twice, the order reversed the second
    time. Agreement wins; a disagreement (or a dead call) is broken by code — the fewest measured
    problems, then the earlier candidate."""
    forward = list(range(len(seeds)))
    backward = forward[::-1]
    votes = []
    for order in (forward, backward):
        try:
            choice = select_fn(brief, render_candidates(brief, [seeds[i] for i in order]), len(seeds))
        except Exception:  # noqa: BLE001 — LIVE SAFETY: a dead judge call is a missing vote
            choice = None
        votes.append(_vote(choice, order))
    if votes[0] is not None and votes[0] == votes[1]:
        return votes[0], [_event("Selector", f"both orders chose seed {votes[0] + 1}",
                                 chosen=votes[0], votes=votes)]
    chosen = min(forward, key=lambda i: (_problems(seeds[i], brief), i))
    return chosen, [_event("Selector", f"the two orders disagreed ({votes}) — code broke the tie: "
                                       f"seed {chosen + 1}, fewest measured problems",
                           chosen=chosen, votes=votes, tie=True)]


def single_seed(brief: CompositionBrief, *, seed_fn: SeedFn) -> ArmResult:
    """The baseline: one seed, one call, no nudge."""
    seed = seed_fn(brief, "")
    return ArmResult("single", seed, [seed], [_event("Composer", "one seed", EventType.PROPOSE)], 1,
                     [seed])


def best_of(brief: CompositionBrief, *, seed_fn: SeedFn, select_fn: SelectFn,
            n: int = BEST_OF_N) -> ArmResult:
    """More attempts, no argument: `n` independent seeds, then the selector."""
    seeds = _seeds(brief, n, seed_fn)
    chosen, events = select(brief, seeds, select_fn=select_fn)
    return ArmResult("best_of", seeds[chosen], seeds, events, n + 2, seeds)


def _turn(brief: CompositionBrief, own: SongSeed, rival: SongSeed, turn_fn: TurnFn,
          label: str) -> tuple[SongSeed, DebateEvent]:
    """One composer's debate turn — its own seed, revised or kept. A dead call keeps the seed."""
    both = render_candidates(brief, [own, rival]).replace("SEED 1", "YOUR SEED", 1).replace(
        "SEED 2", "THE RIVAL'S SEED", 1)
    try:
        turn = turn_fn(brief, own, rival, both)
    except Exception as exc:  # noqa: BLE001 — LIVE SAFETY: the debate must not kill the run
        return own, _event(f"Composer {label}", f"no turn ({exc}) — keeps its seed")
    return turn.seed, _event(f"Composer {label}", turn.argument, EventType.DEBATE,
                             changed=turn.changed)


def debate(brief: CompositionBrief, *, seed_fn: SeedFn, turn_fn: TurnFn,
           select_fn: SelectFn) -> ArmResult:
    """Two independent seeds, ONE round of argument (each revises its own or keeps it — no
    consensus is forced), then the selector over the two that came out of it."""
    first, second = _seeds(brief, 2, seed_fn)
    revised_first, e1 = _turn(brief, first, second, turn_fn, "A")
    revised_second, e2 = _turn(brief, second, first, turn_fn, "B")
    finalists = [revised_first, revised_second]
    chosen, events = select(brief, finalists, select_fn=select_fn)
    return ArmResult("debate", finalists[chosen], finalists, [e1, e2, *events], 2 + 2 + 2,
                     [first, second])
