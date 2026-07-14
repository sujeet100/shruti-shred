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
list of extra swaras — each a raga swara sounded WITH the root, stacked at the lowest
octave above it (a swara stacked up, NOT a fixed interval): the note's OWN swara gives a
root+octave power chord, `["P"]` adds Pa (a true fifth only above the tonic Sa), `["g","n"]`
a raga-colour voicing. Chord tones are validated by the grammar like the root.
A note may also carry an optional "technique": "palm_mute" (a short, slightly softer
chug), "hammer_on"/"pull_off" (a softer legato attack), or "slide"/"bend" (a pitch-
wheel gesture into/up from the note). Because pitch-bend is channel-wide, a slide/bend
on a chorded rhythm channel bends the whole chord together — correct for a power chord.

Andolan (oscillation): a held note may carry "andolan": true — a slow, shallow pitch
sway (a fraction of a semitone, ~2.4 Hz) rendered on the pitch wheel. It is the komal
note that DEFINES ragas like Darbari (komal g/d) and Bhairav (komal r/d); a straight,
un-oscillated komal there sounds like a different raga. Set deterministically by the lead
generator on the raga's own andolan swaras (never by the LLM). Like meend it is a wheel
gesture, so it lives on a monophonic melodic channel and is mutually exclusive with a
meend on the same note.
"""

import math
import subprocess
from midiutil import MIDIFile
from raga import SWARAS
from soundfont import TABLA_KEYS

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
# A meend is a QUICK pull to the target, not a slow swoop. The glide is a short, fixed-ish
# time (scaled a little by interval, capped) — NOT a fraction of the note — so a long held
# note gets a crisp pull and the ear isn't left sitting on the out-of-scale micro-pitches
# in between. (Confirmed empirically: the old 60%-of-the-note linear glide sounded out of
# tune on every patch; see DESIGN.md "meend realism".)
MEEND_GLIDE_BASE_MS = 60     # base glide time
MEEND_GLIDE_PER_ST_MS = 25   # + this per semitone of interval (wider bends read as slower)
MEEND_GLIDE_MIN_MS = 80      # never faster than this (else it stops reading as a glide)
MEEND_GLIDE_MAX_MS = 220     # never slower than this (else it's a swoop again)

# Andolan — the SLOW, SHALLOW pitch oscillation that IS the komal note in ragas like Darbari
# (komal g/d) and Bhairav (komal r/d): the note "sways" a fraction of a semitone rather than
# gliding to a target. Kept slow (a gentle sway, not a fast vibrato/gamak) and shallow (a
# sruti-width waver, not a full bend). Rendered as a sine on the pitch wheel over WHOLE cycles,
# so it starts and ends at 0 and never bleeds into the next note. Rate is real-time (ms) so
# tempo doesn't stretch it. Depth is scaled to the armed bend range in `_wheel`.
ANDOLAN_DEPTH_ST = 0.4       # semitones of sway either side of the note (shallow — a sruti waver)
ANDOLAN_PERIOD_MS = 420      # one oscillation ~0.42s (~2.4 Hz) — slow enough to read as andolan
ANDOLAN_STEPS_PER_CYCLE = 16 # wheel events per cycle — dense enough that the sine has no zipper

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
    over the root, so the root's OWN swara becomes its octave (a power chord), `["P"]` seats
    Pa just above (a true fifth only when the root is Sa), `["g","n"]` a stacked raga-colour
    voicing — all in-raga by construction, since the caller only passes legal swaras. Pure.
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
    """Does this note move the pitch wheel — a meend glide, a slide/bend technique, or an
    andolan oscillation? Any of these needs the channel's wide bend range armed up front."""
    return (n.get("meend_swara") is not None
            or n.get("technique") in ("slide", "bend")
            or bool(n.get("andolan")))


def _meend_glide_beats(interval: int, dur: float, bpm: float) -> float:
    """The glide's duration in beats: a short, interval-scaled, capped pull (never longer
    than the note). Kept in real time (ms) so tempo doesn't stretch it into a swoop."""
    ms = min(MEEND_GLIDE_MAX_MS, max(MEEND_GLIDE_MIN_MS,
                                     MEEND_GLIDE_BASE_MS + MEEND_GLIDE_PER_ST_MS * interval))
    return min(ms * bpm / 60000.0, dur)


