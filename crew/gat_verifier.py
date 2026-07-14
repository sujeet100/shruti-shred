"""
The gat verifier (GAT OVERHAUL fix #4) — TIME-legality for the gat HEAD.

The talk point this makes concrete: **legality has two grammars — pitch AND time.** Ustad's
`validate_composition` owns PITCH legality (is every swara in the raga?). This is the TIME
counterpart for the mukhada: is the head a real, loopable, landing hook, or a fragment / a flat
run / a phrase that never cadences? Those are checkable structural invariants the composer's
pitch guardrail simply cannot see.

Why it exists at all: the aesthetic critics (Rasik/Producer) run LATE — after the whole piece is
assembled — so today there is no repair for a bad mukhada; a weak hook poisons the entire song and
the loop only notices at the end. This verifier runs EARLY, right after the head is generated, so a
weak hook can be RE-ROLLED before it is cached and looped everywhere (see `crew/lead.py`
`_generate_mukhada_cell`). Deterministic and pure — no LLM, free to run, fully unit-tested.

Scope discipline (see the campaign notes): this checks the mukhada's TIME/structure, which is
CHECKABLE — it is NOT gat/taan taste (that stays with Rasik/Producer). It never judges whether the
hook is *good*, only whether it satisfies the structural grammar of a gat head.
"""

from __future__ import annotations

from typing import Final

from crew.contracts import LeadPhrase
from raga import RAGAS

# A mukhada should fill about ONE avartan so it loops as a cycle. Too short == a fragment; well
# over the cycle == a phrase code has to truncate (cutting off its own cadence). Bounds are
# fractions of the avartan, deliberately loose — this flags the gross misses, not tight musical taste.
_FILL_MIN: Final = 0.6
_FILL_MAX: Final = 1.6
# Calling a head "flat" needs enough notes to judge — two notes of equal length is not a pattern.
_MIN_NOTES_FLAT: Final = 3


def _resting_swaras(raga: str) -> set[str]:
    """The swaras a mukhada may cadence onto — Sa (always a nyas) plus the raga's vadi/samvadi.
    Landing here is how the head resolves to the sam and loops cleanly."""
    r = RAGAS[raga]
    return {"S", r["vadi"], r["samvadi"]}


def verify_mukhada(cell: LeadPhrase, *, cycle_beats: float, raga: str) -> list[str]:
    """Return the mukhada head's TIME-legality violations (empty == a clean hook). Pure.

    Three checks the pitch guardrail can't make, each targeting a diagnosed failure of the first
    live gat:
      * FILLS THE AVARTAN — the head's total duration is about one cycle, so looping it re-lands on
        the sam instead of repeating a fragment (or being truncated mid-cadence);
      * CADENCES TO A RESTING SWARA — the last sounding note is Sa, the vadi, or the samvadi, so the
        head resolves to the sam and the loop seam lands rather than restarts;
      * NOT RHYTHMICALLY FLAT — the durations vary (the diagnosed failure was a gat of even quarter
        notes; a hook needs a rhythmic shape).
    A non-empty result drives a bounded RE-ROLL of the head in `generate_lead` — an early, local
    repair, distinct from the late global critique loop.
    """
    notes = cell.notes
    sounding = [n for n in notes if not n.rest]
    if not sounding:
        return ["the mukhada has no sounding notes — it must state a melodic head"]

    viol: list[str] = []
    total = sum(n.dur for n in notes)
    if total < _FILL_MIN * cycle_beats:
        viol.append(f"the mukhada fills only {total:g} of {cycle_beats:g} beats — a fragment, not a "
                    f"one-avartan head; fill about one full cycle so it loops on the sam")
    elif total > _FILL_MAX * cycle_beats:
        viol.append(f"the mukhada runs {total:g} beats, well over the {cycle_beats:g}-beat avartan — "
                    f"keep the head to about one cycle or it gets truncated mid-phrase")

    resting = _resting_swaras(raga)
    last = sounding[-1]
    landing = "S" if last.bol == "chikari" else last.swara   # a chikari sounds taar Sa (a resting note)
    if landing not in resting:
        viol.append(f"the mukhada ends on {last.swara}, not a resting swara "
                    f"({' '.join(sorted(resting))}) — cadence to the sam so the head lands and loops")

    if len(sounding) >= _MIN_NOTES_FLAT and len({round(n.dur, 4) for n in sounding}) == 1:
        viol.append("the mukhada is rhythmically flat — every note is the same length; vary the "
                    "durations so the head has a rhythmic shape (a gat head is not even quarters)")

    return viol
