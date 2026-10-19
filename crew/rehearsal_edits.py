"""
The REHEARSAL's vocabulary — the changes a band tries in the room, applied by code for free
(Sujit, 2026-10-19: "mimic real-life debate, as that is how music making works").

A rehearsal argues over ONE shared song and settles each argument by playing it: "sit out in the
antara", "softer under the alap", "just hit the downbeats and let it ring", "cut the manjha",
"play the mukhada twice". Each is an edit on the realised Composition (and its chart, so the
section map stays true), never a regeneration, so trying an idea costs a render and no model call.

Voices are named the way the band names them (`VOICES_OF`): the sitar includes its chikari, the
guitars are both rhythm takes. Sections are numbered from 1, as the band sees them on the map.
Times are beats, as everywhere in a Composition. Pure.
"""
from __future__ import annotations

from typing import Final, Literal

from pydantic import BaseModel, Field

from crew.contracts import Arrangement, Composition, DrumHit, Layer, Note
from crew.generators import section_spans
from talas import TALAS

EditKind = Literal["sit_out", "louder", "softer", "sparser", "chug", "cut", "repeat"]
# what each change does, as the band is told it (the prompt's vocabulary)
KINDS: Final[dict[str, str]] = {
    "sit_out": "the voice stops playing in those sections (space for the others)",
    "louder": "the voice plays harder in those sections (about +3 dB)",
    "softer": "the voice plays gentler in those sections (about -4 dB)",
    "sparser": "the voice plays only the first note of each vibhag and lets it ring to the next "
               "(no palm-muting): hit and sustain instead of a busy part",
    "chug": "the voice keeps its rhythm but every stroke becomes a palm-muted chug on Sa, the home "
            "note, at its lowest: pulse and weight with no chord changes (a pedal under the melody)",
    "cut": "the sections are removed from the song (every voice)",
    "repeat": "the sections are played twice in a row (every voice)",
}
STRUCTURAL: Final = ("cut", "repeat")
# band name -> the composition roles it covers
VOICES_OF: Final[dict[str, tuple[str, ...]]] = {
    "sitar": ("lead", "chikari"), "guitars": ("rhythm",), "clean_guitar": ("clean",),
    "bass": ("bass",), "drums": ("drums", "tabla"), "drone": ("drone",), "orchestra": ("orchestra",),
}
_LOUDER: Final = 1.25
_SOFTER: Final = 0.65


class Change(BaseModel):
    """One rehearsal change: what, to whom, where (section numbers from 1)."""
    kind: EditKind
    voice: str = Field(description="the band's name for the voice; ignored for cut/repeat")
    sections: list[int] = Field(min_length=1)


def voices(comp: Composition) -> list[str]:
    """The band's names for the voices this composition actually has."""
    roles = {layer.role for layer in comp.layers}
    return [name for name, covers in VOICES_OF.items() if roles & set(covers)]


def change_errors(change: Change, comp: Composition, arr: Arrangement) -> list[str]:
    """What makes a change impossible on this song (empty when it can be tried)."""
    n = len(arr.sections)
    errors = [f"section {s} does not exist (the song has sections 1-{n})" for s in change.sections
              if not 1 <= s <= n]
    if change.kind not in STRUCTURAL and change.voice not in voices(comp):
        errors.append(f"'{change.voice}' is not a voice in this song (voices: {', '.join(voices(comp))})")
    if change.kind == "cut" and len(set(change.sections)) >= n:
        errors.append("cutting every section leaves no song")
    if change.kind in STRUCTURAL and sorted(set(change.sections)) != list(range(min(change.sections),
                                                                               max(change.sections) + 1)):
        errors.append(f"{change.kind} needs consecutive sections")
    return errors


def window(change: Change, arr: Arrangement) -> tuple[float, float]:
    """The change's span in beats: from its first section's start to its last section's end."""
    spans = section_spans(arr)
    return spans[min(change.sections) - 1].start, spans[max(change.sections) - 1].end


def apply_change(change: Change, comp: Composition, arr: Arrangement) -> tuple[Composition, Arrangement]:
    """The song with the change played. Assumes `change_errors` is empty."""
    start, end = window(change, arr)
    if change.kind == "cut":
        return _cut(comp, start, end), _without_sections(arr, change.sections)
    if change.kind == "repeat":
        return _repeat(comp, start, end), _with_repeat(arr, change.sections)
    roles = VOICES_OF[change.voice]
    edit = {"sit_out": lambda ev: _silence(ev, start, end),
            "louder": lambda ev: _scale(ev, start, end, _LOUDER),
            "softer": lambda ev: _scale(ev, start, end, _SOFTER),
            "sparser": lambda ev: _sparse(ev, start, end, _vibhag_starts(arr, start, end)),
            "chug": lambda ev: _chug(ev, start, end)}[change.kind]
    layers = [_edited(layer, edit) if layer.role in roles else layer for layer in comp.layers]
    return comp.model_copy(update={"layers": layers}), arr


def stem(comp: Composition, names: tuple[str, ...]) -> Composition:
    """Only these voices — what a musician hears of their own part in the monitor."""
    roles = {r for n in names for r in VOICES_OF.get(n, ())}
    return comp.model_copy(update={"layers": [layer for layer in comp.layers if layer.role in roles]})


def playing(comp: Composition, arr: Arrangement) -> list[list[str]]:
    """Per section, the voices that actually sound in it (any note overlapping the section — a
    drone held through it counts)."""
    out = []
    for span in section_spans(arr):
        here = [name for name in voices(comp)
                if any(ev.start < span.end and ev.start + ev.dur > span.start for layer in comp.layers
                       if layer.role in VOICES_OF[name] for ev in _events(layer))]
        out.append(here)
    return out