def _meend_wheel(start: float, dur: float, from_pitch: int, to_pitch: int,
                 bpm: float) -> list[tuple[float, int]]:
    """Pure: the (time, wheel-value) ramp for a meend, ANCHORED ON THE TARGET.

    The note is sounded at the TARGET pitch (see `build_midi`); the wheel starts PRE-BENT at
    the source and eases UP TO 0, so the attack is heard at the source, the glide arrives at
    the target, and the sustained tail rests in tune on the target's HOME sample (best
    fidelity) — then holds 0, so nothing bleeds into the next note. The pull is a short,
    interval-scaled, capped time with a CUBIC EASE-OUT (fast off the source, settling onto
    the target), emitted as a dense ramp so there's no zipper stair-stepping. A leading event
    a hair before the note-on guarantees the wheel is pre-bent when the note attacks.
    """
    pre = _wheel(from_pitch - to_pitch)                  # wheel that sounds the source on a target note
    if pre == 0:
        return []                                        # same pitch — no glide
    glide = _meend_glide_beats(abs(from_pitch - to_pitch), dur, bpm)
    ms = MEEND_GLIDE_BASE_MS + MEEND_GLIDE_PER_ST_MS * abs(from_pitch - to_pitch)
    steps = max(8, min(48, int(ms / 6)))                 # ~1 event per 6 ms — dense, no zipper
    ramp: list[tuple[float, int]] = [(round(max(0.0, start - 0.002), 4), pre)]  # pre-bend before onset
    for k in range(steps + 1):
        frac = k / steps
        eased = 1.0 - (1.0 - frac) ** 3                  # cubic ease-out: fast off source, settle on target
        ramp.append((round(start + glide * frac, 4), round(pre * (1.0 - eased))))
    return ramp


def _render_meend(mf: MIDIFile, track: int, ch: int, start: float, dur: float,
                  from_pitch: int, to_pitch: int, bpm: float) -> None:
    for t, val in _meend_wheel(start, dur, from_pitch, to_pitch, bpm):
        mf.addPitchWheelEvent(track, ch, t, val)


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


def _andolan_wheel(start: float, dur: float, bpm: float) -> list[tuple[float, int]]:
    """Pure: the (time, wheel) ramp for an andolan — a slow, shallow sine sway on the pitch
    wheel, spanning the note. The number of cycles is chosen so a WHOLE number of oscillations
    fits the note (start and end land on 0 — no bleed into the next note); the rate is held
    near ANDOLAN_PERIOD_MS in real time so tempo doesn't stretch the sway into a swoop. A note
    too short for even one slow cycle gets no andolan (it can't read as a sway)."""
    dur_ms = dur * 60000.0 / bpm
    cycles = int(round(dur_ms / ANDOLAN_PERIOD_MS))
    if cycles < 1:
        return []                                        # too short to sway — leave it clean
    steps = cycles * ANDOLAN_STEPS_PER_CYCLE
    ramp: list[tuple[float, int]] = []
    for k in range(steps + 1):
        frac = k / steps
        sway = math.sin(2.0 * math.pi * cycles * frac)   # whole cycles: sin is 0 at frac 0 and 1
        ramp.append((round(start + dur * frac, 4), _wheel(ANDOLAN_DEPTH_ST * sway)))
    return ramp


def _render_andolan(mf: MIDIFile, track: int, ch: int, start: float, dur: float,
                    bpm: float) -> None:
    for t, val in _andolan_wheel(start, dur, bpm):
        mf.addPitchWheelEvent(track, ch, t, val)


