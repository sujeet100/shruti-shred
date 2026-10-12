"""
The guitar FRETBOARD — where a pitch can be played, and how far the fretting hand must travel.

A raga-legal riff can still be unplayable: a chord shape wider than a hand, or a position
change too far to make in the time between two notes. Whether a human can play a part is a
fact about the instrument, not a matter of taste, so it lives here as data plus pure
functions — the same split as the raga grammar. The riff verifier
(`crew/riff_playability.py`) asks this module the questions; this module knows nothing about
ragas, riffs or agents.

The model is deliberately the plain one a guitar teacher uses: six strings in standard
tuning, one finger per fret, a "position" = the lowest fretted fret (open strings are free —
they need no hand at all). A shape is comfortable when its fretted notes fit a four-fret box;
a move is fast when the next shape sits several frets away.

Pure — no I/O. MIDI note numbers throughout (E2 = 40).
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Final, Optional

# Standard tuning, low to high: E2 A2 D3 G3 B3 E4.
E_STANDARD: Final[tuple[int, ...]] = (40, 45, 50, 55, 59, 64)
LOWEST_OPEN: Final = E_STANDARD[0]
MAX_FRET: Final = 22
# One finger per fret: a shape whose fretted notes span more than this many frets is a stretch.
COMFORTABLE_SPAN: Final = 3


@dataclass(frozen=True)
class Fingering:
    """One way to play a shape: a (string index, fret) per pitch, in the shape's order."""
    frets: tuple[tuple[int, int], ...]

    @property
    def position(self) -> Optional[int]:
        """Where the hand sits — the lowest FRETTED fret; None when every note is open."""
        fretted = [f for _, f in self.frets if f > 0]
        return min(fretted) if fretted else None

    @property
    def span(self) -> int:
        fretted = [f for _, f in self.frets if f > 0]
        return max(fretted) - min(fretted) if fretted else 0


def placements(pitch: int, tuning: tuple[int, ...] = E_STANDARD) -> list[tuple[int, int]]:
    """Every (string, fret) that sounds `pitch`; empty when the guitar cannot reach it."""
    return [(s, pitch - open_) for s, open_ in enumerate(tuning)
            if 0 <= pitch - open_ <= MAX_FRET]


def fingerings(pitches: tuple[int, ...], tuning: tuple[int, ...] = E_STANDARD,
               max_span: int = COMFORTABLE_SPAN) -> list[Fingering]:
    """Every comfortable way to play `pitches` at once: one string per pitch, no string used
    twice, the fretted notes inside a `max_span` box. Empty = no comfortable shape exists."""
    options = [placements(p, tuning) for p in pitches]
    shapes: list[Fingering] = []
    for combo in product(*options):
        strings = [s for s, _ in combo]
        if len(set(strings)) != len(strings):
            continue
        shape = Fingering(tuple(combo))
        if shape.span <= max_span:
            shapes.append(shape)
    return shapes


def shift(a: Fingering, b: Fingering) -> int:
    """How far the hand moves from shape `a` to shape `b`, in frets. Open shapes need no
    hand, so moving to or from one costs nothing — that is what makes an open-string anchor
    the easiest thing on the instrument."""
    if a.position is None or b.position is None:
        return 0
    return abs(a.position - b.position)


def easiest_path(shapes: list[list[Fingering]]) -> Optional[list[Fingering]]:
    """The sequence of fingerings (one per event) that moves the hand least overall — a
    Viterbi pass over each event's options. Ties prefer lower positions (the rhythm-guitar
    home). None when any event has no comfortable fingering at all."""
    if any(not options for options in shapes):
        return None
    if not shapes:
        return []
    costs = [_home_cost(f) for f in shapes[0]]
    back: list[list[int]] = []
    for prev, options in zip(shapes, shapes[1:]):
        step_costs, step_back = [], []
        for f in options:
            best = min(range(len(prev)), key=lambda i: costs[i] + shift(prev[i], f))
            step_costs.append(costs[best] + shift(prev[best], f) + _home_cost(f))
            step_back.append(best)
        costs, back = step_costs, back + [step_back]
    index = min(range(len(costs)), key=costs.__getitem__)
    path = [shapes[-1][index]]
    for step_back, options in zip(reversed(back), reversed(shapes[:-1])):
        index = step_back[index]
        path.append(options[index])
    return list(reversed(path))


def _home_cost(f: Fingering) -> float:
    # A whisker per fret, so among equally still paths the lower position wins.
    return 0.01 * (f.position or 0)
