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
list of extra swaras — each a raga swara sounded WITH the root. Chord tones are validated
by the grammar like the root, then SEATED at an interval that stays CONSONANT under
high-gain distortion (`_seat_chord_tone`): the note's OWN swara becomes the octave (a
power chord), a perfect fifth/fourth seats as itself (the fourth is the INVERTED power
chord), and a second/third is lifted ABOVE the octave — an add9 / a tenth — where it
colours instead of grinding. An interval that can only clash under distortion (semitone,
tritone, sevenths) degrades to octave weight. This is deliberate metal voicing, not a
raga rule: legality kept every stack in the raga but ignored consonance, and a low-octave
second under distortion is mud (heard, then fixed, on the first live gat render).
A note may also carry an optional "technique": "palm_mute" (a short chug ROUTED to a
genuinely muted-guitar companion channel, with a soft distorted copy underneath —
the timbre change is what reads as a palm mute), "hammer_on"/"pull_off" (a softer
attack PLUS a fast pull from the previous note's pitch — real legato), or a
pitch-wheel gesture — "slide" (starts at the previous note's pitch, so it travels in
the line's own direction), "long_slide" (a wide, slower position shift from a fifth
below), "pick_scrape" (a dive from an octave ABOVE down onto the note — the
dragged-pick fall), or "bend" (up from the note). Because pitch-bend is channel-wide,
a gesture on a chorded rhythm channel moves the whole chord together — correct for a
slid/scraped power chord.

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
    "bell": 53,     # Ride Bell — the piercing driving-metal timekeeper
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
PALM_MUTE_MS = 80        # a chug gates to a FIXED wall-clock length (industry-converged:
                         # TuxGuitar 60ms, alphaTab 80ms), capped at the written duration —
                         # the transient-then-silence shape IS the chug, at any tempo
MUTE_LEVEL = 127         # companion-channel CC7: muted samples are recorded far quieter
                         # than the open patches — full channel volume compensates, so a
                         # chug holds its own against a stacked chord ("chugs barely
                         # audible", heard 2026-07-15)
LEGATO_VEL = 0.8         # hammer_on / pull_off: a softer attack, no re-pick
SLIDE_IN_ST = -2         # a slide starts this far below and rises INTO the note
SLIDE_IN_FRAC = 0.25     # ...over the first quarter of the note
LONG_SLIDE_ST = -7       # a LONG slide climbs from a fifth below — a real position shift
LONG_SLIDE_FRAC = 0.4    # ...over the first 40% of the note (slow enough to hear the travel)
SCRAPE_ST = 12           # a pick scrape DIVES from an octave above down into the note
SCRAPE_FRAC = 0.5        # ...over the first half — the dragged-pick fall onto the downbeat
BEND_ST = 2              # a bend rises this many semitones
BEND_FRAC = 0.5          # ...over the first half of the note, then holds

# Palm-mute REALISM: a chug's "chunk" is a timbre, not just a shorter note. Chug notes
# route to a companion channel playing GM #29 Electric Guitar (muted) — a genuinely
# muted sample — with a soft copy left on the distorted channel underneath for body.
# The companion inherits the take's pan/detune so the chug sits in the same stereo spot;
# it deliberately does NOT inherit a specialized bank (the muted timbre IS the point).
MUTED_GUITAR_PROGRAM = 28   # GM #29 Electric Guitar (muted)
MUTE_BODY_VEL = 1.0         # the distorted under-layer beneath each chug plays at FULL
                            # written velocity — the parity rule ("a chug must be as loud
                            # as any open note", Sujit 2026-07-15): the body IS the open
                            # patch, so a chug can never sit below a same-velocity note;
                            # the 80ms gate + muted layer keep it a chug, not a note

# Legato / slide realism: hammer_on & pull_off PULL the wheel from the PREVIOUS note's
# pitch (a real finger move, not just a softer attack), and a slide now starts at the
# previous note's pitch too (direction follows the line). Both capped — wider travel
# reads as a position shift, which is long_slide's job.
LEGATO_PULL_MAX = 4      # semitones a hammer-on/pull-off may pull across
LEGATO_PULL_FRAC = 0.15  # ...over the first 15% of the note (a finger, not a slide)
SLIDE_FROM_PREV_MAX = 5  # semitones a slide may start away from its note
LEGATO_MAX_GAP = 0.05    # beats: prev note must END this close for a legato connection


# Reverb send (MIDI CC91) per layer role — a metal mix's space: the melodic voices sit in a
# room, the rhythm chug stays tight, and the low end stays dry so it doesn't smear. Without
# an explicit send the specialized banks (Dethmetal) play bone-dry raw samples — the "no
# reverb, sounds like noise" tone of the first live render.
_REVERB_SEND = {"lead": 68, "drone": 48, "rhythm": 30, "bass": 12, "tabla": 52, "drums": 38}
_REVERB_SEND_DEFAULT = 40


def _reverb_send(role) -> int:
    return _REVERB_SEND.get(role, _REVERB_SEND_DEFAULT)


def _fine_tune(mf: MIDIFile, track: int, ch: int, cents: int) -> None:
    """Channel fine-tune via RPN 0,1 — shift the whole channel by `cents` (±100 max).
    A few cents on ONE side of the double-tracked rhythm pair decorrelates the two takes
    (two players, not one copied signal) without reading as chorus or detune."""
    value = max(0, min(16383, round(8192 * (1 + cents / 100))))
    mf.addControllerEvent(track, ch, 0, 101, 0)          # RPN MSB
    mf.addControllerEvent(track, ch, 0, 100, 1)          # RPN LSB -> RPN(0,1) = fine tuning
    mf.addControllerEvent(track, ch, 0, 6, value >> 7)   # data entry MSB
    mf.addControllerEvent(track, ch, 0, 38, value & 0x7F)  # data entry LSB


def _arm_bend_range(mf: MIDIFile, track: int, ch: int, semitones: int) -> None:
    """Widen a channel's pitch-bend range via RPN 0,0 so meend/slide/bend can span >2 semitones."""
    mf.addControllerEvent(track, ch, 0, 101, 0)          # RPN MSB
    mf.addControllerEvent(track, ch, 0, 100, 0)          # RPN LSB -> RPN(0,0) = bend range
    mf.addControllerEvent(track, ch, 0, 6, semitones)    # data entry MSB = semitones
    mf.addControllerEvent(track, ch, 0, 38, 0)           # data entry LSB = cents


def _wheel(semitones: float) -> int:
    """Pitch-wheel value for a bend of `semitones`, scaled to the armed MEEND_RANGE."""
    return max(-8192, min(8191, round(semitones / MEEND_RANGE * 8191)))


# Chord-tone seating: interval above the root (mod 12) -> the interval it SOUNDS at, chosen
# to stay consonant under high-gain distortion. Same swara -> the octave (a power chord); a
# true fifth/fourth keeps its seat (the fourth = an inverted power chord); a second/third is
# lifted an octave (add9 / a tenth) so it colours above the grind instead of beating inside
# it. Anything absent (semitone, tritone, sixths, sevenths) has no clean seat under gain.
_CHORD_SEATS = {
    0: 12,   # own swara -> octave: the power chord
    7: 7,    # perfect fifth (Sa->Pa)
    5: 5,    # perfect fourth — the inverted power chord
    2: 14,   # major second -> add9, above the octave
    3: 15,   # minor third  -> a minor tenth
    4: 16,   # major third  -> a major tenth (Yaman's Ga over Sa, clear of the low octave)
}


def _seat_chord_tone(root_pitch: int, tone_pitch: int) -> int | None:
    """Seat a chord tone at a distortion-consonant interval above the sounding root, or
    None when its pitch class has no clean seat (the caller degrades it to octave weight).
    The tone's own octave is irrelevant — only its pitch class relative to the root matters,
    and the seat table decides where it sounds. Pure."""
    seat = _CHORD_SEATS.get((tone_pitch - root_pitch) % 12)
    return None if seat is None else root_pitch + seat


def _apply_technique(technique, dur: float, vel: int, bpm: float) -> tuple[float, int]:
    """Return (dur, vel) shaped for a technique's ATTACK/SUSTAIN — the part that is
    pure note geometry (pitch gestures are rendered separately). A palm-mute chug
    gates to a fixed WALL-CLOCK length (capped at the written duration) and lands
    slightly softer; a hammer-on/pull-off is a softer legato attack; slide and bend
    leave dur/vel alone (they only move the pitch wheel). Pure."""
    if technique == "palm_mute":
        # the gate alone shapes the chug — no velocity cut: the muted TIMBRE already
        # carries the softness, and attenuating on top of it buried the chugs
        gate = min(dur, PALM_MUTE_MS * bpm / 60000.0)
        return round(gate, 4), vel
    if technique in ("hammer_on", "pull_off"):
        return dur, max(1, int(vel * LEGATO_VEL))
    return dur, vel


def _pull_offset(prev_pitch: int | None, pitch: int, cap: int) -> float | None:
    """The wheel offset a legato/slide gesture starts from: the PREVIOUS sounding pitch
    relative to this note, capped at `cap` semitones. None when there is no usable
    previous note or no travel — the caller then skips (legato) or falls back to the
    fixed default (slide). Pure."""
    if prev_pitch is None or prev_pitch == pitch:
        return None
    return float(max(-cap, min(cap, prev_pitch - pitch)))


def _bends(n: dict) -> bool:
    """Does this note move the pitch wheel — a meend glide, a slide/bend technique, or an
    andolan oscillation? Any of these needs the channel's wide bend range armed up front."""
    return (n.get("meend_swara") is not None
            or n.get("technique") in ("slide", "long_slide", "pick_scrape", "bend",
                                      "hammer_on", "pull_off")
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


def _render_slide(mf: MIDIFile, track: int, ch: int, start: float, dur: float,
                  st: float = SLIDE_IN_ST, frac: float = SLIDE_IN_FRAC) -> None:
    """Slide INTO the note: wheel starts `st` semitones away and settles to pitch over
    the first `frac` of the note, then recenters at note end (riff notes lie end-to-end).
    The short default is the fret-to-fret slide; `long_slide` passes a wider interval
    over a longer window (an audible position shift up the neck), and `pick_scrape`
    passes a big POSITIVE offset (the dragged-pick DIVE down onto the note)."""
    glide = dur * frac
    steps = max(4, min(24, int(glide / 0.02)))
    for k in range(steps + 1):
        t = start + glide * k / steps
        mf.addPitchWheelEvent(track, ch, round(t, 4), _wheel(st * (1 - k / steps)))
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


# The ring-out (fade) — the intro's final Sa resolving "like a struck chord dying away"
# (Sujit): expression (CC11) decays across the note with a quadratic ease (fast at first,
# settling — the shape of a real string's decay), to a quiet floor rather than silence,
# then snaps back to full at the note's end so the next section is untouched.
_FADE_FLOOR = 16          # CC11 the decay settles on (quiet, still ringing)
_FADE_STEPS = 24          # events across the note — dense enough to sound continuous


def _fade_ramp(start: float, dur: float) -> list[tuple[float, int]]:
    """Pure: the (time, CC11-value) ramp for a ring-out, ending with the reset to full."""
    ramp: list[tuple[float, int]] = []
    for k in range(_FADE_STEPS + 1):
        frac = k / _FADE_STEPS
        level = _FADE_FLOOR + (127 - _FADE_FLOOR) * (1.0 - frac) ** 2
        ramp.append((round(start + dur * frac, 4), round(level)))
    ramp.append((round(start + dur, 4), 127))    # snap back — the fade never bleeds onward
    return ramp


def _render_fade(mf: MIDIFile, track: int, ch: int, start: float, dur: float) -> None:
    for t, val in _fade_ramp(start, dur):
        mf.addControllerEvent(track, ch, t, 11, val)


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


def _mute_channel(mf: MIDIFile, track: int, layer: dict,
                  used: set[int]) -> tuple[int, bool] | None:
    """Set up the palm-mute companion channel for a rhythm-guitar layer: the first free
    channel (never 9) at the take's own pan/detune/reverb. When the layer carries a
    `pm_bank` (SGM's real muted-DISTORTION patch — the Songsterr articulation move), the
    companion bank-selects there and the chug needs no body layering; otherwise it plays
    the GM muted guitar and the caller layers a soft distorted copy underneath. Returns
    (channel, has_real_pm), or None when the layer has no chugs or no channel is free."""
    if layer.get("role") != "rhythm" or not any(
            n.get("technique") == "palm_mute" for n in layer.get("notes") or []):
        return None
    ch = next((c for c in range(16) if c != 9 and c not in used), None)
    if ch is None:
        return None
    used.add(ch)
    real_pm = layer.get("pm_bank") is not None
    if real_pm:
        mf.addControllerEvent(track, ch, 0, 0, layer["pm_bank"] // 128)
        mf.addControllerEvent(track, ch, 0, 32, layer["pm_bank"] % 128)
        mf.addProgramChange(track, ch, 0, layer.get("pm_program", MUTED_GUITAR_PROGRAM))
    else:
        mf.addProgramChange(track, ch, 0, MUTED_GUITAR_PROGRAM)
    mf.addControllerEvent(track, ch, 0, 7, MUTE_LEVEL)   # muted samples run quiet — lift them
    if layer.get("pan") is not None:
        mf.addControllerEvent(track, ch, 0, 10, max(0, min(127, layer["pan"])))
    mf.addControllerEvent(track, ch, 0, 91, _reverb_send(layer.get("role")))
    if layer.get("detune_cents"):
        _fine_tune(mf, track, ch, layer["detune_cents"])
    return ch, real_pm


def build_midi(comp: dict, path: str) -> None:
    layers = comp["layers"]
    mf = MIDIFile(numTracks=len(layers), deinterleave=False)
    for i in range(len(layers)):
        mf.addTempo(i, 0, comp["bpm"])
    sa = comp["sa"]
    used_channels = {9} | {la["channel"] for la in layers if la.get("channel") is not None}
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
            mf.addControllerEvent(i, ch, 0, 91, _reverb_send("tabla"))
            for h in layer["hits"]:
                mf.addNote(i, ch, TABLA_KEYS[h["drum"]], h["start"], h.get("dur", 0.2), h.get("vel", 100))
            continue
        # Percussion layers (the metal kit and the GM-conga tabla fallback) carry hits, not
        # pitched notes, and both live on GM channel 9.
        if layer.get("role") in ("drums", "tabla"):
            # A GS drum KIT is selected by a program change on the percussion channel
            # (kit 16 = POWER, the rock/metal kit — what Songsterr's metal tabs use).
            if layer.get("program") is not None:
                mf.addProgramChange(i, 9, 0, layer["program"])
            mf.addControllerEvent(i, 9, 0, 91, _reverb_send(layer.get("role")))
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
        mf.addControllerEvent(i, ch, 0, 91, _reverb_send(layer.get("role")))
        if layer.get("detune_cents"):
            _fine_tune(mf, i, ch, layer["detune_cents"])
        # If any note on this channel moves the pitch wheel (a meend glide, or a riff
        # slide/bend), arm a wide bend range once up front so the gesture spans cleanly.
        if any(_bends(n) for n in layer["notes"]):
            _arm_bend_range(mf, i, ch, MEEND_RANGE)
        # The chug companion: palm-muted notes of a rhythm take sound on a genuinely
        # MUTED guitar channel — SGM's muted-distortion patch when routed (self-
        # sufficient), else GM's clean mute plus a soft distorted copy underneath.
        mute = _mute_channel(mf, i, layer, used_channels)
        mute_ch, real_pm = mute if mute is not None else (None, False)
        bpm = comp["bpm"]
        prev_pitch: int | None = None       # the previous SOUNDING pitch (legato/slide context)
        prev_end = -1.0
        for n in layer["notes"]:
            oct = n.get("oct", 0)
            vel = n.get("vel", 100)
            # Technique first: it shapes the note's length/attack before it is sounded
            # (the chug of a palm-mute, the softer legato of a hammer-on/pull-off).
            dur, vel = _apply_technique(n.get("technique"), n["dur"], vel, bpm)
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
            # A chug sounds on the MUTED companion channel — the real palm-mute "chunk" —
            # with a soft copy on the distorted take underneath for body. Everything else
            # sounds on the take as before.
            is_chug = mute_ch is not None and n.get("technique") == "palm_mute"

            def _sound(p: int) -> None:
                if is_chug:
                    mf.addNote(i, mute_ch, p, n["start"], dur, vel)
                    # ...plus the distorted body underneath in BOTH modes: the gain wall
                    # is what keeps a single-pitch chug from thinning next to a chord
                    mf.addNote(i, ch, p, n["start"], dur, max(1, int(vel * MUTE_BODY_VEL)))
                else:
                    mf.addNote(i, ch, p, n["start"], dur, vel)

            _sound(sounding)
            # Chord: extra raga swaras sounded WITH the root, each seated at a distortion-
            # consonant interval (see `_seat_chord_tone`); a tone with no clean seat under
            # gain degrades to octave weight. Seats are deduped — two tones landing on the
            # same pitch would double a note-on on one channel.
            seated: set[int] = {sounding}
            for csw in n.get("chord") or []:
                tone = _seat_chord_tone(sounding, sa + SWARAS[csw] + 12 * oct)
                if tone is None:
                    tone = sounding + 12          # dissonant colour -> octave weight instead
                if tone not in seated:
                    seated.add(tone)
                    _sound(tone)
            # A ring-out fades the note's expression like a dying string (independent of the
            # wheel gestures below — CC11, not pitch).
            if n.get("fade"):
                _render_fade(mf, i, ch, n["start"], dur)
            # Pitch-wheel gestures (mutually exclusive per note): a meend glide to a target
            # swara, a riff slide/bend/legato, or a slow andolan sway on a held komal note.
            # Legato and slide read the PREVIOUS note's pitch — a hammer-on/pull-off is a
            # finger moving from where the line just was, and a slide travels in the line's
            # own direction; a fixed offset reads as a synth blip, not a hand.
            connected = prev_pitch if n["start"] - prev_end <= LEGATO_MAX_GAP else None
            if target is not None:
                _render_meend(mf, i, ch, n["start"], dur, pitch, target, bpm)
            elif n.get("technique") == "slide":
                st = _pull_offset(connected, sounding, SLIDE_FROM_PREV_MAX) or SLIDE_IN_ST
                _render_slide(mf, i, ch, n["start"], dur, st=st)
            elif n.get("technique") == "long_slide":
                _render_slide(mf, i, ch, n["start"], dur,
                              st=LONG_SLIDE_ST, frac=LONG_SLIDE_FRAC)
            elif n.get("technique") == "pick_scrape":
                _render_slide(mf, i, ch, n["start"], dur,
                              st=SCRAPE_ST, frac=SCRAPE_FRAC)
            elif n.get("technique") in ("hammer_on", "pull_off") and not n.get("chord"):
                st = _pull_offset(connected, sounding, LEGATO_PULL_MAX)
                if st is not None:               # no usable previous note: soft attack only
                    _render_slide(mf, i, ch, n["start"], dur, st=st, frac=LEGATO_PULL_FRAC)
            elif n.get("technique") == "bend":
                _render_bend(mf, i, ch, n["start"], dur)
            elif n.get("andolan"):
                _render_andolan(mf, i, ch, n["start"], dur, bpm)
            prev_pitch, prev_end = sounding, n["start"] + n["dur"]
    with open(path, "wb") as f:
        mf.writeFile(f)


# The full band at gain 1.2 CLIPPED (peaks pinned at 0 dBFS — heard as harsh digital noise
# on the first live gat render); FluidSynth has no limiter, so headroom must come from gain.
# Calibrated against that render's own MIDI: 0.6 peaked at -0.3 dBFS, 0.8 clipped — 0.5
# leaves ~2 dB of true headroom on the densest mix heard so far.
_GAIN = 0.5
# A modest room, shared by the whole band; per-channel CC91 (see `_REVERB_SEND`) decides how
# much each voice sends into it. FluidSynth's defaults leave the specialized banks bone-dry.
_REVERB_SETTINGS = ("synth.reverb.room-size=0.55", "synth.reverb.damp=0.35",
                    "synth.reverb.level=0.7")


def render(
    comp: dict,
    mid_path: str,
    wav_path: str,
    soundfont: str,
    gain: float = _GAIN,
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
    for setting in _REVERB_SETTINGS:
        cmd += ["-o", setting]
    if extra_soundfonts:
        cmd += ["-o", "synth.midi-bank-select=mma"]
    cmd += ["-F", wav_path, "-r", "44100", soundfont]
    for path, bank_offset in extra_soundfonts or []:
        cmd += ["-b", str(bank_offset), path]
    cmd.append(mid_path)
    subprocess.run(cmd, check=True, capture_output=True)
    _normalize_wav(wav_path)
    return wav_path


# Peak-normalize the rendered WAV to this ceiling. This delivers the loudness Sujit
# picked in the Songsterr A/B without the clipping (their player runs synth gain 1.2,
# pinning peaks at 0 dBFS): the synth keeps its calibrated headroom gain and the file
# is lifted afterwards. -2.0 ≈ their "gain 1.0" (Sujit dialed the first -0.5 ceiling
# back, 2026-07-15). Skipped silently when ffmpeg is absent.
NORMALIZE_PEAK_DB = -2.0


def _normalize_wav(wav_path: str) -> None:
    """Lift the WAV so its peak sits at NORMALIZE_PEAK_DB. Two ffmpeg passes
    (measure, then gain); a no-op without ffmpeg or on an already-hot file."""
    import os
    import re
    import shutil
    if shutil.which("ffmpeg") is None:
        return
    probe = subprocess.run(["ffmpeg", "-i", wav_path, "-af", "volumedetect", "-f", "null", "-"],
                           capture_output=True, text=True)
    m = re.search(r"max_volume:\s*(-?[\d.]+) dB", probe.stderr)
    if not m:
        return
    lift = NORMALIZE_PEAK_DB - float(m.group(1))
    if lift <= 0.1:
        return
    tmp = wav_path + ".norm.wav"
    subprocess.run(["ffmpeg", "-y", "-i", wav_path, "-af", f"volume={lift:.2f}dB", tmp],
                   check=True, capture_output=True)
    os.replace(tmp, wav_path)
