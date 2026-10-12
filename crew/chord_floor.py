"""
THE CHORD FLOOR — the rhythm guitar holds a slow harmony under the sitar instead of playing its
melody in power chords.

Measured on `fusion_20261012_152048` (2026-10-12): from the head to the antara the riff changed
root 13 times per 16-beat avartan and sat on Sa only 13% of the time — D F G A A G F D, the
melody harmonised note by note in parallel power chords. Sujit: "the chords are not that great".
His own Yaman sitar-metal recording does the opposite (its low end estimated from the audio):
the home root holds more than half the time and leaves only for short excursions. A floor that
stays put is what lets the sitar's melody move against it.

Sujit described what his recording does, and the floor follows it section by section, under
every section the sitar leads (`articulation.sitar_leads`):

  * HOME (`riff_voicing.home_root`, Sa on every raga but Marwa) is SUSTAINED for long — it
    establishes the key and re-emphasises it every time it returns;
  * the MUKHADA has ONE chord pattern, the same in every avartan and on every return of the
    head: home held, then the section's departure in the last vibhag(s), resolving on the next
    sam. The head's harmony is part of its identity, like its melody;
  * the MANJHA and ANTARA MOVE: home for the first vibhag, then the departures vibhag by vibhag
    back to the sam — and the antara's chords sound an octave HIGHER (`lift_antara`, the guitar
    only; the bass stays down and keeps the floor);
  * other sitar-led sections (the outro, a song-form melody) hold home, departing only into the
    sam like the head; a `drone` harmony never departs.

The departures are the section's own harmony plan (`Section.harmony`, the composers' decision):
a `modal_pedal`'s colour roots, a `progression`'s root for that avartan — keeping only roots that
carry a FULL power chord in the raga (root + fifth, `power_weight` 2). Re in Darbari has no fifth,
so it is never a guitar root there, only a melodic note. A departure is skipped where it would
grind (semitone, tritone, major seventh) against a note the sitar HOLDS in that window, or break
the raga's direction rule. Where the sitar is SILENT the riff plays as written — that is where the
guitar answers.

The bass derives from the floored riff, so the low end holds with it. Pitch is re-chosen here —
deliberately, unlike the articulation pass — but only among the composers' own harmony roots and
home; nothing outside the plan is invented. Pure: no LLM, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Sequence

from crew.articulation import sitar_leads
from crew.coexistence import LeadStability, stability_of
from crew.contracts import Arrangement, HarmonyPlan, Layer, Note, Section
from crew.generators import HARSH_INTERVAL_CLASSES, section_spans, sounding_pitch
from crew.riff_voicing import StrokeRole, home_root, power_voicing, power_weight
from raga import RAGAS, SWARAS, direction_violations
from talas import TALAS, vibhag_starts

_EPS: Final = 1e-6
_FULL: Final = 2                       # power_weight: root + fifth
_FIFTH: Final = 7
_PITCH_MOVES: Final = frozenset({"slide", "long_slide", "pick_scrape", "bend",
                                 "hammer_on", "pull_off"})


@dataclass(frozen=True)
class FloorSpan:
    """The root the guitar holds from `start` to `end` (absolute beats)."""
    start: float
    end: float
    root: str


def departure_roots(section: Section, raga: str, bar: int) -> list[str]:
    """The roots one avartan departs through, from the section's harmony plan — only roots that
    carry a full power chord in the raga, never home. Pure."""
    plan = section.harmony or HarmonyPlan()
    home = home_root(raga)
    if plan.mode == "drone":
        return []
    if plan.mode == "progression" and plan.roots:
        roots = [plan.roots[min(len(plan.roots) - 1, bar * len(plan.roots) // section.bars)]]
    else:
        roots = plan.roots or [RAGAS[raga]["samvadi"]]
    return [r for r in dict.fromkeys(roots) if r != home and power_weight(r, raga) == _FULL]


def _grinds(root: str, held: Sequence[Note]) -> bool:
    """Would this root's power chord sound a harsh interval against a held sitar note? (Both
    sides are measured from Sa, so Sa cancels.)"""
    tones = {SWARAS[root] % 12, (SWARAS[root] + _FIFTH) % 12}
    return any((sounding_pitch(n) - t) % 12 in HARSH_INTERVAL_CLASSES
               for n in held for t in tones)


def _held_in(sitar: Sequence[Note], start: float, end: float) -> list[Note]:
    return [n for n in sitar if stability_of(n) is LeadStability.HELD
            and n.start < end - _EPS and start < n.start + n.dur - _EPS]


_MOVING_ROLES: Final = frozenset({"manjha", "antara"})


def _vibhag_beats(arr: Arrangement) -> list[float]:
    """Each vibhag's start within the avartan, in beats."""
    tala = TALAS[arr.tala]
    scale = arr.beats_per_bar / tala["matras"]
    return [(m - 1) * scale for m in vibhag_starts(arr.tala)]


