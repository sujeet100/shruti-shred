"""
The gat head, measured against the raga facts its prompt already states — the input to ONE
self-revision (Sujit's control run, 2026-10-19; TALK.md "The rival added nothing").

Ten first-draft heads were told, in the prompt, that Darbari lives in the mandra and madhya and to
DWELL below Sa; the most any of them spent there was 19%. Shown a measurement of its OWN draft
(0% below Sa), the composer moved into the mandra on the first revision — with a rival in the room
(the head debate) or without one (the control), identically. A stated fact was ignored; a measured
fault on the composer's own work was acted on. That is self-correction from code, applied to craft.

So this module measures the three facts a head can be checked against, each only where the raga
has a sourced entry: where it LIVES (`raga.REGISTER`), its own PHRASES (pakad or chalan, fuzzy as Rasik's pakad), and
— in a slow gat — one held ANDOLIT swara long enough to sway its counted swings. A finding is a
report, never a rejection: an unmet one earns the composer one revision pass, and
`revision_kept` keeps that revision only when it fixes something without breaking what the draft
had (the control's B head chased "0% below Sa" to 94% and lost the madhya: a fault traded, not
fixed). Pure.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

from crew.contracts import LeadPhrase
from crew.rasik import match_phrase
from gats import is_vilambit
from raga import ANDOLAN_SWINGS, RAGAS, REGISTER
from render import counted_hold_ms

# A saptak the raga lives in is VISITED when it holds this share of the head's sounding time —
# a fifth of the avartan, so a single passing note doesn't count and neither register can be
# traded away for the other. Inference, not a sourced number: calibrate it by ear.
REGISTER_VISIT_SHARE: Final = 0.2
_SAPTAK_OF: Final = {-1: "mandra", 0: "madhya", 1: "taar"}


@dataclass(frozen=True)
class HeadFinding:
    """One fact the head can be measured against: the fact as sourced, what code measured, met?"""
    name: str
    fact: str
    measured: str
    met: bool


def head_findings(head: LeadPhrase, raga: str, bpm: float) -> list[HeadFinding]:
    """Every finding that applies to this raga at this tempo (none for a raga with no entries)."""
    found = [_register(head, raga), _phrases(head, raga), _andolan(head, raga, bpm)]
    return [f for f in found if f is not None]


def unmet(findings: list[HeadFinding]) -> list[HeadFinding]:
    return [f for f in findings if not f.met]


def revision_kept(draft: list[HeadFinding], revised: list[HeadFinding]) -> bool:
    """Keep a revision only when it meets a fact the draft missed and misses none the draft met."""
    was = {f.name: f.met for f in draft}
    now = {f.name: f.met for f in revised}
    fixed = any(now.get(name) and not met for name, met in was.items())
    broke = any(met and not now.get(name, False) for name, met in was.items())
    return fixed and not broke


def render_head_report(findings: list[HeadFinding]) -> str:
    """The measurements as the revision prompt shows them: the fact, then what code measured."""
    return "\n".join(f"  {'met   ' if f.met else 'MISSED'}  {f.name}: {f.fact}\n"
                     f"          measured: {f.measured}" for f in findings)


def _saptak_shares(head: LeadPhrase) -> dict[str, float]:
    sounding = [n for n in head.notes if not n.rest]
    total = sum(n.dur for n in sounding) or 1.0
    shares = dict.fromkeys(_SAPTAK_OF.values(), 0.0)
    for n in sounding:
        shares[_SAPTAK_OF[max(-1, min(1, n.oct))]] += n.dur / total
    return shares


def _register(head: LeadPhrase, raga: str) -> HeadFinding | None:
    entry = REGISTER.get(raga)
    if entry is None:
        return None
    lives = entry["saptak"]
    shares = _saptak_shares(head)
    fact = (f"the raga is developed in the {' and '.join(s.upper() for s in lives)}; each it lives in "
            f"wants at least {REGISTER_VISIT_SHARE:.0%} of the head")
    measured = ", ".join(f"{s} {shares[s]:.0%}" for s in _SAPTAK_OF.values())
    return HeadFinding("register", fact, measured,
                       all(shares[s] >= REGISTER_VISIT_SHARE for s in lives))


def _phrases(head: LeadPhrase, raga: str) -> HeadFinding | None:
    """Does the head carry one of the raga's own phrases — a pakad or a chalan phrase, grace notes
    allowed? Chalan counts because a whole 7-9 note pakad rarely fits one head: measured on the
    pakad alone, the control's best revision (both of Darbari's cells, g m R S and d n P) read as
    a loss, and a head transposed whole into the mandra read as a gain."""
    phrases = [*(RAGAS[raga].get("pakad") or []), *(RAGAS[raga].get("chalan") or [])]
    if not phrases:
        return None
    loop = [n.swara for n in head.notes if not n.rest]
    loop += loop[:1]                                   # the head returns to its first note on the sam
    found = [" ".join(p) for p in phrases if match_phrase(loop, p) != "absent"]
    return HeadFinding("phrases", "the head carries one of the raga's pakad or chalan phrases (grace notes allowed)",
                       f"carries [{'], ['.join(found)}]" if found else "none of them", bool(found))


def _andolan(head: LeadPhrase, raga: str, bpm: float) -> HeadFinding | None:
    swaras = RAGAS[raga].get("andolan") or []
    swings = ANDOLAN_SWINGS.get(raga)
    if not swaras or swings is None or not is_vilambit(bpm):
        return None
    hold = float(math.ceil(counted_hold_ms(swings, most=True) * bpm / 60000.0))
    held = [n for n in head.notes if not n.rest and n.swara in swaras and n.dur >= hold]
    longest = max((n.dur for n in head.notes if not n.rest and n.swara in swaras), default=0.0)
    return HeadFinding("andolan", f"at this slow tempo a held {' or '.join(swaras)} needs {hold:g} beats to "
                                  f"sway {swings[0]}-{swings[1]} times",
                       f"longest {'/'.join(swaras)}: {longest:g} beats", bool(held))
