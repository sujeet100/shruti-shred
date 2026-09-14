"""
THE HARMONIC GUIDE — one shared answer to "what is the melody doing here?", so the
accompaniment voices stop each inventing a harmonic floor of their own.

Every accompanying voice picks its own sustained tones today, and each picks LEGALLY: the
clean guitar rotates the composers' colour tones over a Sa pedal, the orchestra sustains its
string/choir voicing, the riff stacks raga swaras on its roots. Nothing is wrong with any one
choice. But four voices choosing independently is how a piece ends up sustaining S, P, g, m
and n at once — a modal cluster nobody designed, assembled entirely out of correct decisions.
(The riff's half of this is repaired note-by-note by the Arranger; this is the same question
asked for the voices that HOLD.)

The guide is derived, not decided: for each section it reads what the melody actually settles
on — the notes long enough for the ear to tune to them — and names the raga swaras that would
grind underneath. Accompaniment voices then filter their chosen tones through it. They keep
their own orchestration, register and rhythm; they simply stop sustaining the handful of
pitches that fight the tune.

Two deliberate limits:
  * It only speaks about SUSTAINED tones. A passing dissonance is ordinary music, and a guide
    that policed every eighth note would flatten the writing.
  * It never empties a voice. Filtering always leaves at least one tone (the ground Sa first),
    because a pad that drops out is a worse answer than a pad with one fewer colour.

Pure: no LLM, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from crew.coexistence import LeadStability, stability_of
from crew.contracts import Arrangement, Layer, Note
from crew.generators import HARSH_INTERVAL_CLASSES, section_spans, sounding_pitch
from raga import SWARAS

# The melody notes a harmonic floor must answer to: the ones the ear has time to tune.
_SETTLED = frozenset({LeadStability.HELD, LeadStability.STABLE})


@dataclass(frozen=True)
class HarmonicWindow:
    """What the melody settles on across one section, and what would grind under it."""
    start: float
    end: float
    focus: tuple[str, ...]        # the melody's settled swaras here, most-sustained first
    avoid: frozenset[str]         # swaras that sound a harsh interval against any of them

    def covers(self, start: float) -> bool:
        return self.start <= start < self.end


def _settled_swaras(notes: list[Note]) -> list[str]:
    """The melody's settled swaras, ordered by how long they sound — a note the line rests
    on outranks one it merely pauses on. Uses the SOUNDING pitch, so a meend counts where it
    lands rather than where it was written."""
    weight: dict[str, float] = {}
    for note in notes:
        if stability_of(note) not in _SETTLED:
            continue
        swara = _swara_at(sounding_pitch(note))
        if swara is not None:
            weight[swara] = weight.get(swara, 0.0) + note.dur
    return sorted(weight, key=lambda s: -weight[s])


def _swara_at(pitch: int) -> Optional[str]:
    """The swara name for a sounding pitch (octave-independent)."""
    return next((name for name, semitones in SWARAS.items() if semitones == pitch % 12), None)


def _grinding(focus: list[str]) -> frozenset[str]:
    """Swaras at a harsh interval class from anything the melody settles on."""
    centres = [SWARAS[s] for s in focus]
    return frozenset(name for name, semitones in SWARAS.items()
                     if any((semitones - centre) % 12 in HARSH_INTERVAL_CLASSES
                            for centre in centres))


def harmonic_guide(leads: list[Layer], arr: Arrangement) -> tuple[HarmonicWindow, ...]:
    """One window per section: what the melody settles on, and what must not sustain under
    it. Derived entirely from the realized lead, so it can only be built AFTER the melody
    exists — which is the point. Pure."""
    notes = sorted((n for ly in leads for n in (ly.notes or [])), key=lambda n: n.start)
    windows: list[HarmonicWindow] = []
    for span in section_spans(arr):
        in_span = [n for n in notes if span.start <= n.start < span.end]
        focus = _settled_swaras(in_span)
        windows.append(HarmonicWindow(start=round(span.start, 4), end=round(span.end, 4),
                                      focus=tuple(focus), avoid=_grinding(focus)))
    return tuple(windows)


def avoided_at(guide: tuple[HarmonicWindow, ...], start: float) -> frozenset[str]:
    """What must not sustain at this beat. Empty when no window covers it (no guide, no
    opinion) — an absent guide must never silence a voice."""
    window = next((w for w in guide if w.covers(start)), None)
    return window.avoid if window else frozenset()


def supported(tones: list[str], avoid: frozenset[str]) -> list[str]:
    """Filter a voice's chosen sustained tones through the guide, NEVER to nothing.

    A voice that drops out entirely is a worse answer than one holding a single tone, so
    when every choice grinds the ground Sa is kept if it is among them, else the first tone
    stands. Order is preserved — this removes colours, it does not re-voice the part.
    """
    kept = [t for t in tones if t not in avoid]
    if kept or not tones:
        return kept
    return ["S"] if "S" in tones else tones[:1]
