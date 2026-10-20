"""
WHEN THE NOTES DEBATE RUNS — only for a concrete concern (2026-10-20, GPT's review).

The debate used to run on every accepted song: ~8-12 calls across two models, minutes outside the
round cap, and a record by ear of 2 better / 1 sidegrade / 1 neutral out of 4 rewrites. Now it runs
only when a reviewer of the SHIPPED take named a weakness the debate can fix, and that concern —
in the reviewer's own words — becomes the players' brief, so they argue about the problem rather
than about wherever each happens to look:

  * the Producer judged the take weak on how the parts meet (independence, balance, performance or
    the hook at or below `CRAFT_CONCERN_SCORE`) but did not spend a revision on it;
  * Rasik flagged the raga (`second_look.rasik_flags`) and the Producer's second look kept the take.

Measured friction is deliberately NOT a trigger: grinds between the riff and the sitar appear in
every recent song, and Sujit keeps them by ear. Pure.
"""
from __future__ import annotations

from typing import Final, Optional

from crew.contracts import ProducerVerdict, RasikVerdict
from crew.second_look import rasik_flags

CRAFT_CONCERN_SCORE: Final = 3
# The Producer's criteria about how the sitar and the band meet — what the two players can change.
RELATIONSHIP_CRITERIA: Final = ("independence", "balance", "performance", "hook")


def debate_concerns(producer: Optional[ProducerVerdict], rasik: Optional[RasikVerdict]) -> list[str]:
    """The concerns that justify a notes debate on an accepted take, in plain words (empty = no
    debate). Pure."""
    out: list[str] = []
    if producer is not None and producer.decision == "accept":
        low = [c for c in RELATIONSHIP_CRITERIA if (getattr(producer.scores, c) or 5) <= CRAFT_CONCERN_SCORE]
        if low:
            out.append(f"The Producer heard a weakness in {', '.join(low)} — how the sitar and the band "
                       f"meet: {producer.notes}")
    if rasik is not None and rasik_flags(rasik):
        out.append(f"Rasik heard the raga go missing in the sitar line: {rasik.notes}")
    return out
