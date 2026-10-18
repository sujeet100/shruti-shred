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
A note may also carry an optional "technique": "palm_mute" (a chug ROUTED to a genuinely
muted-guitar companion channel — the timbre change is what reads as a palm mute; a GM
clean-mute companion gets a distorted copy underneath for body, a routed muted-DISTORTION
patch needs none. The note sounds for a SHARE of its written duration, damped, not for a
fixed wall-clock chunk), "hammer_on"/"pull_off" (a softer
attack PLUS a fast pull from the previous note's pitch — real legato), or a
pitch-wheel gesture — "slide" (starts at the previous note's pitch, so it travels in
the line's own direction), "long_slide" (a wide, slower position shift from a fifth
below), "pick_scrape" (a dive from an octave ABOVE down onto the note — the
dragged-pick fall), or "bend" (up from the note). Because pitch-bend is channel-wide,
a gesture on a chorded rhythm channel moves the whole chord together — correct for a
slid/scraped power chord.

Andolan (oscillation): a held note may carry "andolan": true — the slow Darbari-style
sway, rendered on the pitch wheel: the note lands and SETTLES (~250 ms), then undulates
below itself toward the lower sruti in shallow (~30 cent), slow (~1/s), deliberately
non-identical waves (deterministic jitter — a periodic dip reads as machine vibrato),
while the expression (CC11) dips a hair alongside. It is the komal note that DEFINES
ragas like Darbari (komal g/d) and Bhairav (komal r/d); a straight, un-oscillated komal
there sounds like a different raga. Set deterministically by the lead generator on the
raga's own andolan swaras (never by the LLM); the renderer only sways holds long enough
in REAL time (ANDOLAN_MIN_MS) to carry the settle plus a slow wave — shorter flagged
notes play plain. Like meend it is a wheel gesture on a monophonic melodic channel; a
note carrying BOTH glides in first and then sways ("R -> g~~" — the research-correct
Darbari entry: the glide establishes the swara, one attack, no struck grace).
"""

import subprocess
from midiutil import MIDIFile
from raga import RAGAS, SWARAS
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
# KAN IS UNSTRUCK (2026-10-11 ornament research). On a sitar a kan is a LEFT-HAND touch, not a
# second stroke: rising, the player plucks the kan's fret and hammers onto the note (sparsh);
# falling, plucks the kan's fret and pulls off (krintan) — ITC: a "slightly metallic timbre [that]
# can never be reproduced by the human voice", the sitar's own sound. We used to strike every kan
# as separate crushed notes, which read as a plucked cluster. Now the note is plucked ONCE, on the
# beat, AT the kan's pitch (the wheel pre-set there) and the wheel STEPS — no glide — to the
# swara, one left-hand touch per kan. No source measures the touch, so its length is inference.
KAN_STEP_MS = 60         # one left-hand touch (inference: the research's 40-80 ms band)
KAN_MAX_SHARE = 0.4      # the kan never eats more than this share of its note
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

# Andolan — the SLOW pitch oscillation that IS the komal note in ragas like Darbari
# (komal g/d) and Bhairav (komal r/d). Research-grounded (AUTRIM/NCPA pitch graphs;
# Parrikar — see DESIGN.md): the note lands and SETTLES first, then undulates BELOW
# itself toward the lower sruti ("a progressive series of movements between Re and Ga"
# — never above), each wave slow (~1/s) and SHALLOW (~30 cents, research bound 20-35),
# and no two waves alike — a perfectly periodic dip is exactly what reads as machine
# vibrato (both the ±0.4 st sine at 420 ms and the half-semitone sin² at 850 ms we
# shipped first failed Sujit's ear this way). Waves are jittered DETERMINISTICALLY
# (the drum machine's humanization idiom — same input, same output, no RNG), keyed on
# the note's start so unison doubles sway in phase. Each wave sinks a little faster
# than it rises and the whole gesture ends at exactly 0 — nothing bleeds onward.
ANDOLAN_DEPTH_ST = 0.30      # the default dip when no direction is stamped (~30 cents below)
# The far turning point is AIMED, not drifting (Sujit, 2026-10-11: "does andolan happen between
# 2 notes or randomly at any cents?" — ITC: it "touches the periphery of an adjacent note", a
# raga-specific target). The July 65-100% depth jitter let it wander ~33-50 cents wave to wave;
# now only the TIMING varies freely and the depth stays within a few percent of the target.
ANDOLAN_DEPTH_SPREAD = 0.08  # each wave reaches 92-100% of the aimed depth
ANDOLAN_DELAY_MS = 150       # land and settle on the swara before the sway begins
ANDOLAN_PERIOD_MS = 700      # one slow undulation
ANDOLAN_MIN_MS = 800         # shortest NOTE (kan included) that carries the settle + one wave
# v4 (2026-10-12, measured on the solo sitar of fusion_20261012_213455): the soundfont's sitar
# loses ~20 dB in its first 0.6 s and ~30 dB by 1 s — far faster than a real sitar's jawari. A
# sway spread across a 1.5 s note dipped at 0.6 s, held there, and drew its return at -50 dB,
# so the last thing heard of Ga was a note 40 cents FLAT (Sujit: "0:07 sounds out of tune").
# The waves now fit inside the note's AUDIBLE life; after it the string rests on the swara.
ANDOLAN_AUDIBLE_MS = 1200
# v5 (2026-10-18): a raga whose andolan names a swing count (`Note.andolan_swings` from
# raga.ANDOLAN_SWINGS — Darbari 2-3, van der Meer & Rao + Sujit) sways LONGER: the sitar's NRPN
# sustain (SITAR_DECAY_TIMECENTS, +9 dB at 1 s) keeps it audible past the old window, and the
# sway fits as many of its swings as it can, none quicker than ANDOLAN_MIN_PERIOD_MS — still a
# slow swing, never vibrato. A note too short for the fewest keeps the default waves.
ANDOLAN_COUNTED_AUDIBLE_MS = 1800
ANDOLAN_MIN_PERIOD_MS = 500
ANDOLAN_STEPS_PER_CYCLE = 20 # wheel events per wave — dense enough that the curve has no zipper
ANDOLAN_CC11_DIP = 8         # expression dips a hair with the pitch (a pulled string darkens)
# v3 (2026-10-11 research): the sources describe GLIDES WITH HOLDS — "multiple meend in
# succession, punctuated by delicate holds" (Kumar et al., IIT Kanpur) — not a sine. Each wave
# rests on the swara, glides toward the neighbour, holds at its periphery, glides back.
# v4: no flat HOLD at the edge — held 300 ms, the dip read as a note gone flat, not a swing.
# The wave rests on the swara, sinks to TOUCH the periphery (the smoothstep's zero slope there
# is the brief turn) and returns more slowly than it went — the string dwells on its swara.
ANDOLAN_SHAPE = ((0.15, 0.0), (0.50, 1.0), (0.95, 0.0))  # (fraction, reach) knots
# A real sitar's pull bends ONE string while the sympathetic strings keep ringing the true note
# (Chiruthapudi, ISMIR 2022 LBD) — a pitch-bent sample moves its baked-in resonance too, and
# nothing holds steady. A quiet UNBENT copy of the swara on its own channel restores that anchor.
# Sujit, 2026-10-12: "play taraf only when the note is from the scale — any bent note should not
# trigger taraf". An unbent copy under a sway sat 40-50 cents from the bending string and beat
# against it (the sour 0:07 of fusion_20261012_213455). The taraf answers a plain, held swara
# only. It shares the chikari channel, whose level rose 96 -> 112, so its share drops to match.
TARAF_VEL_SHARE = 0.30       # the sympathetic layer sits well under the plucked string
TARAF_MIN_MS = 400           # a passing note is gone before a sympathetic string could answer it
# A note sung at its SHRUTI (Darbari's 22-shruti offsets reach at most 8 cents) is still "from the
# scale": its unbent taraf differs by a few cents — a slow shimmer under 2 beats a second, not the
# 40-50 cent clash of a sway — so it keeps the taraf. A larger offset counts as bent.
TARAF_INTONATION_TOLERANCE_CENTS = 10

# The SLOW (alap) meend — the sources' "very slow in early alap", the raga signposts (Malkauns
# g held long then glided to S; Jog g->S; Bhairavi n-d-P with a dwell on d) and Sujit's Bageshree
# Ma->Ga reverse bend. It HOLDS the source, then moves through the raga's own swaras in between
# with a short pause on each ("meend with rests", ITC), so the glide never smears through
# out-of-raga pitches. No source times it; the numbers are inference for the ear to tune.
SLOW_MEEND_MIN_MS = 350
SLOW_MEEND_PER_ST_MS = 120
SLOW_MEEND_MAX_MS = 1400
SLOW_MEEND_MAX_SHARE = 0.7   # of the note
SLOW_MEEND_HOLD = 0.3        # share of the glide spent holding the source before it moves
SLOW_MEEND_DWELL = 0.5       # share of each intermediate leg spent resting on that swara

# GAMAK — "a fast meend over 2-3 notes, repeated, played with force", distinguished from andolan
# by speed and by AUDIBLE start and end points (ITC). Swings up to the next raga swara and back,
# stopping on each. Rate is inference (vocal pitch-modulation studies: 3-10 Hz).
GAMAK_HZ = 6.0
GAMAK_MAX_CYCLES = 3
GAMAK_SHAPE = ((0.15, 0.0), (0.35, 1.0), (0.65, 1.0), (0.85, 0.0))

# Rhythm-guitar technique shaping (see _apply_technique / _render_slide / _render_bend).
# A chug sounds for a SHARE of its written slot, not a fixed wall-clock chunk. The old
# fixed 80ms gate (TuxGuitar/alphaTab's default) silently overrode every duration the riff
# agent wrote: measured on `out/fusion_20260720_183403.json`, an 8th-note chug sounded at a
# 32% gate and 21% of palm-muted notes were written a BEAT or longer and still played for
# 0.16 beats — a click followed by up to 1.84 beats of dead air. That gap is what reads as
# the machine-gun staccato, and because the PADS sections (manjha/antara/taan) write their
# long chords palm-muted, it is also what hollowed out the "ringing chord" support.
PALM_MUTE_GATE = 0.62    # a normal chug: sounds for this share of its slot, then damps
PALM_MUTE_MIN_MS = 55    # ...never shorter than a real picked chunk (a 16th stays audible)
PALM_MUTE_MAX_MS = 700   # ...never longer than a damped string physically rings, so a chug
                         # written on a long slot reads as a held mute, not a sustain
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
                            # the gate + muted layer keep it a chug, not a note

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
# reverb, sounds like noise" tone of the first live render. The tabla sits WETTER than the
# kit (52 -> 78, Sujit's ear 2026-07-16: "tabla is very dry") — the Indian Ensemble strokes
# are close-miked one-shots that need the room the metal samples carry baked in.
_REVERB_SEND = {"lead": 56,     # a touch drier than it was (68): closer, in front of the guitars "drone": 48, "rhythm": 30, "bass": 12, "tabla": 78, "drums": 38,
                "clean": 62,   # the clean arpeggios live in the room — shimmer, not chug
                # the orchestra lives in a CONCERT HALL: strings/choir wet and cinematic, brass
                # tighter so its stabs still punch, timpani drier so the low hits stay defined.
                "orch_strings": 80, "orch_choir": 85, "orch_brass": 55, "orch_timpani": 45,
                # the high drone strings ring out in the room, wetter than the melody (72 -> 90:
                # Sujit 2026-10-12, "needs more reverb/sustain")
                "chikari": 90}
_REVERB_SEND_DEFAULT = 40


def _reverb_send(role) -> int:
    return _REVERB_SEND.get(role, _REVERB_SEND_DEFAULT)


# Static mix level (MIDI CC7) per layer role — a light balance so the LEAD (sitar / lead guitar)
# no longer BURIES the rhythm guitars (Sujit, 2026-07-16: "the guitars are buried behind the lead
# tone now"). The melodic voices are pulled back; the TABLA is LIFTED (Sujit, same day: "I did
# not hear tabla" — the Indian Ensemble strokes sit at low velocity against a Power-kit at ~85
# and companions at CC7=127, so the theka needs channel volume the velocities can't give it).
# Rhythm / bass / drums keep their ear-calibrated default level, and the palm-mute companion
# keeps its own CC7=127 (MUTE_LEVEL) — so this cannot disturb the chug parity. None (unlisted
# role) = leave the channel at its default.
# The lead was pulled back to 92 when a doubling lead guitar shared the role and the two buried
# the riff; with the lead guitar OFF (config.lead_guitar_enabled, 2026-10-12) that cut only made
# the sitar "feeble compared to guitar" (Sujit), so the sitar comes back up.
_MIX_LEVEL = {"lead": 112, "drone": 74, "tabla": 115,
              "clean": 84,     # the harmony shimmer sits UNDER the lead voices
              # the orchestra is an ACCOMPANIST, not the star: strings/choir sit under the
              # band, brass a touch more present for its accents, timpani solid on the low end.
              "orch_strings": 82, "orch_choir": 84, "orch_brass": 90, "orch_timpani": 100,
              # level with the sitar: they are its own strings (96 -> 112, Sujit 2026-10-12:
              # "the volume felt less"); the velocities keep them under the melody's attacks
              "chikari": 112}


def _mix_level(role) -> int | None:
    return _MIX_LEVEL.get(role)


def _fine_tune(mf: MIDIFile, track: int, ch: int, cents: int) -> None:
    """Channel fine-tune via RPN 0,1 — shift the whole channel by `cents` (±100 max).
    A few cents on ONE side of the double-tracked rhythm pair decorrelates the two takes
    (two players, not one copied signal) without reading as chorus or detune."""
    value = max(0, min(16383, round(8192 * (1 + cents / 100))))
    mf.addControllerEvent(track, ch, 0, 101, 0)          # RPN MSB
    mf.addControllerEvent(track, ch, 0, 100, 1)          # RPN LSB -> RPN(0,1) = fine tuning
    mf.addControllerEvent(track, ch, 0, 6, value >> 7)   # data entry MSB
    mf.addControllerEvent(track, ch, 0, 38, value & 0x7F)  # data entry LSB


# The Indian Ensemble sitar decays ~30 dB in its first second — far faster than a real sitar,
# whose jawari keeps a note ringing for seconds — so an andolan or a loop drawn on a held note
# ran on into silence (Sujit, 2026-10-12: "do we need to increase sustain so certain bends get
# more time and don't chop midway?"). Measured: its fade is the preset's volume-ENVELOPE decay
# (a looped sample), so FluidSynth's SoundFont NRPN (MSB 120, LSB = generator 36 decayVolEnv)
# lengthens it: +1200 timecents doubles the decay time — about 5 dB louder at 0.5 s and 9 dB at
# 1 s (-30 -> -21 dB/s). The sustain level and release generators changed nothing. Kept moderate:
# a much longer decay exposes the sample's loop. Synths without SF2 NRPNs ignore it.
SITAR_DECAY_TIMECENTS = 1200
_NRPN_SF2 = 120                     # FluidSynth's SoundFont-generator NRPN space
_GEN_DECAY_VOL_ENV = 36


def _sitar_sustain(mf: MIDIFile, track: int, ch: int) -> None:
    """Lengthen a sitar channel's ring (see SITAR_DECAY_TIMECENTS)."""
    value = 8192 + SITAR_DECAY_TIMECENTS
    mf.addControllerEvent(track, ch, 0, 99, _NRPN_SF2)            # NRPN MSB
    mf.addControllerEvent(track, ch, 0, 98, _GEN_DECAY_VOL_ENV)   # NRPN LSB = the generator
    mf.addControllerEvent(track, ch, 0, 6, value >> 7)            # data entry MSB
    mf.addControllerEvent(track, ch, 0, 38, value & 127)          # data entry LSB


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


def chord_voicing(root: int, tone_pitches: list[int]) -> list[int]:
    """The chord tones that SOUND above a sounding root, in order, deduped and excluding the
    root itself: each tone seated at its distortion-consonant interval (`_seat_chord_tone`),
    a tone with no clean seat degraded to octave weight. Shared by the renderer and by
    anything that must reason about the exact pitches a chord will play (e.g. fingering it on
    a guitar). Pure."""
    seated: list[int] = []
    for pitch in tone_pitches:
        tone = _seat_chord_tone(root, pitch)
        if tone is None:
            tone = root + 12                  # dissonant colour -> octave weight instead
        if tone != root and tone not in seated:
            seated.append(tone)
    return seated


def _chug_gate(dur: float, bpm: float) -> float:
    """The sounding length of a palm-muted note: a SHARE of its written slot (so the chug
    breathes with the rhythm at any tempo), bounded by what a damped string can actually
    do — never shorter than a picked chunk, never longer than a mute rings, never past the
    slot itself. Pure."""
    beats_per_ms = bpm / 60000.0
    gate = dur * PALM_MUTE_GATE
    gate = max(gate, PALM_MUTE_MIN_MS * beats_per_ms)
    gate = min(gate, PALM_MUTE_MAX_MS * beats_per_ms)
    return min(gate, dur)


def _apply_technique(technique, dur: float, vel: int, bpm: float) -> tuple[float, int]:
    """Return (dur, vel) shaped for a technique's ATTACK/SUSTAIN — the part that is
    pure note geometry (pitch gestures are rendered separately). A palm-mute chug
    gates to a fixed WALL-CLOCK length (capped at the written duration) and lands
    slightly softer; a hammer-on/pull-off is a softer legato attack; slide and bend
    leave dur/vel alone (they only move the pitch wheel). Pure."""
    if technique == "palm_mute":
        # the gate alone shapes the chug — no velocity cut: the muted TIMBRE already
        # carries the softness, and attenuating on top of it buried the chugs
        return round(_chug_gate(dur, bpm), 4), vel
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


_INTONATION_RESET_S = 0.003   # an intoned note hands the wheel back this long before it ends —
                              # earlier than the next note's kan pre-bend (<= 1 ms) at any tempo


class _Intoned:
    """The MIDI file as ONE note's gestures see it: every pitch-wheel value shifted by the note's
    intonation (`Note.cents`), everything else passed through untouched."""

    def __init__(self, mf: MIDIFile, shift: int) -> None:
        self._mf, self._shift = mf, shift

    def addPitchWheelEvent(self, track: int, ch: int, t: float, value: int) -> None:  # noqa: N802
        self._mf.addPitchWheelEvent(track, ch, t, max(-8192, min(8191, value + self._shift)))

    def __getattr__(self, name: str):
        return getattr(self._mf, name)


def _bends(n: dict) -> bool:
    """Does this note move the pitch wheel — a meend glide, a slide/bend technique, or an
    andolan oscillation? Any of these needs the channel's wide bend range armed up front."""
    return (n.get("meend_swara") is not None
            or n.get("technique") in ("slide", "long_slide", "pick_scrape", "bend",
                                      "hammer_on", "pull_off")
            or bool(n.get("andolan"))
            or bool(n.get("grace"))
            or bool(n.get("gamak_st"))
            or bool(n.get("cents")))


def kan_pitch(sa: int, swara: str, near: int) -> int:
    """A kan swara's pitch: the octave of it NEAREST the note it decorates — a kan is a
    neighbour. (Taken in the note's own octave, a kan of Ni on Sa sounded ten semitones ABOVE
    Sa instead of one below.) Pure."""
    base = sa + SWARAS[swara]
    return base + 12 * round((near - base) / 12)


def _kan_wheel(start: float, dur: float, bpm: float,
               offsets: list[int]) -> tuple[list[tuple[float, int]], float]:
    """Pure: the wheel steps for an unstruck kan and the beats it consumes. The first value is
    set a hair BEFORE the onset so the single pluck already sounds at the kan's pitch; each
    later kan, then the swara itself (0), arrives as an instant step — a finger, not a glide."""
    each = min(KAN_STEP_MS * bpm / 60000.0, dur * KAN_MAX_SHARE / len(offsets))
    events = [(round(max(0.0, start - 0.001), 4), _wheel(offsets[0]))]
    for j, off in enumerate(offsets[1:], start=1):
        events.append((round(start + j * each, 4), _wheel(off)))
    used = each * len(offsets)
    events.append((round(start + used, 4), 0))
    return events, used


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


def _render_bend(mf: MIDIFile, track: int, ch: int, start: float, dur: float,
                 st: float = BEND_ST) -> None:
    """Bend UP: wheel rises from 0 to `st` semitones over the first half, holds, then
    recenters at note end. The apex HOLDS, so `st` must land on a real pitch — the
    sequencer stamps a raga-aware depth per note (`bend_st`, the next enterable swara);
    BEND_ST is only the fallback for hand-authored dicts. On a polyphonic (chorded)
    channel the whole chord bends together — acceptable, and correct for a slid/bent
    power chord."""
    glide = dur * BEND_FRAC
    steps = max(4, min(24, int(glide / 0.02)))
    for k in range(steps + 1):
        t = start + glide * k / steps
        mf.addPitchWheelEvent(track, ch, round(t, 4), _wheel(st * k / steps))
    mf.addPitchWheelEvent(track, ch, round(start + dur, 4), 0)


# The ring-out (fade) — the intro's final Sa resolving "like a struck chord dying away"
# (Sujit): expression (CC11) decays across the note with a quadratic ease (fast at first,
# settling — the shape of a real string's decay), to a quiet floor rather than silence,
# then snaps back to full at the note's end so the next section is untouched.
_FADE_FLOOR = 16          # CC11 the decay settles on (quiet, still ringing)
_FADE_RESET_LEAD = 0.004  # beats before the next attack that expression returns to full
_FADE_STEPS = 24          # events across the note — dense enough to sound continuous


def _fade_ramp(start: float, dur: float, *, floor: int = _FADE_FLOOR,
               reset: bool = True) -> list[tuple[float, int]]:
    """Pure: the (time, CC11-value) ramp for a ring-out, ending with the reset to full
    unless `reset` is off (the piece's final tail — nothing follows it, and a snap back to
    full on the note-off tick lifts the sample's release into an audible blip)."""
    ramp: list[tuple[float, int]] = []
    for k in range(_FADE_STEPS + 1):
        frac = k / _FADE_STEPS
        level = floor + (127 - floor) * (1.0 - frac) ** 2
        ramp.append((round(start + dur * frac, 4), round(level)))
    if reset:
        ramp.append((round(start + dur, 4), 127))    # snap back — the fade never bleeds onward
    return ramp


def _render_fade(mf: MIDIFile, track: int, ch: int, start: float, dur: float, *,
                 floor: int = _FADE_FLOOR, reset: bool = True) -> None:
    for t, val in _fade_ramp(start, dur, floor=floor, reset=reset):
        mf.addControllerEvent(track, ch, t, 11, val)


def _andolan_jitter(start: float, k: int) -> float:
    """Deterministic fraction in [0, 1) keyed on (note start, wave index) — the drum
    machine's no-RNG humanization idiom (`drum_patterns.humanized`), so renders stay
    reproducible and unison doubles at the same start sway in phase."""
    key = (int(round(start * 8)) * 2654435761 + k * 40503 + 12289) & 0xFFFFFFFF
    return (key % 1024) / 1024.0


def _smooth(x: float) -> float:
    return x * x * (3.0 - 2.0 * x)


def _knot_shape(frac: float, knots: tuple[tuple[float, float], ...]) -> float:
    """Pure: a held-and-glided wave — flat between knots, a smoothstep between them. The
    reach starts and ends at 0 (on the swara)."""
    prev_x, prev_y = 0.0, 0.0
    for x, y in knots:
        if frac <= x:
            span = x - prev_x
            u = 1.0 if span <= 0 else (frac - prev_x) / span
            return prev_y + (y - prev_y) * _smooth(min(1.0, max(0.0, u)))
        prev_x, prev_y = x, y
    return prev_y


def _wave_count(sway_ms: float, swings: tuple[int, int] | None) -> int:
    """How many waves a sway of `sway_ms` carries: the default slow period's worth, or — where the
    raga counts its swings — the most of (fewest, most) that fit at ANDOLAN_MIN_PERIOD_MS or
    slower, falling back to the default when even the fewest do not. Pure."""
    default = max(1, int(round(sway_ms / ANDOLAN_PERIOD_MS)))
    if swings is None:
        return default
    fewest, most = swings
    fit = int(sway_ms // ANDOLAN_MIN_PERIOD_MS)
    return min(most, fit) if fit >= fewest else default


def _andolan_wheel(start: float, dur: float, bpm: float,
                   after_glide: bool = False,
                   depth_st: float = -ANDOLAN_DEPTH_ST, *, note_ms: float | None = None,
                   lead_ms: float | None = None,
                   swings: tuple[int, int] | None = None) -> list[tuple[float, int]]:
    """Pure: the (time, wheel) ramp for an andolan — land, settle, then a slow, one-sided
    undulation dipping BELOW the note toward its lower sruti. The pitch holds steady for
    ANDOLAN_DELAY_MS, then sways in waves of deterministically varied length and depth
    (periodic dips read as machine vibrato); each wave sinks a little faster than it
    rises (trough at ~40%) and the last sample lands exactly on 0 at the note's end —
    no bleed into the next note. A hold shorter than ANDOLAN_MIN_MS in real time plays
    plain (the gate lives HERE because only the renderer knows the tempo; the generator
    flags the swara, real time decides the gesture). `after_glide` = a meend leads INTO
    the sway ("R -> g~~"): the glide owns the onset, so the settle-at-0 event is dropped
    (it would yank the wheel to 0 mid-glide); the settle window always outlasts the
    glide (ANDOLAN_DELAY_MS 250 > MEEND_GLIDE_MAX_MS 220), so the first wave still
    departs from a settled swara.

    v4: the gate reads the whole NOTE (`note_ms`, a kan included — the kan used to push a
    one-second Ga under the gate, so it played plain while its neighbours swayed), and the waves
    are drawn only within the note's audible life (`ANDOLAN_AUDIBLE_MS`, counted from the attack:
    `lead_ms` is how much of it a kan or glide already used); the string then rests on 0.
    v5: `swings` (the raga's counted range) lengthens the window and sets the wave count
    (`_wave_count`)."""
    dur_ms = dur * 60000.0 / bpm
    if (note_ms if note_ms is not None else dur_ms) < ANDOLAN_MIN_MS:
        return []                                        # too short to sway — leave it clean
    audible_ms = ANDOLAN_COUNTED_AUDIBLE_MS if swings else ANDOLAN_AUDIBLE_MS
    window_ms = min(dur_ms, audible_ms - (lead_ms or 0.0))
    if window_ms - ANDOLAN_DELAY_MS < 0.75 * ANDOLAN_PERIOD_MS:
        return []                                        # no room for one whole wave while audible
    delay = ANDOLAN_DELAY_MS * bpm / 60000.0             # the settle, in beats
    sway = window_ms * bpm / 60000.0 - delay             # the swaying span, in beats
    n = _wave_count(window_ms - ANDOLAN_DELAY_MS, swings)
    lengths = [0.85 + 0.3 * _andolan_jitter(start, k) for k in range(n)]        # ±15% per wave
    depths = [depth_st * (1.0 - ANDOLAN_DEPTH_SPREAD * _andolan_jitter(start, n + k))
              for k in range(n)]                                                # aimed, ±a hair
    total = sum(lengths)
    ramp: list[tuple[float, int]] = [(round(start, 4), 0)]   # settle flat until the first wave
    left, cum = start + delay, 0.0
    for k in range(n):
        cum += lengths[k]
        right = start + delay + sway * (cum / total)     # wave k ends here; wave n-1 at dur
        span = right - left
        for i in range(1, ANDOLAN_STEPS_PER_CYCLE + 1):
            frac = i / ANDOLAN_STEPS_PER_CYCLE
            reach = _knot_shape(frac, ANDOLAN_SHAPE)     # rest, glide, hold at the edge, return
            ramp.append((round(left + span * frac, 4), _wheel(depths[k] * reach)))
        left = right
    return ramp[1:] if after_glide else ramp


def sways(dur: float, bpm: float, *, lead_ms: float = 0.0,
          swings: tuple[int, int] | None = None) -> bool:
    """Whether a flagged andolit note of `dur` beats is drawn with a sway at `bpm` — this
    renderer's own gate (`_andolan_wheel`), so a report can never disagree with the render.
    `lead_ms` is what a kan or glide already used of the note's audible life. Pure."""
    return bool(_andolan_wheel(0.0, dur, bpm, note_ms=dur * 60000.0 / bpm, lead_ms=lead_ms,
                               swings=swings))


def _swings(n: dict) -> tuple[int, int] | None:
    """The note's counted swing range, if its raga names one (JSON carries it as a list)."""
    counted = n.get("andolan_swings")
    return (int(counted[0]), int(counted[1])) if counted else None


def _andolan_cc(wheel_val: int, depth_st: float = ANDOLAN_DEPTH_ST) -> int:
    """Expression (CC11) tracking the sway: the level dips a hair as the pitch moves away from
    the swara — a pulled string darkens — and recenters to full (127) as the wheel returns."""
    full = abs(_wheel(abs(depth_st)))
    depth = abs(wheel_val) / full if full else 0.0
    return 127 - round(ANDOLAN_CC11_DIP * min(1.0, depth))


def _render_andolan(mf: MIDIFile, track: int, ch: int, start: float, dur: float,
                    bpm: float, *, shimmer: bool = True, after_glide: bool = False,
                    depth_st: float = -ANDOLAN_DEPTH_ST, note_ms: float | None = None,
                    lead_ms: float | None = None, swings: tuple[int, int] | None = None) -> bool:
    """Draw the sway on the wheel, with the expression shimmer riding the same curve.
    `shimmer` is off when the note also carries a fade — the fade owns CC11 then.
    `after_glide` is set when a meend leads INTO the sway (see `_andolan_wheel`). Returns
    whether a sway was drawn (a hold under the real-time gate plays plain)."""
    events = _andolan_wheel(start, dur, bpm, after_glide=after_glide, depth_st=depth_st,
                            note_ms=note_ms, lead_ms=lead_ms, swings=swings)
    for t, val in events:
        mf.addPitchWheelEvent(track, ch, t, val)
        if shimmer:
            mf.addControllerEvent(track, ch, t, 11, _andolan_cc(val, depth_st))
    return bool(events)


def slow_meend_wheel(start: float, dur: float, from_pitch: int, to_pitch: int, bpm: float,
                     via: list[int]) -> list[tuple[float, int]]:
    """Pure: the wheel for a SLOW alap meend, anchored on the target like the quick one: hold
    the source, then move through each raga swara in `via` (pitches strictly between, in
    travel order) with a short rest on it, and settle on the target at 0."""
    pre = from_pitch - to_pitch
    if pre == 0:
        return []
    ms = min(SLOW_MEEND_MAX_MS, max(SLOW_MEEND_MIN_MS, SLOW_MEEND_PER_ST_MS * abs(pre)))
    glide = min(ms * bpm / 60000.0, dur * SLOW_MEEND_MAX_SHARE)
    hold = glide * SLOW_MEEND_HOLD
    stops = [p - to_pitch for p in via] + [0]
    leg = (glide - hold) / len(stops)
    ramp: list[tuple[float, int]] = [(round(max(0.0, start - 0.002), 4), _wheel(pre)),
                                     (round(start + hold, 4), _wheel(pre))]
    t, level = start + hold, float(pre)
    for stop in stops:
        move = leg * (1.0 - SLOW_MEEND_DWELL) if stop != 0 else leg
        steps = 10
        for k in range(1, steps + 1):
            frac = _smooth(k / steps)
            ramp.append((round(t + move * k / steps, 4), _wheel(level + (stop - level) * frac)))
        t, level = t + leg, float(stop)
        if stop != 0:
            ramp.append((round(t, 4), _wheel(stop)))          # the rest on the passing swara
    return ramp


def meend_via(raga: str, sa: int, from_pitch: int, to_pitch: int) -> list[int]:
    """The raga swaras a slow meend passes on its way, in travel order — the ascending ladder
    going up, the descending one going down, so the pauses are on swaras the raga really
    sings in that direction. Pure."""
    ladder = RAGAS[raga]["aroha" if to_pitch > from_pitch else "avaroha"] if raga in RAGAS else []
    lo, hi = sorted((from_pitch, to_pitch))
    pitches = {sa + SWARAS[sw] + 12 * k for sw in ladder for k in range(-4, 5)}
    between = sorted(p for p in pitches if lo < p < hi)
    return between if to_pitch > from_pitch else between[::-1]


_PATH_STEPS = 8              # wheel events per moving segment of a gesture path
# A pulled string loses a little energy and brightness while it is held away from its fret: a
# loop to Ma at full level on the same bright sample read as a separate NOTE (fusion_
# 20261012_213455 at 0:32.5 / 0:34 / 0:40.5). Expression dips with the pull and returns on the
# swara. (Inference, for the ear — the measured paths give the pitch, not the level.)
PULL_CC11_DIP = 14


def path_wheel(start: float, dur: float, bpm: float,
               path: list[list[float]]) -> tuple[list[tuple[float, int]], float]:
    """Pure: the wheel events for a gesture path of (ms, semitones) knots, and the beats it
    uses. Held segments emit one event; moving ones a smoothstep. A path longer than the note
    is not drawn (the caller only stamps paths that fit) — returns ([], 0.0). A path that
    starts AWAY from the swara (a release — plucked already pulled to the neighbour) sets the
    wheel a hair before the onset, as a kan and a slow meend do, so the pluck itself sounds
    there instead of on the swara with a jump a tick later."""
    def beat(ms: float) -> float:
        return ms * bpm / 60000.0

    used = beat(path[-1][0])
    if used > dur or len(path) < 2:
        return [], 0.0
    onset = start if path[0][1] == 0 else max(0.0, start - 0.002)
    events: list[tuple[float, int]] = [(round(onset, 4), _wheel(path[0][1]))]
    for (t0, v0), (t1, v1) in zip(path, path[1:]):
        steps = 1 if v0 == v1 else _PATH_STEPS
        for k in range(1, steps + 1):
            frac = k / steps
            events.append((round(start + beat(t0 + (t1 - t0) * frac), 4),
                           _wheel(v0 + (v1 - v0) * _smooth(frac))))
    return events, used


def gamak_wheel(start: float, dur: float, bpm: float, st: int) -> list[tuple[float, int]]:
    """Pure: a gamak — up to `st` semitones (the next raga swara) and back, with a stop on each,
    `GAMAK_HZ` times a second for at most `GAMAK_MAX_CYCLES`, then resting on the note."""
    cycle = bpm / (60.0 * GAMAK_HZ)                      # one swing, in beats
    cycles = min(GAMAK_MAX_CYCLES, int(dur / cycle))
    if cycles < 1 or st == 0:
        return []
    ramp: list[tuple[float, int]] = [(round(start, 4), 0)]
    for c in range(cycles):
        for i in range(1, 13):
            frac = i / 12
            ramp.append((round(start + cycle * (c + frac), 4),
                         _wheel(st * _knot_shape(frac, GAMAK_SHAPE))))
    return ramp


def _chikari_channel(layers: list[dict]) -> int | None:
    """The chikari layer's channel, if the piece has one (crew/chikari.py). The chikari and the
    taraf are both the sitar's UNBENT strings on the sitar's own patch, so the taraf rides this
    channel rather than claiming a companion of its own — with the orchestra and both
    palm-mute companions in play, a separate one would starve a chug channel."""
    return next((la["channel"] for la in layers
                 if la.get("role") == "chikari" and la.get("channel") is not None), None)


def _taraf_channel(mf: MIDIFile, track: int, layer: dict, used: set[int],
                   shared: int | None = None) -> int | None:
    """The sympathetic-string companion for a sitar layer: the `shared` unbent-string channel
    when there is one (already set up by its own layer), else the first free channel, on the
    layer's own program, pan and reverb, never bent. None when no channel is free."""
    if shared is not None and layer.get("instrument") == "sitar":
        return shared
    ch = next((c for c in range(16) if c != 9 and c not in used), None)
    if ch is None:
        return None
    used.add(ch)
    if layer.get("bank") is not None:            # the same routed sitar (e.g. the Indian Ensemble)
        mf.addControllerEvent(track, ch, 0, 0, layer["bank"] // 128)
        mf.addControllerEvent(track, ch, 0, 32, layer["bank"] % 128)
    if "program" in layer:
        mf.addProgramChange(track, ch, 0, layer["program"])
    if layer.get("pan") is not None:
        mf.addControllerEvent(track, ch, 0, 10, max(0, min(127, layer["pan"])))
    mf.addControllerEvent(track, ch, 0, 91, _reverb_send(layer.get("role")))
    if layer.get("instrument") == "sitar":
        _sitar_sustain(mf, track, ch)
    return ch


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
    unbent_strings = _chikari_channel(layers)
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
            lvl = _mix_level("tabla")                 # the theka's channel-volume lift — its own
            if lvl is not None:                       # channel only (the GM-conga fallback shares
                mf.addControllerEvent(i, ch, 0, 7, lvl)  # channel 9 with the kit: never lift there)
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
        lvl = _mix_level(layer.get("role"))          # pull the melodic voices back under the rhythm wall
        if lvl is not None:
            mf.addControllerEvent(i, ch, 0, 7, lvl)
        if layer.get("detune_cents"):
            _fine_tune(mf, i, ch, layer["detune_cents"])
        if layer.get("instrument") == "sitar":
            _sitar_sustain(mf, i, ch)
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
        raga = comp.get("raga", "")
        taraf: list[int] = []               # the sympathetic companion, opened on first sway

        def _sympathetic(p: int, start: float, length: float, v: int) -> None:
            # The taraf rings with a PLAIN held swara only (see the rule after the gestures): a
            # sympathetic string sounds the scale's own pitch, so under a bending string it was a
            # detuned unison (Ga against a loop to Ma; a 40-50 cent beat under every sway).
            if length <= 0:
                return
            if not taraf:
                ch_t = _taraf_channel(mf, i, layer, used_channels, shared=unbent_strings)
                if ch_t is None:
                    return
                taraf.append(ch_t)
            mf.addNote(i, taraf[0], p, start, length, max(1, int(v * TARAF_VEL_SHARE)))

        prev_pitch: int | None = None       # the previous SOUNDING pitch (legato/slide context)
        prev_end = -1.0
        faded_from: float | None = None     # a ring-out fade left CC11 down from this beat
        for n in layer["notes"]:
            if faded_from is not None:      # restore expression just BEFORE the next attack
                mf.addControllerEvent(i, ch, max(faded_from, n["start"] - _FADE_RESET_LEAD),
                                      11, 127)
                faded_from = None
            oct = n.get("oct", 0)
            vel = n.get("vel", 100)
            # Technique first: it shapes the note's length/attack before it is sounded
            # (the chug of a palm-mute, the softer legato of a hammer-on/pull-off).
            dur, vel = _apply_technique(n.get("technique"), n["dur"], vel, bpm)
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
                    # ...plus the distorted body underneath ONLY when the companion is GM's
                    # CLEAN mute, which has no gain of its own. A routed muted-DISTORTION
                    # patch (`pm_bank`) is self-sufficient — doubling it fired two identical
                    # attacks at the same pitch, velocity and length on two channels, which
                    # is a comb-filtered machine-gun transient, not a thicker chug. `real_pm`
                    # was computed for exactly this and then never read (the branch the
                    # `_mute_channel` docstring always described, finally implemented).
                    if not real_pm:
                        mf.addNote(i, ch, p, n["start"], dur, max(1, int(vel * MUTE_BODY_VEL)))
                else:
                    mf.addNote(i, ch, p, n["start"], dur, vel)

            _sound(sounding)
            # Chord: extra raga swaras sounded WITH the root, each seated at a distortion-
            # consonant interval (see `_seat_chord_tone`); a tone with no clean seat under
            # gain degrades to octave weight. Seats are deduped — two tones landing on the
            # same pitch would double a note-on on one channel.
            seated = [sounding, *chord_voicing(sounding, [sa + SWARAS[csw] + 12 * oct
                                                          for csw in n.get("chord") or []])]
            for tone in seated[1:]:
                _sound(tone)
            # A ring-out fades the note's expression like a dying string (independent of the
            # wheel gestures below — CC11, not pitch).
            fading = bool(n.get("fade") or n.get("fade_tail"))   # the fade owns CC11 then
            if n.get("fade"):
                # no snap back at the note-off: that lifted the dying release into a blip (GPT,
                # 2026-10-12: "127 -> 16, then an immediate reset to 127"); the reset waits for
                # the next attack on this channel instead
                _render_fade(mf, i, ch, n["start"], dur, reset=False)
                faded_from = n["start"]
            elif n.get("fade_tail"):
                tail = min(n["fade_tail"], dur)          # the piece's end: decay to silence
                _render_fade(mf, i, ch, n["start"] + dur - tail, tail, floor=0, reset=False)
            # PITCH-WHEEL SAFETY — the wheel is CHANNEL-WIDE, so a gesture on a note that
            # sounds a chord sweeps every tone of that chord together. A guitarist cannot do
            # that: a power chord changing position is a new fretted attack with string
            # noise, not the whole shape rubber-banding. Measured on the 2026-07-20 render,
            # 85 of the rhythm guitar's 146 wheel gestures (58%) rode a chord — the "weird,
            # nobody-in-metal-does-that" sound. A voicing therefore stays FIRMLY FRETTED, and
            # continuous pitch movement stays where it belongs: the sitar's single line.
            # (The legato branch already carried this guard; it is now the rule for all.)
            polyphonic = len(seated) > 1
            # The unstruck kan comes first: the pluck sounds at the kan, the finger steps onto
            # the note, and any glide or sway starts from there. A chord takes no kan — the
            # wheel would drag the whole voicing — so it stays a clean fretted attack.
            g_start, g_dur = n["start"], dur
            bent = False                        # did any gesture move this note's pitch?
            # A note's own INTONATION (`cents`, e.g. an ati-komal swara) shifts every wheel value
            # its gestures draw, and holds it under a plain note; the next attack resets it.
            shift = _wheel(n["cents"] / 100) if n.get("cents") and not polyphonic else 0
            wm = _Intoned(mf, shift) if shift else mf
            if shift:
                # a static shruti offset is not a bend: a note within the tolerance keeps its taraf
                bent = abs(n["cents"]) > TARAF_INTONATION_TOLERANCE_CENTS
                wm.addPitchWheelEvent(i, ch, round(max(0.0, n["start"] - 0.001), 4), 0)
                reset = n["start"] + dur - _INTONATION_RESET_S * bpm / 60.0   # before any kan pre-bend
                mf.addPitchWheelEvent(i, ch, round(max(n["start"], reset), 4), 0)

            def _ms(beats: float) -> float:
                return beats * 60000.0 / bpm

            if n.get("grace") and not polyphonic:
                offsets = [kan_pitch(sa, gsw, pitch) - sounding for gsw in n["grace"]]
                events, used = _kan_wheel(n["start"], dur, bpm, offsets)
                # with a meend to follow, its own pre-bend replaces the step back to 0
                for t, val in events[:-1] if target is not None else events:
                    wm.addPitchWheelEvent(i, ch, t, val)
                g_start, g_dur = n["start"] + used, max(dur - used, 0.0)
                bent = True
            # Pitch-wheel gestures: a meend glide to a target swara, a riff
            # slide/bend/legato, or a slow andolan sway on a held komal note. One per
            # note, EXCEPT meend + andolan, which compose (glide in, settle, sway).
            # Legato and slide read the PREVIOUS note's pitch — a hammer-on/pull-off is a
            # finger moving from where the line just was, and a slide travels in the line's
            # own direction; a fixed offset reads as a synth blip, not a hand.
            connected = prev_pitch if n["start"] - prev_end <= LEGATO_MAX_GAP else None
            if polyphonic:
                pass                             # a chord is fretted, never bent (see above)
            elif target is not None:
                bent = True
                sway_from = g_start
                if n.get("meend_style") == "slow":
                    ramp = slow_meend_wheel(g_start, g_dur, pitch, target, bpm,
                                            meend_via(raga, sa, pitch, target))
                    for t, val in ramp:
                        wm.addPitchWheelEvent(i, ch, t, val)
                    sway_from = ramp[-1][0] if ramp else g_start   # a slow glide outlasts the settle
                else:
                    _render_meend(wm, i, ch, g_start, g_dur, pitch, target, bpm)
                    sway_from = g_start + _meend_glide_beats(abs(target - pitch), g_dur, bpm)
                if n.get("andolan"):             # meend INTO the sway: glide, settle, undulate
                    depth = n.get("andolan_st") or -ANDOLAN_DEPTH_ST
                    _render_andolan(wm, i, ch, sway_from, g_start + g_dur - sway_from, bpm,
                                    shimmer=not fading, after_glide=True, depth_st=depth,
                                    note_ms=_ms(dur), lead_ms=_ms(sway_from - n["start"]),
                                    swings=_swings(n))
            elif n.get("technique") == "slide":
                bent = True
                st = _pull_offset(connected, sounding, SLIDE_FROM_PREV_MAX) or SLIDE_IN_ST
                _render_slide(wm, i, ch, n["start"], dur, st=st)
            elif n.get("technique") == "long_slide":
                bent = True
                _render_slide(wm, i, ch, n["start"], dur,
                              st=LONG_SLIDE_ST, frac=LONG_SLIDE_FRAC)
            elif n.get("technique") == "pick_scrape":
                bent = True
                _render_slide(wm, i, ch, n["start"], dur,
                              st=SCRAPE_ST, frac=SCRAPE_FRAC)
            elif n.get("technique") in ("hammer_on", "pull_off"):
                st = _pull_offset(connected, sounding, LEGATO_PULL_MAX)
                if st is not None:               # no usable previous note: soft attack only
                    bent = True
                    _render_slide(wm, i, ch, n["start"], dur, st=st, frac=LEGATO_PULL_FRAC)
            elif n.get("technique") == "bend":
                bent = True
                _render_bend(wm, i, ch, n["start"], dur, st=n.get("bend_st") or BEND_ST)
            elif n.get("pitch_path"):
                # a measured raga GESTURE (src/gestures.py): draw its whole path, then let a
                # long held note settle into its slow sway after it, as after a glide
                events, used = path_wheel(g_start, g_dur, bpm, n["pitch_path"])
                full = max((abs(v) for _, v in events), default=0)
                for t, val in events:
                    wm.addPitchWheelEvent(i, ch, t, val)
                    if full and not fading:
                        wm.addControllerEvent(i, ch, t, 11,
                                              127 - round(PULL_CC11_DIP * abs(val) / full))
                bent = bent or bool(events)
                rest = g_dur - used
                if n.get("andolan") and rest > 0:
                    depth = n.get("andolan_st") or -ANDOLAN_DEPTH_ST
                    bent = _render_andolan(wm, i, ch, g_start + used, rest, bpm,
                                           shimmer=not fading, after_glide=True, depth_st=depth,
                                           note_ms=_ms(dur),
                                           lead_ms=_ms(g_start + used - n["start"]),
                                           swings=_swings(n)) or bent
            elif n.get("andolan"):
                depth = n.get("andolan_st") or -ANDOLAN_DEPTH_ST
                bent = _render_andolan(wm, i, ch, g_start, g_dur, bpm, shimmer=not fading,
                                       depth_st=depth, note_ms=_ms(dur),
                                       lead_ms=_ms(g_start - n["start"]), swings=_swings(n)) or bent
            elif n.get("gamak_st"):
                for t, val in gamak_wheel(g_start, g_dur, bpm, n["gamak_st"]):
                    wm.addPitchWheelEvent(i, ch, t, val)
                    bent = True
            # The taraf answers only a PLAIN swara — struck and held unbent, long enough for a
            # sympathetic string to ring with it. A bent note (kan, meend, sway, gesture, gamak,
            # slide) never wakes it: under a moving string an unbent copy is a detuned unison.
            if (not bent and not polyphonic and layer.get("instrument") == "sitar"
                    and layer.get("role") == "lead" and _ms(dur) >= TARAF_MIN_MS):
                _sympathetic(sounding, n["start"], dur, vel)
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
    _compress_wav(wav_path)
    _normalize_wav(wav_path)
    return wav_path


# Peak-normalize the rendered WAV to this ceiling. This delivers the loudness Sujit
# picked in the Songsterr A/B without the clipping (their player runs synth gain 1.2,
# pinning peaks at 0 dBFS): the synth keeps its calibrated headroom gain and the file
# is lifted afterwards. -2.0 ≈ their "gain 1.0" (Sujit dialed the first -0.5 ceiling
# back, 2026-07-15). Skipped silently when ffmpeg is absent.
NORMALIZE_PEAK_DB = -2.0


# A gentle BUS COMPRESSOR before the peak-normalise (Sujit, 2026-10-12: "would using a compressor
# help?" — yes, as the second half of evening the dynamics; the first is the narrower energy arc in
# crew/dynamics.py). It smooths what the arrangement leaves and tames the breakdown peaks that hit
# 0 dBFS, which in turn lets the normaliser lift the whole mix. Low ratio, soft knee, and an attack
# slow enough to let a sitar pluck's transient through; heavier settings pump and flatten the
# plucks. Inference for the ear — tune here.
BUS_COMPRESSOR = "acompressor=threshold=-20dB:ratio=2.5:attack=25:release=250:knee=4"


def _compress_wav(wav_path: str) -> None:
    """Run the mix through `BUS_COMPRESSOR`; a no-op without ffmpeg."""
    import os
    import shutil
    if shutil.which("ffmpeg") is None:
        return
    tmp = wav_path + ".comp.wav"
    subprocess.run(["ffmpeg", "-y", "-i", wav_path, "-af", BUS_COMPRESSOR, tmp],
                   check=True, capture_output=True)
    os.replace(tmp, wav_path)


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
