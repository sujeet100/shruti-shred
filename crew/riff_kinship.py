"""RIFF ↔ HEAD KINSHIP — does the guitar riff come from the sitar's mukhada?

The derivation (`crew/riff_from_mukhada.py`) makes the head riff by construction, but a judge
still has to HEAR whether riff and head read as one idea: a revise may rewrite the slot, a contrast
section departs on purpose, and a riff_first piece runs the other way round. So the relationship is
MEASURED on the realised score and reported to the Producer — the judge decides; code never rejects
on it (the same contract as `crew/density.py`).

Per section that plays the rhythm guitar, per avartan, against the head's anatomy
(`crew/head_anatomy.py`):

  * rhythm    — share of the head's plucks (every stroke of every bol) the riff also strikes;
  * accents   — share of the head's accented notes (on the sam and talis) the riff strikes on the
                same swara at the same matra;
  * structure — share of the head's structural notes the riff sounds as a root at their onset.

Swaras are compared without octave (the riff is seated low on purpose). The head is the chart's
`seed_hook` (the Flow stores the realised head there before the critics run). `extra_onsets` is the
seam for the sitar's chikari strokes: they join the head's rhythm when another layer exposes them.
Pure.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from crew.contracts import Arrangement, Composition, Note
from crew.generators import section_spans
from crew.head_anatomy import accent_beats, accented_notes, head_anatomy, head_onsets, structural_notes
from crew.riff_from_mukhada import guitar_led

_RHYTHM: Final = "rhythm"
_GRID: Final = 3                     # onsets compared to a thousandth of a beat


@dataclass(frozen=True)
class SectionKinship:
    """How much of the head one section's riff carries (each a share in [0, 1])."""
    index: int
    label: str
    under_sitar: bool
    rhythm: float
    accents: float
    structure: float


def _riff_notes(comp: Composition) -> list[Note]:
    """The rhythm guitar as written — the FIRST rhythm layer (the double track is a copy)."""
    return next((list(layer.notes) for layer in comp.layers
                 if layer.role == _RHYTHM and layer.notes), [])


def _strikes(notes: list[Note], start: float, cycle: float) -> dict[float, str]:
    """Within-cycle onset -> the root swara struck there, for one avartan from `start`."""
    return {round(n.start - start, _GRID): n.swara for n in notes
            if start - 1e-6 <= n.start < start + cycle - 1e-6}


def _share(hits: int, total: int) -> float:
    return round(hits / total, 3) if total else 0.0


def kinship_report(comp: Composition, arr: Arrangement,
                   extra_onsets: Sequence[float] = ()) -> list[SectionKinship]:
    """Each rhythm section's kinship with the head, averaged over its avartans. Empty when the
    chart carries no head or the piece has no rhythm guitar. Pure."""
    riff = _riff_notes(comp)
    if arr.seed_hook is None or not riff:
        return []
    cycle = arr.beats_per_bar
    anatomy = head_anatomy(arr.seed_hook, cycle_beats=cycle, accents=accent_beats(arr))
    plucks = [round(o, _GRID) for o in head_onsets(anatomy, extra_onsets)]
    accented = [(round(n.onset, _GRID), n.swara) for n in accented_notes(anatomy)]
    structural = [(round(n.onset, _GRID), n.swara) for n in structural_notes(anatomy)]
    report: list[SectionKinship] = []
    for span in section_spans(arr):
        if _RHYTHM not in span.section.layers:
            continue
        bars = [_strikes(riff, span.start + bar * cycle, cycle) for bar in range(span.section.bars)]
        rhythm = sum(_share(sum(o in b for o in plucks), len(plucks)) for b in bars)
        accents = sum(_share(sum(b.get(o) == sw for o, sw in accented), len(accented)) for b in bars)
        structure = sum(_share(sum(b.get(o) == sw for o, sw in structural), len(structural))
                        for b in bars)
        count = len(bars)
        report.append(SectionKinship(
            index=span.index, label=span.section.form_role or span.section.kind.value,
            under_sitar=not guitar_led(span.section), rhythm=round(rhythm / count, 3),
            accents=round(accents / count, 3), structure=round(structure / count, 3)))
    return report


def render_kinship(comp: Composition, arr: Arrangement) -> str:
    """The Producer's prompt block, or "" when there is nothing to compare. Pure."""
    rows = kinship_report(comp, arr)
    if not rows:
        return ""
    lines = ["  - riff ↔ gat-head KINSHIP (does the guitar riff grow out of the sitar's mukhada? "
             "shares of the head's plucks / accented swaras / structural swaras the riff strikes "
             "at the same matra, per avartan):"]
    for row in rows:
        where = "under the sitar" if row.under_sitar else "guitar-led"
        lines.append(f"    section {row.index} ({row.label}, {where}): rhythm {row.rhythm:.0%}, "
                     f"accents {row.accents:.0%}, structure {row.structure:.0%}")
    lines.append("    how to read it: a guitar statement grown from the head keeps its accents and "
                 "most of its rhythm; later statements may loosen (heavier, a pedal, a push); under "
                 "the sitar the riff thins to the accents. Low everywhere means riff and head are "
                 "two separate ideas — a deliberate contrast or a seam that interrupts; you decide.")
    return "\n".join(lines)