# --------------------------------------------------------------------------- #
# Time edits on one layer's events (notes or drum hits).                      #
# --------------------------------------------------------------------------- #

Event = Note | DrumHit


def _events(layer: Layer) -> list[Event]:
    return list(layer.notes or layer.hits or [])


def _edited(layer: Layer, edit) -> Layer:
    key = "notes" if layer.notes is not None else "hits"
    return layer.model_copy(update={key: edit(_events(layer))})


def _silence(events: list[Event], start: float, end: float) -> list[Event]:
    """Nothing attacks inside the window; a note ringing into it stops at its start; a note held
    through the whole window (the drone) resumes after it."""
    out: list[Event] = []
    for ev in events:
        stop = ev.start + ev.dur
        if start <= ev.start < end:
            continue
        if ev.start < start < stop:
            out.append(ev.model_copy(update={"dur": start - ev.start}))
            if stop > end:
                out.append(ev.model_copy(update={"start": end, "dur": stop - end}))
            continue
        out.append(ev)
    return out


def _scale(events: list[Event], start: float, end: float, factor: float) -> list[Event]:
    return [ev.model_copy(update={"vel": max(1, min(127, round(ev.vel * factor)))})
            if start <= ev.start < end else ev for ev in events]


def _sparse(events: list[Event], start: float, end: float, beats: list[float]) -> list[Event]:
    """Inside the window keep the first attack at or after each vibhag start, ringing to the next
    kept attack (or the window's end); everything else is untouched. Drum hits just thin out."""
    inside = sorted((ev for ev in events if start <= ev.start < end), key=lambda e: e.start)
    kept: list[Event] = []
    for b, nxt in zip(beats, [*beats[1:], end]):
        first = next((ev for ev in inside if b <= ev.start < nxt), None)
        if first is not None:
            kept.append(first)
    rung: list[Event] = []
    for ev, nxt in zip(kept, [*[k.start for k in kept[1:]], end]):
        update = {"dur": nxt - ev.start}
        if isinstance(ev, Note):
            update["technique"] = None
        rung.append(ev if isinstance(ev, DrumHit) else ev.model_copy(update=update))
    return [ev for ev in events if not start <= ev.start < end] + rung


def _chug(events: list[Event], start: float, end: float) -> list[Event]:
    """Inside the window every note keeps its attack and length but sounds Sa at the window's
    lowest octave, chordless and palm-muted — a pedal. Drum hits are left as they are."""
    notes = [ev for ev in events if isinstance(ev, Note) and start <= ev.start < end]
    floor = min((n.oct for n in notes), default=0)
    pedal = {"swara": "S", "oct": floor, "chord": None, "technique": "palm_mute", "meend_swara": None,
             "meend_oct": None, "bend_st": None, "grace": None}
    return [ev.model_copy(update=pedal) if isinstance(ev, Note) and start <= ev.start < end else ev
            for ev in events]


def _vibhag_starts(arr: Arrangement, start: float, end: float) -> list[float]:
    groups = TALAS[arr.tala]["vibhags"]
    offsets, t = [], 0.0
    for g in groups:
        offsets.append(t)
        t += g * arr.beats_per_bar / sum(groups)
    beats, bar = [], start
    while bar < end - 1e-9:
        beats += [bar + o for o in offsets if bar + o < end - 1e-9]
        bar += arr.beats_per_bar
    return beats


def _cut(comp: Composition, start: float, end: float) -> Composition:
    gap = end - start

    def cut(events: list[Event]) -> list[Event]:
        out: list[Event] = []
        for ev in events:
            stop = ev.start + ev.dur
            if start <= ev.start < end:
                continue
            if ev.start < start:
                held = stop - gap if stop > end else min(stop, start)
                out.append(ev.model_copy(update={"dur": held - ev.start}))
            else:
                out.append(ev.model_copy(update={"start": ev.start - gap}))
        return out
    return comp.model_copy(update={"layers": [_edited(layer, cut) for layer in comp.layers]})


def _repeat(comp: Composition, start: float, end: float) -> Composition:
    gap = end - start

    def repeat(events: list[Event]) -> list[Event]:
        out: list[Event] = []
        for ev in events:
            stop = ev.start + ev.dur
            if start <= ev.start < end:
                first = ev.model_copy(update={"dur": min(ev.dur, end - ev.start)}) if stop > end else ev
                out += [first, ev.model_copy(update={"start": ev.start + gap})]
            elif ev.start >= end:
                out.append(ev.model_copy(update={"start": ev.start + gap}))
            elif stop > start:                              # held through: hold it through both
                out.append(ev.model_copy(update={"dur": ev.dur + gap}))
            else:
                out.append(ev)
        return out
    return comp.model_copy(update={"layers": [_edited(layer, repeat) for layer in comp.layers]})


def _without_sections(arr: Arrangement, numbers: list[int]) -> Arrangement:
    drop = {n - 1 for n in numbers}
    return arr.model_copy(update={"sections": [s for i, s in enumerate(arr.sections) if i not in drop]})


def _with_repeat(arr: Arrangement, numbers: list[int]) -> Arrangement:
    lo, hi = min(numbers) - 1, max(numbers)
    sections = list(arr.sections)
    return arr.model_copy(update={"sections": sections[:hi] + sections[lo:hi] + sections[hi:]})