def _pattern(section: Section, bar: int, arr: Arrangement) -> list[tuple[float, str]]:
    """(within-avartan start, root) for one avartan, before the grind/direction guards: home held,
    the departures where the section's role puts them."""
    home = home_root(arr.raga)
    departures = departure_roots(section, arr.raga, bar)
    if not departures:
        return [(0.0, home)]
    vibhags = _vibhag_beats(arr)[1:] or [arr.beats_per_bar / 2]
    if section.form_role in _MOVING_ROLES:
        return [(0.0, home)] + [(v, departures[min(i, len(departures) - 1)])
                                for i, v in enumerate(vibhags)]
    tail = vibhags[-len(departures):]               # the head departs only into the sam
    return [(0.0, home)] + list(zip(tail, departures))


def _avartan(start: float, pattern: list[tuple[float, str]], sitar: Sequence[Note],
             arr: Arrangement) -> list[FloorSpan]:
    """One avartan's floor: each departure kept only where it neither grinds against a held
    sitar note nor breaks the raga's direction rule (else home holds there)."""
    home = home_root(arr.raga)
    ends = [t for t, _ in pattern[1:]] + [arr.beats_per_bar]
    spans = []
    for (t, root), end in zip(pattern, ends):
        a, b = start + t, start + end
        ok = root == home or not _grinds(root, _held_in(sitar, a, b))
        spans.append(FloorSpan(a, b, root if ok else home))
    if direction_violations([(s.root, 0) for s in spans] + [(home, 0)], arr.raga):
        return [FloorSpan(start, start + arr.beats_per_bar, home)]
    return spans


def floor_spans(arr: Arrangement, melody: Sequence[Layer]) -> list[FloorSpan]:
    """The floor under every sitar-led section, avartan by avartan. Pure."""
    sitar = [n for ly in melody for n in (ly.notes or []) if not n.chikari]
    out: list[FloorSpan] = []
    for span in section_spans(arr):
        if not sitar_leads(span.section):
            continue
        for bar in range(span.section.bars):
            start = span.start + bar * arr.beats_per_bar
            out += _avartan(start, _pattern(span.section, bar, arr), sitar, arr)
    return out


def _root_at(t: float, spans: Sequence[FloorSpan]) -> str | None:
    return next((s.root for s in spans if s.start - _EPS <= t < s.end - _EPS), None)


def _sitar_sounding(t: float, sitar: Sequence[Note]) -> bool:
    return any(n.start - _EPS <= t < n.start + n.dur - _EPS for n in sitar)


def reroot(layer: Layer, spans: Sequence[FloorSpan], melody: Sequence[Layer], arr: Arrangement,
           *, octave: int, chords: bool) -> Layer:
    """Every note of `layer` that sounds under the sitar, inside a floor span, re-rooted onto the
    floor at `octave` — rhythm, articulation and velocity kept, a pitch gesture dropped (a held
    floor does not slide), voiced as a power chord when `chords`. Pure."""
    sitar = [n for ly in melody for n in (ly.notes or []) if not n.chikari]
    out: list[Note] = []
    for note in layer.notes or []:
        root = _root_at(note.start, spans)
        if root is None or not _sitar_sounding(note.start, sitar):
            out.append(note)
            continue
        chord = (power_voicing(root, note.dur, arr.raga, StrokeRole.ACCENT) or None) if chords else None
        technique = None if note.technique in _PITCH_MOVES else note.technique
        out.append(note.model_copy(update={"swara": root, "oct": octave, "chord": chord,
                                           "technique": technique}))
    return layer.model_copy(update={"notes": out})


def on_floor(rhythm: Layer | None, melody: Sequence[Layer], arr: Arrangement) -> Layer | None:
    """The rhythm guitar with its roots taken from the floor (see the module docstring). Pure."""
    if rhythm is None or not rhythm.notes:
        return rhythm
    spans = floor_spans(arr, melody)
    if not spans:
        return rhythm
    return reroot(rhythm, spans, melody, arr, octave=arr.registers["rhythm"], chords=True)


def lift_antara(layer: Layer | None, arr: Arrangement) -> Layer | None:
    """The guitar's antara an octave higher — the second movement climbs, and the chords climb
    with it (Sujit's Yaman). Only sitar-led antara sections; the bass is derived before this, so
    it stays down. Pure."""
    if layer is None or not layer.notes:
        return layer
    lifted = [(s.start, s.end) for s in section_spans(arr)
              if s.section.form_role == "antara" and sitar_leads(s.section)]
    if not lifted:
        return layer
    notes = [n.model_copy(update={"oct": n.oct + 1})
             if any(a - _EPS <= n.start < b - _EPS for a, b in lifted) else n
             for n in layer.notes]
    return layer.model_copy(update={"notes": notes})
