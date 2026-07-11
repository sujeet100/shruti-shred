"""
POC: hand-authored Raga Bhairav x djent-metal fusion -> MIDI -> WAV.

This is the RISK-CHECK for V1: prove that FluidSynth + a GM soundfont
(Distortion Guitar, program 30 -- the same patch Songsterr uses) can render
a raga-constrained djent clip that clears the "sounds good enough" bar,
BEFORE we build the CrewAI agent crew on top.

Nothing here is agentic yet. The notes are hand-written but follow real
Raga Bhairav grammar so the timbre/quality is representative of what the
agents will eventually produce.

Raga Bhairav (Sa = C):
  Sa  re(komal) Ga  Ma  Pa  dha(komal) Ni  Sa'
  C   Db        E   F   G   Ab         B   C'
  Vadi = Dha (komal), Samvadi = Re (komal). Both komal notes are the
  signature of the raga -- get them wrong and any Hindustani listener
  hears it instantly. That's exactly what the Guru-critic agent will guard.
"""

import os

from midiutil import MIDIFile

# ---- tuning / structure ------------------------------------------------
BPM = 140                     # djent tempo
BEATS_PER_BAR = 3.5           # 7/8 -> 7 eighth-notes = 3.5 quarter-note beats
EIGHTH = 0.5                  # one eighth note in quarter-note beats

# Raga Bhairav scale degrees (semitone offsets from Sa)
SA, RE_K, GA, MA, PA, DHA_K, NI = 0, 1, 4, 5, 7, 8, 11

# GM programs (0-indexed)
DIST_GUITAR = 29   # "Distortion Guitar" == GM program 30 (1-indexed)
SITAR       = 104  # for the alaap / lead Indian voice
STRINGS     = 48   # sustained tanpura-style drone pad

# MIDI note numbers
C1, C2, C3, C4 = 24, 36, 48, 60
# GM percussion (channel 9)
KICK, SNARE, HHAT = 36, 38, 42

mf = MIDIFile(numTracks=4, deinterleave=False)
T_GTR, T_DRONE, T_LEAD, T_DRUM = 0, 1, 2, 3
CH_GTR, CH_DRONE, CH_LEAD, CH_DRUM = 0, 1, 2, 9

for t in range(4):
    mf.addTempo(t, 0, BPM)
mf.addProgramChange(T_GTR,   CH_GTR,   0, DIST_GUITAR)
mf.addProgramChange(T_DRONE, CH_DRONE, 0, STRINGS)
mf.addProgramChange(T_LEAD,  CH_LEAD,  0, SITAR)

def bhairav(base, degree):
    return base + degree

# ---- SECTION 1: alaap (2 bars, ~3s) ------------------------------------
# tanpura drone Sa-Pa underneath, sitar states the raga slowly.
INTRO_BARS = 2
intro_len = INTRO_BARS * BEATS_PER_BAR

# drone: Sa (C3) + Pa (G3) held across the whole intro AND the drop
mf.addNote(T_DRONE, CH_DRONE, C3,            0, intro_len + 6 * BEATS_PER_BAR, 55)
mf.addNote(T_DRONE, CH_DRONE, C3 + PA,       0, intro_len + 6 * BEATS_PER_BAR, 45)

# sitar alaap phrase: Sa re Ga Ma Pa dha Ni Sa' -- unhurried, in Bhairav
alaap = [SA, RE_K, GA, MA, PA, DHA_K, NI, SA + 12]
t = 0.0
for i, deg in enumerate(alaap):
    dur = 0.9 if i < len(alaap) - 1 else 1.4
    mf.addNote(T_LEAD, CH_LEAD, bhairav(C4, deg), t, dur, 90)
    t += dur * 0.9

# ---- SECTION 2: the djent drop (6 bars, ~9s) ---------------------------
DROP_BARS = 6
# 7/8 palm-muted low riff. Mostly Sa chugs on low C, colored with the two
# komal notes + Ga so the metal riff still "spells" Bhairav.
# 7 eighths per bar; pitch per eighth (offset from low C2):
riff = [SA, SA, RE_K, SA, GA, SA, MA]
for bar in range(DROP_BARS):
    bar_start = intro_len + bar * BEATS_PER_BAR
    for i, deg in enumerate(riff):
        t = bar_start + i * EIGHTH
        mf.addNote(T_GTR, CH_GTR, bhairav(C2, deg), t, 0.42, 118)  # tight = palm mute
        # octave-down reinforcement on the downbeat for weight
        if i == 0:
            mf.addNote(T_GTR, CH_GTR, bhairav(C1, deg), t, 0.42, 110)
    # lead sitar answers every other bar, up an octave, in Bhairav
    if bar % 2 == 1:
        phrase = [PA, DHA_K, PA, MA, GA, RE_K, SA]
        for i, deg in enumerate(phrase):
            mf.addNote(T_LEAD, CH_LEAD, bhairav(C4, deg), bar_start + i * EIGHTH, 0.4, 85)
    # drums: 7/8 groove
    for i in range(7):
        t = bar_start + i * EIGHTH
        mf.addNote(T_DRUM, CH_DRUM, HHAT, t, 0.2, 70)          # hats every eighth
    for k in (0, 3, 5):
        mf.addNote(T_DRUM, CH_DRUM, KICK,  bar_start + k * EIGHTH, 0.2, 120)
    for s in (2, 6):
        mf.addNote(T_DRUM, CH_DRUM, SNARE, bar_start + s * EIGHTH, 0.2, 110)

_OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out", "bhairav_djent.mid")
with open(_OUT, "wb") as f:
    mf.writeFile(f)
print("wrote out/bhairav_djent.mid")
