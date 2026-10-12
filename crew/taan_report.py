"""
THE TAAN, MEASURED — does the climax climb late and run straight into the sam?

Sujit's review of fusion_20261012_213455 (2026-10-12): the taan reached its top note early, spent
the rest descending, struck one low note again and again (a forced tihai), and stopped 1.75 s
before the returning mukhada's sam. Each of those is a fact the score shows, so code measures it
and the Producer judges with it (the same contract as `crew/density.py` — reported, never a
rejection; the hard limits live in `gat_verifier.check_taan`):

  * PEAK — where the highest note arrives (share of the taan) and in which octave;
  * MOMENTUM — notes per beat in the first half against the second (does the run gather speed?);
  * FLOW — the share of the taan's time on notes of a beat or longer, and how many such holds
    stall the run mid-flight (the 2026-10-13 review: half the 233435 taan sat on held notes, so
    its fast clusters read as disconnected phrases);
  * GAP — silence between the taan's last note and the next sam;
  * ARRIVAL — how far its last note is from the returning head's first swara (ladder steps);
  * TIHAI — whether it ends on one phrase stated three times.

Pure: the placed composition in, text out.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from crew.contracts import Arrangement, Composition, Note
from crew.generators import section_spans
from raga import RAGAS, SWARAS

_LEAD: Final = "lead"
_EPS: Final = 1e-6
_MIN_STATEMENT: Final = 2
_HELD_BEATS: Final = 1.0     # a note this long stops a run


@dataclass(frozen=True)
class TaanFacts:
    index: int
    peak_at: float          # share of the taan elapsed when its highest note sounds
    peak: str               # that note, e.g. "g'" (taar)
    density_first: float    # notes per beat, first half
    density_second: float  # ...second half
    held_share: float       # share of the taan's sounding time on notes of a beat or longer
    stalls: int             # such held notes with more of the run after them
    gap_beats: float        # silence before the next sam
    arrival_steps: int | None   # ladder steps from the last note to the next head's first swara
    tihai: bool


def _sitar(comp: Composition) -> list[Note]:
    lead = next((ly for ly in comp.layers if ly.role == _LEAD and ly.instrument == "sitar"), None)
    return sorted((n for n in (lead.notes if lead else []) if not n.chikari), key=lambda n: n.start)


def _pitch(n: Note) -> int:
    return SWARAS[n.swara] + 12 * n.oct


def _tripled(notes: list[Note]) -> bool:
    """Does the line end on one phrase (of 2+ notes) stated three times?"""
    pitches = [(n.swara, n.oct) for n in notes]
    for size in range(_MIN_STATEMENT, len(pitches) // 3 + 1):
        tail = pitches[-3 * size:]
        if tail[:size] == tail[size:2 * size] == tail[2 * size:]:
            return True
    return False


def _steps(a: str, b: str, raga: str) -> int:
    ladder = [sw for sw in sorted(RAGAS[raga]["allowed"], key=lambda sw: SWARAS[sw])]
    if a not in ladder or b not in ladder:
        return 99
    gap = abs(ladder.index(a) - ladder.index(b))
    return min(gap, len(ladder) - gap)


def _held_share(notes: list[Note]) -> float:
    total = sum(n.dur for n in notes)
    return sum(n.dur for n in notes if n.dur >= _HELD_BEATS - _EPS) / total if total else 0.0


def _stalls(notes: list[Note]) -> int:
    """Held notes the run has to restart after (the last note may ring into the sam)."""
    return sum(1 for n in notes[:-1] if n.dur >= _HELD_BEATS - _EPS)


def taan_facts(comp: Composition, arr: Arrangement) -> list[TaanFacts]:
    """The facts of every taan_long the piece plays. Pure."""
    sitar = _sitar(comp)
    spans = section_spans(arr)
    out = []
    for k, span in enumerate(spans):
        if span.section.form_role != "taan_long":
            continue
        inside = [n for n in sitar if span.start - _EPS <= n.start < span.end - _EPS]
        if not inside:
            continue
        top = max(inside, key=_pitch)
        mid = span.start + span.length / 2
        half = span.length / 2
        following = next((n for n in sitar if n.start >= span.end - _EPS), None)
        next_is_head = k + 1 < len(spans) and spans[k + 1].section.form_role == "mukhada"
        arrival = (_steps(inside[-1].swara, following.swara, arr.raga)
                   if next_is_head and following is not None else None)
        mark = "'" if top.oct > 0 else ("." if top.oct < 0 else "")
        out.append(TaanFacts(
            index=span.index, peak_at=(top.start - span.start) / span.length, peak=top.swara + mark,
            density_first=sum(1 for n in inside if n.start < mid) / half,
            density_second=sum(1 for n in inside if n.start >= mid) / half,
            held_share=_held_share(inside), stalls=_stalls(inside),
            gap_beats=max(0.0, span.end - max(n.start + n.dur for n in inside)),
            arrival_steps=arrival, tihai=_tripled(inside)))
    return out


def render_taan(comp: Composition, arr: Arrangement) -> str:
    """The Producer's prompt block, or "" when the piece has no taan_long. Pure."""
    facts = taan_facts(comp, arr)
    if not facts:
        return ""
    seconds = 60.0 / arr.bpm
    lines = ["  - THE TAAN (the climax) — where it peaks, whether it gathers speed, how it arrives:"]
    for f in facts:
        arrival = ("" if f.arrival_steps is None else
                   f"; its last note is {f.arrival_steps} step(s) from the returning head's first "
                   f"swara")
        lines.append(f"    section {f.index}: highest note {f.peak} at {f.peak_at:.0%} of the taan; "
                     f"{f.density_first:.1f} notes/beat in the first half, {f.density_second:.1f} "
                     f"in the second; {f.held_share:.0%} of its time on notes of a beat or "
                     f"longer, {f.stalls} mid-run hold(s); {f.gap_beats * seconds:.2f} s of "
                     f"silence before the next sam"
                     f"{arrival}; {'ENDS ON A TIHAI' if f.tihai else 'no tihai'}")
    lines.append("    how to read it: a climax peaks LATE (past ~60%) in the taar, gathers speed "
                 "into the end, and arrives on the sam with no silence — the returning head's "
                 "first note its resolution. A taan FLOWS: little time on held notes and few "
                 "mid-run holds, so it reads as one run, not fast clusters joined by pauses. An "
                 "early peak followed by descent, a run that thins out or keeps stopping, or a "
                 "gap before the sam is NOT a high climax score.")
    return "\n".join(lines)
