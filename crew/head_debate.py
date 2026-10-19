"""
The HEAD debate — two composers argue over their gat heads for several rounds (Sujit, 2026-10-18).

The seed debate argued over seed IDEAS, and its revisions were recomposed from scratch, so a change
was as much a new roll of the dice as an argument. Here the debate is over the NOTES: each composer
wrote a head from its own approach (the information differs, so the drafts differ), then in every
round both read both heads as they stand — notes plus code's measurements — argue, and keep or
revise their own head. Rounds are simultaneous (both answer the same pair) and stop early when
both keep. Every version is kept, so the run shows what arguing actually did: did the heads move
toward each other, toward the raga, or nowhere?

Pure: the turn is injected, so the loop is tested with no LLM (`seed_debate_crew.llm_head_turn`
is the live one).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from crew.anchor import lead_tokens
from crew.contracts import HeadTurn, LeadPhrase

MAX_ROUNDS: Final = 4
# (composer, own head, the other head, round) -> the composer's turn
TurnFn = Callable[[str, LeadPhrase, LeadPhrase, int], HeadTurn]


@dataclass(frozen=True)
class HeadVersion:
    """One head as it stood: round 0 is the proposal."""
    composer: str
    round: int
    head: LeadPhrase
    argument: str = ""
    changed: bool = False


def head_debate(proposals: dict[str, LeadPhrase], turn_fn: TurnFn,
                rounds: int = MAX_ROUNDS) -> list[HeadVersion]:
    """Every version, from the two proposals to the last round. Both composers answer the same pair
    each round; a dead turn keeps its head; the debate ends early when neither changes."""
    a, b = proposals
    current = dict(proposals)
    versions = [HeadVersion(c, 0, h) for c, h in current.items()]
    for r in range(1, rounds + 1):
        turns = {c: _turn(turn_fn, c, current[c], current[o], r) for c, o in ((a, b), (b, a))}
        for c, turn in turns.items():
            current[c] = turn.head
            versions.append(HeadVersion(c, r, turn.head, turn.argument, turn.changed))
        if not any(t.changed for t in turns.values()):
            break
    return versions


def _turn(turn_fn: TurnFn, composer: str, own: LeadPhrase, other: LeadPhrase, r: int) -> HeadTurn:
    try:
        turn = turn_fn(composer, own, other, r)
    except Exception as exc:  # noqa: BLE001 — LIVE SAFETY: a dead turn keeps the head
        return HeadTurn(argument=f"(no turn: {exc})", changed=False, head=own)
    return turn if turn.changed else turn.model_copy(update={"head": own})   # "kept" means kept


# --------------------------------------------------------------------------- #
# The debate's view of a head — the notes, and what code can measure.         #
# --------------------------------------------------------------------------- #

def swara_loop(head: LeadPhrase) -> list[str]:
    """The head's sounding swaras with its first note appended: it loops, so its last phrase
    lands on that note at the next sam."""
    sw = [n.swara for n in head.notes if not n.rest]
    return sw + sw[:1]


def count_cell(seq: list[str], cell: list[str]) -> int:
    n = len(cell)
    return sum(1 for i in range(len(seq) - n + 1) if seq[i:i + n] == cell)


def head_measures(head: LeadPhrase, held: tuple[str, ...] = ("g", "d")) -> dict[str, float | int]:
    """What code measures of a head for the debate: the raga's recurring cells (counted across the
    loop), the held andolit swaras, and how much of it sits low. Darbari's cells by default — the
    run this was built for; the measures are reports, never rules."""
    loop = swara_loop(head)
    sounding = [n for n in head.notes if not n.rest]
    total = sum(n.dur for n in sounding) or 1.0
    return {"g m R S": count_cell(loop, ["g", "m", "R", "S"]),
            "d n P": count_cell(loop, ["d", "n", "P"]),
            "held g/d (2+ beats)": sum(1 for n in sounding if n.swara in held and n.dur >= 2),
            "below madhya Sa": round(sum(n.dur for n in sounding if n.oct < 0) / total, 2)}


def render_head(label: str, head: LeadPhrase) -> str:
    measures = "; ".join(f"{k}: {v}" for k, v in head_measures(head).items())
    return f"  {label}\n    notes: {lead_tokens(head.notes)}\n    measured: {measures}"


def render_pair(own: LeadPhrase, other: LeadPhrase) -> str:
    """The `{debate}` block: YOUR head and THE OTHER COMPOSER'S head."""
    return render_head("YOUR HEAD", own) + "\n" + render_head("THE OTHER COMPOSER'S HEAD", other)
