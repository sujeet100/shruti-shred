"""
DENSITY CONTRAST — does the lead line BREATHE?

Measured on Sujit's guruji's recorded Darbari gat (2026-10-12, 120 bpm): the right hand is
nearly metronomic — about two strokes a beat throughout — and all the contrast is in the LEFT
hand. 23% of beats are BURSTS of 3-7 swara changes (several swaras on one stroke), each burst
only 1-3 beats long; 53% of beats are STILL (one change or none); and most bursts (12 of 19)
are followed within two beats by a still beat. That alternation — a quick figure, then a note
left to ring — is what a GPT review heard as "rapid figures giving way to longer notes".
The 2026-10-12 Darbari render had the opposite profile: calm on paper (8% busy, 68% still) but
UNIFORM — the hook moved at the same medium rate every beat, the taan ran busy for 16 beats.

A change is counted the way the recording was measured: every new sounding pitch — a struck
note, each kan touch on the way into it, a gesture's trip out to its neighbour and back, a
meend's arrival. A sway (andolan) is not a change. Counted per beat on the absolute grid.

This is a MEASUREMENT reported to the judges (Rasik and the Producer), never a rule: the
reference numbers are one recording at one tempo, and a doom piece at 64 bpm has longer beats.
Pure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from crew.contracts import Arrangement, Composition, Note
from crew.generators import section_spans
from raga import SWARAS

BUSY_MOVES: Final = 3          # a beat with this many swara changes or more is a burst
STILL_MOVES: Final = 1         # a beat with this many or fewer is still
BREATH_WINDOW: Final = 2       # a burst "breathes" when a still beat follows within this many
_LEAD_ROLE: Final = "lead"

# Guruji's recorded Darbari gat (pYIN + onsets, mixed recording — indicative, not exact)
REFERENCE: Final = "guruji's Darbari gat: ~23% busy beats in 1-3 beat bursts, ~53% still, " \
                   "and most bursts followed within two beats by a still beat"


@dataclass(frozen=True)
class DensityProfile:
    """The motion profile of a stretch of the lead, beat by beat."""
    moves: tuple[int, ...]      # swara changes in each beat
    busy_share: float
    still_share: float
    longest_burst: int          # beats in the longest run of busy beats
    bursts: int
    breathed: int               # bursts followed by a still beat within BREATH_WINDOW


def moves_per_beat(notes: list[Note], beats: int) -> list[int]:
    """Swara changes in each beat of the absolute grid, over the whole line."""
    moves = [0] * beats
    prev: int | None = None
    for n in sorted(notes, key=lambda x: x.start):
        beat = int(n.start)
        for pitch in _sounded(n):
            if pitch != prev and 0 <= beat < beats:
                moves[beat] += 1
            prev = pitch
    return moves


def _sounded(n: Note) -> list[int]:
    """The pitches one note sounds, in order: its kan touches, the note, a gesture's
    neighbour and the return, a meend's arrival."""
    home = SWARAS[n.swara] + 12 * n.oct
    pitches = [_nearest(SWARAS[g], home) for g in n.grace or []] + [home]
    if n.pitch_path:
        reach = max((st for _, st in n.pitch_path), key=abs)
        pitches += [home + round(reach), home]
    if n.meend_swara is not None:
        octave = n.meend_oct if n.meend_oct is not None else n.oct
        pitches.append(SWARAS[n.meend_swara] + 12 * octave)
    return pitches


def _nearest(semitone: int, near: int) -> int:
    return semitone + 12 * round((near - semitone) / 12)


def profile(moves: list[int], start: int, end: int) -> DensityProfile:
    """The profile of beats [start, end) — a burst near the end may breathe after it."""
    window = moves[start:end]
    beats = len(window) or 1
    runs: list[tuple[int, int]] = []           # (first beat, length) of each busy run
    i = start
    while i < end:
        if moves[i] >= BUSY_MOVES:
            j = i
            while j < end and moves[j] >= BUSY_MOVES:
                j += 1
            runs.append((i, j - i))
            i = j
        else:
            i += 1
    breathed = sum(1 for first, length in runs
                   if any(m <= STILL_MOVES
                          for m in moves[first + length:first + length + BREATH_WINDOW]))
    return DensityProfile(
        moves=tuple(window),
        busy_share=round(sum(m >= BUSY_MOVES for m in window) / beats, 3),
        still_share=round(sum(m <= STILL_MOVES for m in window) / beats, 3),
        longest_burst=max((length for _, length in runs), default=0),
        bursts=len(runs), breathed=breathed)


def _lead_notes(comp: Composition) -> list[Note]:
    for layer in comp.layers:
        if layer.role == _LEAD_ROLE and layer.notes:
            return list(layer.notes)
    return []


def render_density(comp: Composition, arr: Arrangement) -> str:
    """The prompt block: each lead section's swara changes per beat (grouped by vibhag-sized
    fours) and its burst/breath summary, then the reference. Empty when there is no lead."""
    notes = _lead_notes(comp)
    if not notes:
        return ""
    spans = section_spans(arr)
    moves = moves_per_beat(notes, int(spans[-1].end) + 1)
    lines = ["  - how the lead BREATHES (swara changes per beat — kan, gestures and meends count; "
             f"a burst is {BUSY_MOVES}+, still is {STILL_MOVES} or fewer):"]
    for span in spans:
        start, end = int(span.start), int(span.end)
        if not any(span.start <= n.start < span.end for n in notes):
            continue
        p = profile(moves, start, end)
        grid = " ".join("".join(str(min(m, 9)) for m in p.moves[k:k + 4])
                        for k in range(0, len(p.moves), 4))
        label = span.section.form_role or span.section.kind.value
        bursts = (f"{p.bursts} burst(s), longest {p.longest_burst} beat(s), "
                  f"{p.breathed} followed by a still beat") if p.bursts else "no burst"
        lines.append(f"    section {span.index} ({label}): {grid}  — busy {p.busy_share:.0%}, "
                     f"still {p.still_share:.0%}, {bursts}")
    lines.append(f"    reference — {REFERENCE}. A line at the same density every beat, or "
                 f"busy for many beats with no still beat, does not breathe.")
    return "\n".join(lines)
