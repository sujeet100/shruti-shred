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
                                "dur": 0.5, "vel": 100, "grace": ["R"],
                                "meend_swara": "m", "meend_oct": null,
                                "chord": ["P"], "technique": "palm_mute"}, ...]},  # last five OPTIONAL
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

Meend (glide): a note may carry an optional "meend_swara" target (with an optional
"meend_oct" for the target's octave; omit/null to glide within the note's own octave).
The note sounds its own swara, then bends CONTINUOUSLY to the target across its
duration — a true portamento, rendered with MIDI pitch-bend. Because pitch-bend is
channel-wide, meend only works on a MONOPHONIC melodic channel (lead lines are); it is
not for the drone or drums. (Two flat fields rather than a swara|{swara,oct} union,
which Gemini's controlled-generation JSON schema handles poorly.)

Both kan and meend endpoints are validated by the raga grammar like any other
pitch. The continuous pitches a meend sweeps THROUGH are deliberately not
validated — sliding through microtones between two legal swaras is what a meend
is, not a grammar violation.

Riff chords + techniques (the rhythm guitar): a note may carry an optional "chord"
list of extra swaras — each sounded WITH the root, stacked at the lowest octave
above it, so `["S"]` is a root-octave power chord, `["P"]` a fifth, `["g","n"]` a
stacked raga-colour voicing. Chord tones are validated by the grammar like the root.
A note may also carry an optional "technique": "palm_mute" (a short, slightly softer
chug), "hammer_on"/"pull_off" (a softer legato attack), or "slide"/"bend" (a pitch-
wheel gesture into/up from the note). Because pitch-bend is channel-wide, a slide/bend
on a chorded rhythm channel bends the whole chord together — correct for a power chord.
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

# Rhythm-guitar technique shaping (see _apply_technique / _render_slide / _render_bend).
PALM_MUTE_DUR = 0.5      # a chug is short — clip the note to half its written length
PALM_MUTE_VEL = 0.9      # and a hair softer, the muted-string thud
LEGATO_VEL = 0.8         # hammer_on / pull_off: a softer attack, no re-pick
SLIDE_IN_ST = -2         # a slide starts this far below and rises INTO the note
SLIDE_IN_FRAC = 0.25     # ...over the first quarter of the note
BEND_ST = 2              # a bend rises this many semitones
BEND_FRAC = 0.5          # ...over the first half of the note, then holds


def _arm_bend_range(mf: MIDIFile, track: int, ch: int, semitones: int) -> None:
    """Widen a channel's pitch-bend range via RPN 0,0 so meend/slide/bend can span >2 semitones."""
    mf.addControllerEvent(track, ch, 0, 101, 0)          # RPN MSB
    mf.addControllerEvent(track, ch, 0, 100, 0)          # RPN LSB -> RPN(0,0) = bend range
    mf.addControllerEvent(track, ch, 0, 6, semitones)    # data entry MSB = semitones
    mf.addControllerEvent(track, ch, 0, 38, 0)           # data entry LSB = cents


def _wheel(semitones: float) -> int:
    """Pitch-wheel value for a bend of `semitones`, scaled to the armed MEEND_RANGE."""
    return max(-8192, min(8191, round(semitones / MEEND_RANGE * 8191)))


def _stack_above(root_pitch: int, tone_pitch: int) -> int:
    """Raise `tone_pitch` by whole octaves until it sounds strictly ABOVE `root_pitch`.

    The one rule behind chord voicing: every chord tone is seated at the lowest octave
    over the root, so `["S"]` becomes the root's octave (a power chord), `["P"]` the
    fifth just above, `["g","n"]` a stacked raga-colour voicing — all in-raga by
    construction, since the caller only passes legal swaras. Pure.
    """
    while tone_pitch <= root_pitch:
        tone_pitch += 12
    return tone_pitch


def _apply_technique(technique, dur: float, vel: int) -> tuple[float, int]:
    """Return (dur, vel) shaped for a technique's ATTACK/SUSTAIN — the part that is
    pure note geometry (pitch gestures are rendered separately). A palm-mute chug is
    short and slightly softer; a hammer-on/pull-off is a softer legato attack; slide
    and bend leave dur/vel alone (they only move the pitch wheel). Pure."""
    if technique == "palm_mute":
        return round(dur * PALM_MUTE_DUR, 4), max(1, int(vel * PALM_MUTE_VEL))
    if technique in ("hammer_on", "pull_off"):
        return dur, max(1, int(vel * LEGATO_VEL))
    return dur, vel


def _bends(n: dict) -> bool:
    """Does this note move the pitch wheel — a meend glide or a slide/bend technique?"""
    return n.get("meend_swara") is not None or n.get("technique") in ("slide", "bend")


def _render_meend(mf: MIDIFile, track: int, ch: int, start: float, dur: float,
                  from_pitch: int, to_pitch: int) -> None:
    """Ramp the pitch wheel from `from_pitch` to `to_pitch`, then recenter at note end."""
    interval = to_pitch - from_pitch                     # signed semitones
    full = _wheel(interval)
    glide = dur * MEEND_GLIDE_FRAC
    steps = max(6, min(48, int(glide / 0.02)))           # ~1 event per 0.02 beat, capped
    for k in range(steps + 1):
        t = start + glide * k / steps
        mf.addPitchWheelEvent(track, ch, round(t, 4), round(full * k / steps))
    # hold the target for the rest of the note, then recenter for the next note
    mf.addPitchWheelEvent(track, ch, round(start + dur, 4), 0)


def _render_slide(mf: MIDIFile, track: int, ch: int, start: float, dur: float) -> None:
    """Slide INTO the note: wheel starts SLIDE_IN_ST below and rises to pitch over the
    first quarter, then recenters at note end (riff notes lie end-to-end)."""
    glide = dur * SLIDE_IN_FRAC
    steps = max(4, min(24, int(glide / 0.02)))
    for k in range(steps + 1):
        t = start + glide * k / steps
        mf.addPitchWheelEvent(track, ch, round(t, 4), _wheel(SLIDE_IN_ST * (1 - k / steps)))
    mf.addPitchWheelEvent(track, ch, round(start + dur, 4), 0)


def _render_bend(mf: MIDIFile, track: int, ch: int, start: float, dur: float) -> None:
    """Bend UP: wheel rises from 0 to BEND_ST over the first half, holds, then recenters
    at note end. On a polyphonic (chorded) channel the whole chord bends together —
    acceptable, and correct for a slid/bent power chord."""
    glide = dur * BEND_FRAC
    steps = max(4, min(24, int(glide / 0.02)))
    for k in range(steps + 1):
        t = start + glide * k / steps
        mf.addPitchWheelEvent(track, ch, round(t, 4), _wheel(BEND_ST * k / steps))
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
        # Stereo placement (CC10): metal mixes pan the two rhythm-guitar tracks hard
        # L/R and separate the melodic voices, so parts don't stack up mono-centre.
        if layer.get("pan") is not None:
            mf.addControllerEvent(i, ch, 0, 10, max(0, min(127, layer["pan"])))
        # If any note on this channel moves the pitch wheel (a meend glide, or a riff
        # slide/bend), arm a wide bend range once up front so the gesture spans cleanly.
        if any(_bends(n) for n in layer["notes"]):
            _arm_bend_range(mf, i, ch, MEEND_RANGE)
        for n in layer["notes"]:
            oct = n.get("oct", 0)
            vel = n.get("vel", 100)
            # Technique first: it shapes the note's length/attack before it is sounded
            # (the chug of a palm-mute, the softer legato of a hammer-on/pull-off).
            dur, vel = _apply_technique(n.get("technique"), n["dur"], vel)
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
            mf.addNote(i, ch, pitch, n["start"], dur, vel)
            # Chord: extra raga swaras sounded WITH the root, each stacked at the lowest
            # octave above it — a power chord (`["S"]`), a fifth (`["P"]`), a voicing.
            for csw in n.get("chord") or []:
                tone = _stack_above(pitch, sa + SWARAS[csw] + 12 * oct)
                mf.addNote(i, ch, tone, n["start"], dur, vel)
            # Pitch-wheel gestures: a meend glide to a target swara, or a riff slide/bend.
            tsw = n.get("meend_swara")
            if tsw is not None:
                toct = n.get("meend_oct")
                target = sa + SWARAS[tsw] + 12 * (oct if toct is None else toct)
                _render_meend(mf, i, ch, n["start"], dur, pitch, target)
            elif n.get("technique") == "slide":
                _render_slide(mf, i, ch, n["start"], dur)
            elif n.get("technique") == "bend":
                _render_bend(mf, i, ch, n["start"], dur)
    with open(path, "wb") as f:
        mf.writeFile(f)


def render(comp: dict, mid_path: str, wav_path: str, soundfont: str, gain: float = 1.2) -> str:
    build_midi(comp, mid_path)
    subprocess.run(
        ["fluidsynth", "-ni", "-g", str(gain), "-F", wav_path, "-r", "44100", soundfont, mid_path],
        check=True, capture_output=True,
    )
    return wav_path
