"""
The ENDING — how the piece stops, decided by the composers and realised by code.

Until now every piece simply ran out: the last section's notes ended and the renderer's tail
decayed. A metal ending is an EVENT — the band lands one stroke together on the sam and then
there is silence — and the tihai the taan already closes with is built to land exactly there:
its third statement ends at the section's end, so the sam it lands on is the beat right after
the last section. `hard_stop` puts the arrival on that beat:

  * the lead lands on TAAR Sa (one octave above its home) — the melody resolves upward;
  * the rhythm guitar (both takes) and the bass strike LOW Sa underneath, the guitar as a
    power chord (Sa + its octave, plus Pa where the raga has one);
  * the kit hits kick and crash together;
  * every other voice has already stopped, and nothing sounds after the stroke.

`ring_out` stays the default. It used to mean "do nothing", which was not a ring-out: every
sustaining voice was written to stop on the final beat, so drone, sitar, guitars and bass all
released together at full level and the file fell ~60 dB in a quarter-second (the listening
pass heard "an unnatural cut" on `fusion_20261012_112714`). Now each sustained note still
sounding at the end rings `RING_TAIL_S` past it and its expression decays across that tail
only (`Note.fade_tail`); a palm-muted chug cannot ring, so it is left as written.
The composers choose (a closed Literal on the draft); code places every note, because "land
on the sam together" is timing arithmetic, not taste.

Pure — no LLM, no I/O. Legal by construction: Sa always, Pa only where the raga allows it.
"""

from __future__ import annotations

from typing import Final, Optional

from crew.contracts import RHYTHM_FLOOR, Arrangement, DrumHit, Layer, Note
from crew.generators import total_beats
from raga import RAGAS

_HIT_BEATS: Final = 1.0      # the final stroke's length — a struck chord, then silence
RING_TAIL_S: Final = 3.0     # a ring-out's decay past the last beat (inference, for the ear)
_HIT_VEL: Final = 124        # everyone lands it hard
_BASS_FLOOR: Final = -3      # never below ~D1 (same floor as the bass generator)
_LEAD_ROLE: Final = "lead"
_RHYTHM_ROLE: Final = "rhythm"
_BASS_ROLE: Final = "bass"
_DRUMS_ROLE: Final = "drums"
_EPS: Final = 1e-6


def apply_ending(layers: list[Layer], arr: Arrangement) -> list[Layer]:
    """Realise the chart's ending. `ring_out` lets whatever still sounds at the end decay
    past it; `hard_stop` adds the final stroke on the landing sam and silences everything
    after it."""
    if arr.ending != "hard_stop":
        return [_rung_out(layer, total_beats(arr), RING_TAIL_S * arr.bpm / 60.0)
                for layer in layers]
    sam = total_beats(arr)
    final_cycle = sam - arr.beats_per_bar
    leads = [la for la in layers if la.role == _LEAD_ROLE and la.notes]
    landing_leads = [la for la in leads if _sounds_after(la, final_cycle)] or leads[:1]
    out: list[Layer] = []
    for layer in layers:
        clipped = _clip(layer, sam)
        stroke = _stroke_for(clipped, arr, sam, lands=any(la is layer for la in landing_leads))
        out.append(_with_stroke(clipped, stroke))
    return out


def _rung_out(layer: Layer, end: float, tail: float) -> Layer:
    """Every sustained note sounding at `end` (or struck on it — a tihai's landing) holds to
    `end + tail` and fades across the part after `end`."""
    if not layer.notes:
        return layer
    final = end + tail
    notes = [n.model_copy(update={"dur": round(final - n.start, 4),
                                  "fade_tail": round(final - max(n.start, end), 4)})
             if n.start + n.dur >= end - _EPS and n.technique != "palm_mute" else n
             for n in layer.notes]
    return layer.model_copy(update={"notes": notes})


def _sounds_after(layer: Layer, t: float) -> bool:
    return any(n.start + n.dur > t + _EPS for n in layer.notes or [])


def _clip(layer: Layer, end: float) -> Layer:
    """Nothing written may sound past the landing sam: notes that start there are dropped,
    notes that straddle it are cut at it."""
    update: dict = {}
    if layer.notes is not None:
        update["notes"] = [n if n.start + n.dur <= end + _EPS
                           else n.model_copy(update={"dur": round(end - n.start, 4)})
                           for n in layer.notes if n.start < end - _EPS]
    if layer.hits is not None:
        update["hits"] = [h for h in layer.hits if h.start < end - _EPS]
    return layer.model_copy(update=update) if update else layer


def _stroke_for(layer: Layer, arr: Arrangement, sam: float, *,
                lands: bool) -> Optional[list[Note] | list[DrumHit]]:
    """What this layer plays on the landing sam, or None when it is not part of the stroke."""
    if layer.role == _LEAD_ROLE and lands:
        taar = arr.registers.get(_LEAD_ROLE, 0) + 1
        return [Note(swara="S", oct=taar, start=sam, dur=_HIT_BEATS, vel=_HIT_VEL)]
    if layer.role == _RHYTHM_ROLE:
        return [Note(swara="S", oct=_rhythm_low(layer, arr), start=sam, dur=_HIT_BEATS,
                     vel=_HIT_VEL, chord=_power_chord(arr.raga))]
    if layer.role == _BASS_ROLE:
        return [Note(swara="S", oct=_bass_low(layer, arr), start=sam, dur=_HIT_BEATS,
                     vel=_HIT_VEL)]
    if layer.role == _DRUMS_ROLE:
        return [DrumHit(drum="kick", start=sam, dur=_HIT_BEATS, vel=127),
                DrumHit(drum="crash", start=sam, dur=_HIT_BEATS, vel=127)]
    return None


def _with_stroke(layer: Layer, stroke) -> Layer:
    if not stroke:
        return layer
    if isinstance(stroke[0], DrumHit):
        return layer.model_copy(update={"hits": [*(layer.hits or []), *stroke]})
    return layer.model_copy(update={"notes": [*(layer.notes or []), *stroke]})


def _power_chord(raga: str) -> list[str]:
    """Sa's octave always; Pa (the fifth) only where the raga admits it — Malkauns and Marwa
    have none, and an illegal chord tone would be a forced revise."""
    return ["S", "P"] if "P" in RAGAS[raga]["allowed"] else ["S"]


def _lowest_sa(layer: Layer) -> Optional[int]:
    octaves = [n.oct for n in layer.notes or [] if n.swara == "S"]
    return min(octaves) if octaves else None


def _rhythm_low(layer: Layer, arr: Arrangement) -> int:
    """The riff's own lowest Sa — on an E-standard guitar in E, the open low string."""
    low = _lowest_sa(layer)
    if low is not None:
        return low
    return max(arr.registers.get(_RHYTHM_ROLE, RHYTHM_FLOOR), RHYTHM_FLOOR)


def _bass_low(layer: Layer, arr: Arrangement) -> int:
    low = _lowest_sa(layer)
    if low is not None:
        return low
    return max(arr.registers.get(_RHYTHM_ROLE, RHYTHM_FLOOR) - 1, _BASS_FLOOR)
