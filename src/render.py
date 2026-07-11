"""
Composition -> MIDI -> WAV renderer.

A composition is plain data (swaras + timing) — exactly what a Gemini agent
will emit. This module is deterministic: no LLM, no randomness. The agents
decide *what* to play; this decides *how it sounds*.

Composition schema:
{
  "raga": "bhairav", "sa": 60, "bpm": 140,
  "tala": {"name": "rupak", "beats_per_bar": 3.5},
  "layers": [
    {"role": "drone"|"lead"|"rhythm", "instrument": str, "program": int,
     "channel": int, "notes": [{"swara": "S", "oct": 0, "start": 0.0,
                                "dur": 0.5, "vel": 100,
                                "grace": ["R"]}, ...]},   # "grace" is OPTIONAL
    {"role": "drums", "channel": 9,
     "hits": [{"drum": "kick"|"snare"|"hhat", "start": 0.0, "dur": 0.2, "vel": 100}]},
  ]
}
Pitch = sa + semitone(swara) + 12 * oct   (oct is octave offset from Sa).
Times are in quarter-note beats.

Grace notes (kan): a note may carry an optional "grace" list of swaras. Each is
rendered as a short, softer note crushed into the window just BEFORE the main
note's onset — the discrete-MIDI stand-in for a Hindustani kan (a quick adjacent
touch that leans into the main swara, e.g. Darbari's Ga touched with a hint of
Re). Grace swaras inherit the main note's octave.

Meend (glide): a note may carry an optional "meend" target swara (a string, or
{"swara","oct"} to cross octaves). The note sounds its own swara, then bends
CONTINUOUSLY to the target across its duration — a true portamento, rendered
with MIDI pitch-bend. Because pitch-bend is channel-wide, meend only works on a
MONOPHONIC melodic channel (lead lines are); it is not for the drone or drums.

Both kan and meend endpoints are validated by the raga grammar like any other
pitch. The continuous pitches a meend sweeps THROUGH are deliberately not
validated — sliding through microtones between two legal swaras is what a meend
is, not a grammar violation.
"""

import subprocess
from midiutil import MIDIFile
from raga import SWARAS

# GM percussion voices (channel 9). The metal kit the groove engine draws from (a
# subgenre's drum vocabulary may only name kit keys), plus two conga voices that
# stand in for the tabla — GM has no tabla, so Low/Open-Hi Conga approximate the
# bayan (bass, left hand) and dayan (treble, right hand). Both the metal kit and the
# tabla share channel 9 (they are all GM percussion) and simply mix.
DRUMS = {
    "kick": 36,     # Bass Drum 1
    "snare": 38,    # Acoustic Snare
    "hhat": 42,     # Closed Hi-Hat
    "ohat": 46,     # Open Hi-Hat
    "crash": 49,    # Crash Cymbal 1
    "ride": 51,     # Ride Cymbal 1
    "china": 52,    # Chinese Cymbal (the metal "trash" accent)
    "tom_hi": 50,   # High Tom
    "tom_mid": 47,  # Low-Mid Tom
    "tom_lo": 45,   # Low Tom
    "tabla_lo": 64,  # Low Conga     — bayan (tabla bass) stand-in
    "tabla_hi": 63,  # Open Hi Conga — dayan (tabla treble) stand-in
}
GRACE_LEN = 0.15         # beats: total window a note's kan ornament occupies before it
MEEND_RANGE = 12         # semitones of pitch-bend range we arm the channel with (±octave)
MEEND_GLIDE_FRAC = 0.6   # glide over the first 60% of the note, then hold the target


def _resolve(spec, default_oct: int):
    """A swara spec is either 'P' (inherits octave) or {'swara','oct'}."""
    if isinstance(spec, dict):
        return spec["swara"], spec.get("oct", default_oct)
    return spec, default_oct