def build_midi(comp: dict, path: str) -> None:
    layers = comp["layers"]
    mf = MIDIFile(numTracks=len(layers), deinterleave=False)
    for i in range(len(layers)):
        mf.addTempo(i, 0, comp["bpm"])
    sa = comp["sa"]
    for i, layer in enumerate(layers):
        # A tabla routed to a real tabla soundfont (it carries a `bank`) plays its stroke
        # keys as pitched notes on its own melodic channel — NOT GM percussion. Bank-select
        # + program first, then each bol's hit becomes a note at its mapped tabla key.
        if layer.get("role") == "tabla" and layer.get("bank") is not None:
            ch = layer["channel"]
            mf.addControllerEvent(i, ch, 0, 0, layer["bank"] // 128)
            mf.addControllerEvent(i, ch, 0, 32, layer["bank"] % 128)
            if "program" in layer:
                mf.addProgramChange(i, ch, 0, layer["program"])
            # Tune the dayan to Sa (MIDI RPN 00 02 coarse tuning; 64 = no shift): the strokes
            # are fixed near C, so we pitch-shift the whole tabla channel into the piece's key.
            ct = layer.get("coarse_tune", 0)
            if ct:
                mf.addControllerEvent(i, ch, 0, 101, 0)   # RPN MSB
                mf.addControllerEvent(i, ch, 0, 100, 2)    # RPN LSB = coarse tuning
                mf.addControllerEvent(i, ch, 0, 6, 64 + ct)  # data entry MSB (semitones)
            for h in layer["hits"]:
                mf.addNote(i, ch, TABLA_KEYS[h["drum"]], h["start"], h.get("dur", 0.2), h.get("vel", 100))
            continue
        # Percussion layers (the metal kit and the GM-conga tabla fallback) carry hits, not
        # pitched notes, and both live on GM channel 9.
        if layer.get("role") in ("drums", "tabla"):
            for h in layer["hits"]:
                mf.addNote(i, 9, DRUMS[h["drum"]], h["start"], h.get("dur", 0.2), h.get("vel", 100))
            continue
        ch = layer["channel"]
        # Bank Select (CC0 MSB + CC32 LSB) BEFORE the program change: routes this channel
        # to a stacked specialized soundfont (e.g. the guitars to a real distorted bank).
        # Absent on base-GM voices. Emitted first so the following program change resolves
        # inside the selected bank (FluidSynth reads bank-select, then program change).
        if layer.get("bank") is not None:
            msb, lsb = layer["bank"] // 128, layer["bank"] % 128
            mf.addControllerEvent(i, ch, 0, 0, msb)
            mf.addControllerEvent(i, ch, 0, 32, lsb)
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
        bpm = comp["bpm"]
        for n in layer["notes"]:
            oct = n.get("oct", 0)
            vel = n.get("vel", 100)
            # Technique first: it shapes the note's length/attack before it is sounded
            # (the chug of a palm-mute, the softer legato of a hammer-on/pull-off).
            dur, vel = _apply_technique(n.get("technique"), n["dur"], vel)
            # Kan: crushed grace notes stolen from just before the main onset (at the
            # written pitch, wheel 0 — a meend leaves the wheel at 0, so they never bleed).
            grace = n.get("grace")
            if grace:
                span = min(GRACE_LEN, n["start"])
                if span > 0:
                    each = span / len(grace)
                    gvel = max(1, int(vel * 0.7))   # kan is softer than the note
                    for j, gsw in enumerate(grace):
                        gp = sa + SWARAS[gsw] + 12 * oct
                        mf.addNote(i, ch, gp, round(n["start"] - span + j * each, 4),
                                   each * 0.9, gvel)
            pitch = sa + SWARAS[n["swara"]] + 12 * oct
            # A meend is ANCHORED ON ITS TARGET: sound the note at the target swara (so the
            # sustained tail rests on that sample's home pitch), and let `_render_meend`
            # pre-bend the wheel to the source and ease it to 0. Non-meend notes sound at
            # their own pitch. Chord tones stack above whichever pitch actually sounds.
            tsw = n.get("meend_swara")
            toct = n.get("meend_oct")
            target = (sa + SWARAS[tsw] + 12 * (oct if toct is None else toct)) if tsw is not None else None
            sounding = target if target is not None else pitch
            mf.addNote(i, ch, sounding, n["start"], dur, vel)
            # Chord: extra raga swaras sounded WITH the root, each stacked at the lowest
            # octave above the sounding pitch — a power chord (`["S"]`), a fifth (`["P"]`).
            for csw in n.get("chord") or []:
                tone = _stack_above(sounding, sa + SWARAS[csw] + 12 * oct)
                mf.addNote(i, ch, tone, n["start"], dur, vel)
            # Pitch-wheel gestures (mutually exclusive per note): a meend glide to a target
            # swara, a riff slide/bend, or a slow andolan sway on a held komal note.
            if target is not None:
                _render_meend(mf, i, ch, n["start"], dur, pitch, target, bpm)
            elif n.get("technique") == "slide":
                _render_slide(mf, i, ch, n["start"], dur)
            elif n.get("technique") == "bend":
                _render_bend(mf, i, ch, n["start"], dur)
            elif n.get("andolan"):
                _render_andolan(mf, i, ch, n["start"], dur, bpm)
    with open(path, "wb") as f:
        mf.writeFile(f)


def render(
    comp: dict,
    mid_path: str,
    wav_path: str,
    soundfont: str,
    gain: float = 1.2,
    extra_soundfonts: list[tuple[str, int]] | None = None,
) -> str:
    """Render the composition to WAV via FluidSynth.

    `soundfont` is the GM base. `extra_soundfonts` is an optional list of
    `(path, bank_offset)` specialized banks stacked on top (each via FluidSynth's `-b`
    positional flag); a layer's Bank Select then routes it to one of them. When any extra
    is stacked, bank-select mode is set to 'mma' so high SF2 banks are addressable.
    """
    build_midi(comp, mid_path)
    cmd = ["fluidsynth", "-ni", "-g", str(gain)]
    if extra_soundfonts:
        cmd += ["-o", "synth.midi-bank-select=mma"]
    cmd += ["-F", wav_path, "-r", "44100", soundfont]
    for path, bank_offset in extra_soundfonts or []:
        cmd += ["-b", str(bank_offset), path]
    cmd.append(mid_path)
    subprocess.run(cmd, check=True, capture_output=True)
    return wav_path