def _arm_bend_range(mf: MIDIFile, track: int, ch: int, semitones: int) -> None:
    """Widen a channel's pitch-bend range via RPN 0,0 so meend can span >2 semitones."""
    mf.addControllerEvent(track, ch, 0, 101, 0)          # RPN MSB
    mf.addControllerEvent(track, ch, 0, 100, 0)          # RPN LSB -> RPN(0,0) = bend range
    mf.addControllerEvent(track, ch, 0, 6, semitones)    # data entry MSB = semitones
    mf.addControllerEvent(track, ch, 0, 38, 0)           # data entry LSB = cents


def _render_meend(mf: MIDIFile, track: int, ch: int, start: float, dur: float,
                  from_pitch: int, to_pitch: int) -> None:
    """Ramp the pitch wheel from `from_pitch` to `to_pitch`, then recenter at note end."""
    interval = to_pitch - from_pitch                     # signed semitones
    full = max(-8192, min(8191, round(interval / MEEND_RANGE * 8191)))
    glide = dur * MEEND_GLIDE_FRAC
    steps = max(6, min(48, int(glide / 0.02)))           # ~1 event per 0.02 beat, capped
    for k in range(steps + 1):
        t = start + glide * k / steps
        mf.addPitchWheelEvent(track, ch, round(t, 4), round(full * k / steps))
    # hold the target for the rest of the note, then recenter for the next note
    mf.addPitchWheelEvent(track, ch, round(start + dur, 4), 0)


def build_midi(comp: dict, path: str) -> None:
    layers = comp["layers"]
    mf = MIDIFile(numTracks=len(layers), deinterleave=False)
    for i in range(len(layers)):
        mf.addTempo(i, 0, comp["bpm"])
    sa = comp["sa"]
    for i, layer in enumerate(layers):
        # Percussion layers (the metal kit and the tabla) carry hits, not pitched
        # notes, and both live on GM channel 9.
        if layer.get("role") in ("drums", "tabla"):
            for h in layer["hits"]:
                mf.addNote(i, 9, DRUMS[h["drum"]], h["start"], h.get("dur", 0.2), h.get("vel", 100))
            continue
        ch = layer["channel"]
        if "program" in layer:
            mf.addProgramChange(i, ch, 0, layer["program"])
        # If any note on this channel glides, arm a wide bend range once up front.
        if any("meend" in n for n in layer["notes"]):
            _arm_bend_range(mf, i, ch, MEEND_RANGE)
        for n in layer["notes"]:
            oct = n.get("oct", 0)
            vel = n.get("vel", 100)
            # Kan: crushed grace notes stolen from just before the main onset.
            grace = n.get("grace")
            if grace:
                span = min(GRACE_LEN, n["start"])  # never start before beat 0
                if span > 0:
                    each = span / len(grace)
                    gvel = max(1, int(vel * 0.7))   # kan is softer than the note
                    for j, gsw in enumerate(grace):
                        gp = sa + SWARAS[gsw] + 12 * oct
                        mf.addNote(i, ch, gp, round(n["start"] - span + j * each, 4),
                                   each * 0.9, gvel)
            pitch = sa + SWARAS[n["swara"]] + 12 * oct
            mf.addNote(i, ch, pitch, n["start"], n["dur"], vel)
            # Meend: continuous glide from this note to a target swara.
            meend = n.get("meend")
            if meend is not None:
                tsw, toct = _resolve(meend, oct)
                target = sa + SWARAS[tsw] + 12 * toct
                _render_meend(mf, i, ch, n["start"], n["dur"], pitch, target)
    with open(path, "wb") as f:
        mf.writeFile(f)


def render(comp: dict, mid_path: str, wav_path: str, soundfont: str, gain: float = 1.2) -> str:
    build_midi(comp, mid_path)
    subprocess.run(
        ["fluidsynth", "-ni", "-g", str(gain), "-F", wav_path, "-r", "44100", soundfont, mid_path],
        check=True, capture_output=True,
    )
    return wav_path
