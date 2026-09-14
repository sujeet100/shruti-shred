"""
The generators (step 4) — read the shared Arrangement chart and emit the layers
of the Composition the proven Phase-0 renderer turns into audio. This module is
the chart -> audio HANDOFF.

The design (DESIGN.md): Lead, Riff and Groove run in PARALLEL, each reading the
same chart, plus a deterministic Drone. They interlock with no sequential handoff
because they all place their notes against one shared timeline and one shared set
of registers — like session players reading a chart, not improvising blind.

This sub-step lays the DETERMINISTIC backbone the LLM generators plug into:
  * the section TIMELINE (pure) — where each section sits on the beat grid, so
    every generator fills the SAME windows;
  * the DRONE generator (deterministic, NO agent) — a tanpura pad, raga-aware so
    it is legal by construction;
  * ASSEMBLY — fold the per-role layers into the Composition contract, plus the
    thin render shell.

The LLM generators (Lead, Riff, Groove) land in later sub-steps; each will be a
function `(Arrangement, section windows) -> Layer` dropped into `assemble`.

Pure core vs. imperative shell (CLAUDE.md): the timeline, the drone and assembly
are pure — data in, data out, fully unit-tested with no API key and no cost. Only
`render_composition` / `main` touch the outside world (fluidsynth, the file
system) — the imperative edge.

Entry point (deterministic, no LLM):  uv run python -m crew.generators
"""

from __future__ import annotations

import math
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from crew.contracts import (
    Arrangement,
    ArrangementDraft,
    Composition,
    CompositionBrief,
    Layer,
    Note,
    Section,
    SectionKind,
    build_arrangement,
)
from raga import SWARAS, direction_violations, drone_swaras, scale_step_up, validate_composition


# --------------------------------------------------------------------------- #
# Voices — the GM instrument/channel per melodic role, as DATA so no generator #
# hardcodes it. Drums are channel 9 with no program (see render.DRUMS); tabla  #
# is wired with the Groove generator (a later sub-step of step 4).             #
# Matches the Phase-0 render proof (out/fusion_legal.wav): dist guitar = GM#30.#
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Voice:
    """The GM voice a melodic role renders through."""
    instrument: str
    program: int   # 0-indexed GM program (29 -> GM #30, Distortion Guitar)
    channel: int
    pan: int = 64  # MIDI CC10 stereo position: 0=hard-left, 64=centre, 127=hard-right


# The `lead` role can be voiced by two timbres, chosen per section (see crew/lead.py):
# the sitar sings the raga, the lead guitar shreds — a DISTINCT, more saturated patch
# than the rhythm guitar's tighter overdrive, so the solo voice reads separately.
#
# STEREO FIELD (a metal mix, not everything stacked mono-centre): the rhythm guitar is
# DOUBLE-TRACKED and panned hard L/R (`rhythm` left + `rhythm_double` right, its own
# channel), the two melodic timbres separate (sitar left-of-centre, lead guitar right),
# and the low end (bass, drone) holds the centre.
VOICES: Final[dict[str, Voice]] = {
    "drone": Voice("strings", 48, 1, pan=64),         # String Ensemble — the tanpura pad (centre)
    "sitar": Voice("sitar", 104, 2, pan=44),          # the raga voice (lead role) — left-of-centre
    "lead_guitar": Voice("dist_guitar_lead", 30, 4, pan=84),  # GM #31 Distortion shred (lead) — right
    # The double-tracked rhythm pair use DIFFERENT gain patches (GM's two high-gain
    # tones) — Overdriven left, Distortion right — so the two sides don't sum to one
    # mono tone; the distinct saturation + the micro-offset in band.py is what gives
    # the classic wide double-tracked wall.
    "rhythm": Voice("overdrive_guitar", 29, 0, pan=20),      # GM #30 Overdriven — hard LEFT
    "rhythm_double": Voice("dist_guitar", 30, 5, pan=108),   # GM #31 Distortion — hard RIGHT
    "bass": Voice("electric_bass", 33, 3, pan=64),    # GM #34 Electric Bass — the low-end anchor (centre)
    # The clean electric guitar — the HARMONY voice (crew/harmony.py): arpeggiated
    # voicings / fillers on GM #28 Electric Guitar (clean), off-centre LEFT so it
    # shimmers opposite the lead guitar without crowding the sitar.
    "clean": Voice("clean_guitar", 27, 10, pan=52),
    # The ORCHESTRA — the symphonic-metal cinematic voice (crew/orchestra.py). ONE LLM
    # agent decides per-section intent; code expands it into these deterministic families,
    # each its own GM program + channel (channels 6/7/11/12 are free — 0-5,8,9,10 taken):
    # a wide string section (pads/tremolo/countermelody), brass (stabs/sustain), choir
    # (aahs), and timpani. Panned into a wide cinematic field, distinct from the hard-L/R
    # rhythm wall. Only the families a chart actually uses become layers (each *_layer
    # returns None otherwise), so channels are consumed on demand.
    "orch_strings": Voice("strings", 48, 6, pan=54),    # GM #49 String Ensemble 1 — left-of-centre
    "orch_brass": Voice("brass", 61, 7, pan=74),        # GM #62 Brass Section — right-of-centre
    "orch_choir": Voice("choir", 52, 11, pan=64),       # GM #53 Choir Aahs — centre, the wash
    "orch_timpani": Voice("timpani", 47, 12, pan=64),   # GM #48 Timpani — centre-low reinforcement
    # The sitar's JOD drone string — a plucked mandra Sa struck ONCE and left to RING under the
    # alap (a sustained open string, not a re-attacked pluck). Its OWN channel so the melodic
    # sitar's meend/bend wheel never bends it; the GM sitar patch gives the plucked attack + ring.
    "jod": Voice("sitar", 104, 13, pan=64),
}


# --------------------------------------------------------------------------- #
# The section timeline — pure. Matra = one quarter-note beat (the Arrangement  #
# contract: beats_per_bar == the tala's matra count), so a section spans       #
# bars * beats_per_bar beats. Every generator reads these SAME windows.        #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class SectionSpan:
    """Where one section sits on the absolute beat grid. Internal, already-valid."""
    index: int
    section: Section
    start: float
    end: float

    @property
    def length(self) -> float:
        return self.end - self.start


def section_spans(arr: Arrangement) -> list[SectionSpan]:
    """Lay the sections end-to-end on the beat grid; return one span each.

    This is how the PARALLEL generators stay aligned with no handoff: they all
    place notes against this one timeline. Pure — no LLM, no I/O.
    """
    spans: list[SectionSpan] = []
    t = 0.0
    for index, section in enumerate(arr.sections):
        length = section.bars * arr.beats_per_bar
        spans.append(SectionSpan(index=index, section=section, start=t, end=t + length))
        t += length
    return spans


def total_beats(arr: Arrangement) -> float:
    """Length of the whole piece in beats — the sum of every section window."""
    return sum(section.bars * arr.beats_per_bar for section in arr.sections)


# --------------------------------------------------------------------------- #
# The Drone generator — DETERMINISTIC, no agent. The drone is pure raga FACT,  #
# not a creative choice, so it is code, not an LLM call.                       #
# --------------------------------------------------------------------------- #

_DRONE_VEL_SA: Final[int] = 55          # Sa is the loudest drone tone
_DRONE_VEL_COMPANION: Final[int] = 45   # its companion sits a touch under it


def drone_layer(arr: Arrangement) -> Layer:
    """The tanpura drone — a sustained pad under the whole piece.

    Sounds Sa plus one companion tone, both drawn from the raga's own allowed
    swaras (`drone_swaras`), so the drone is LEGAL IN THE GRAMMAR by construction
    — the guardrail can never flag it (this matters for e.g. Malkauns, which has
    no Pa: the tanpura tunes Sa-ma, not Sa-Pa). It sits at the chart's `drone`
    register (the lowest voice) and holds the tonal centre the metal riff and the
    raga lead both resolve to.
    """
    octave = arr.registers["drone"]
    length = total_beats(arr)
    tones = drone_swaras(arr.raga)
    velocities = [_DRONE_VEL_SA] + [_DRONE_VEL_COMPANION] * (len(tones) - 1)
    notes = [Note(swara=swara, oct=octave, start=0.0, dur=length, vel=velocity)
             for swara, velocity in zip(tones, velocities)]
    voice = VOICES["drone"]
    return Layer(role="drone", instrument=voice.instrument, program=voice.program,
                 channel=voice.channel, pan=voice.pan, notes=notes)


# The jod string sits an octave ABOVE the tanpura pad: the pad at the drone octave is a
# sub-bass rumble that barely reads as Sa, so the jod is the AUDIBLE plucked home the ear
# hears in the alap (Sujit, 2026-07-19: the alap's Sa is a plucked open string that RINGS
# and FADES NATURALLY, re-plucked to hold home — not the melodic sitar re-attacking low Sa).
_JOD_OCT_ABOVE_DRONE: Final[int] = 1
_JOD_VEL: Final[int] = 78               # the pluck's attack — a present drone-anchor, under the melodic sitar

# A jod stroke is PLAYED IN TIME, like any other note. Held for a whole avartan it stopped
# being a stroke and became a pad — measured on all three 2026-07-20 renders, the intro
# carried four 16-beat jod notes, one per cycle, under a 448-beat tanpura and 16-beat string
# pads, with four drum hits the only attacks in 64 beats. That is why the alap read as
# "unnaturally out of rhythm" (Sujit, 2026-09-14): nothing in it was rhythmic. A sitarist
# strikes the drone string where the melody LEAVES SPACE — to fill an empty matra — so the
# strokes are placed against the melody, on the beat grid, and allowed to ring only briefly.
_JOD_RING: Final[float] = 2.0           # beats a stroke rings before the next event (it fades)
_JOD_MIN_GAP: Final[float] = 1.0        # a hole shorter than this needs no filling
_JOD_GRID: Final[float] = 0.5           # strokes land on the beat grid, like any played note
_JOD_MAX_PER_CYCLE: Final[int] = 4      # ...and never so many that the drone becomes the part


def _sounding_spans(notes: list[Note]) -> list[tuple[float, float]]:
    """Merged (start, end) spans where a voice is sounding — the melody's occupied time."""
    spans: list[tuple[float, float]] = []
    for note in sorted(notes, key=lambda n: n.start):
        start, end = note.start, note.start + note.dur
        if spans and start <= spans[-1][1]:
            spans[-1] = (spans[-1][0], max(spans[-1][1], end))
        else:
            spans.append((start, end))
    return spans


def _gaps_in(spans: list[tuple[float, float]], start: float, end: float) -> list[tuple[float, float]]:
    """The holes in [start, end) the melody leaves — where a drone stroke belongs."""
    gaps: list[tuple[float, float]] = []
    edge = start
    for span_start, span_end in spans:
        if span_end <= start or span_start >= end:
            continue
        if span_start > edge:
            gaps.append((edge, min(span_start, end)))
        edge = max(edge, span_end)
    if edge < end:
        gaps.append((edge, end))
    return [(a, b) for a, b in gaps if b - a >= _JOD_MIN_GAP]


def _on_grid(beat: float) -> float:
    """The next beat-grid position at or after `beat` — a stroke is played in time."""
    return round(math.ceil(beat / _JOD_GRID - 1e-9) * _JOD_GRID, 4)


def _jod_strokes(gaps: list[tuple[float, float]], octave: int) -> list[Note]:
    """One short plucked Sa at the head of each hole, ringing into the space and fading."""
    notes: list[Note] = []
    for gap_start, gap_end in gaps[:_JOD_MAX_PER_CYCLE]:
        start = _on_grid(gap_start)
        if start >= gap_end:
            continue
        notes.append(Note(swara="S", oct=octave, start=start,
                          dur=round(min(_JOD_RING, gap_end - start), 4),
                          vel=_JOD_VEL, fade=True))
    return notes


def intro_jod_layer(arr: Arrangement, lead_layers: list[Layer] = ()) -> Layer | None:
    """The sitar's JOD drone string under the alap — a plucked mandra Sa struck WHERE THE
    MELODY LEAVES SPACE, on the beat grid, ringing briefly and fading (a real jod: played in
    time like any note, filling an empty matra — never a bowed pad spanning the avartan, and
    never the melodic sitar re-attacking low Sa). It rings over the sustained tanpura beneath,
    and IS the alap's audible 'home', so the melodic sitar need not mark Sa itself.

    Deterministic and raga-trivially legal (it sounds Sa). Without `lead_layers` there is no
    melody to answer, so it falls back to one stroke on each avartan's sam — still a stroke,
    never a pad. None when the chart declares no intro section. Pure.
    """
    octave = arr.registers.get("drone", 0) + _JOD_OCT_ABOVE_DRONE
    cycle = arr.beats_per_bar
    lead = _sounding_spans([n for ly in lead_layers if ly.role == "lead"
                            for n in (ly.notes or [])])
    notes: list[Note] = []
    for span in section_spans(arr):
        if span.section.form_role != "intro":
            continue
        for bar in range(span.section.bars):
            start = span.start + bar * cycle
            gaps = _gaps_in(lead, start, start + cycle) if lead else [(start, start + cycle)]
            notes.extend(_jod_strokes(gaps, octave))
    if not notes:
        return None
    voice = VOICES["jod"]
    return Layer(role="jod", instrument=voice.instrument, program=voice.program,
                 channel=voice.channel, pan=voice.pan, notes=notes)


# --------------------------------------------------------------------------- #
# The Bass — a DETERMINISTIC shadow of the riff, no agent (see DESIGN.md).      #
# --------------------------------------------------------------------------- #

_BASS_VEL_SCALE: Final[float] = 0.9    # the bass sits just under the guitar it follows
_BASS_FLOOR: Final[int] = -3           # deepest octave the bass drops to (~D1) — never subsonic
# Bass momentum (GPT: "climbing into the next chord before the riff changes creates momentum").
# A SUSTAINED root leans up/down one raga step in its last half-beat, INTO the next root.
_APPROACH_BEATS: Final[float] = 0.5    # the walk-up takes the last half-beat before a root change
_APPROACH_MIN_DUR: Final[float] = 1.5  # only a held root (>= this) earns one — occasional, not every change
_APPROACH_VEL_SCALE: Final[float] = 0.85  # a lead-in, a touch under the root it walks from


def _bass_approach(cur: tuple[str, int], nxt: tuple[str, int],
                   raga: str) -> tuple[str, int] | None:
    """A raga-legal WALK-UP note into the next bass root: one scale step toward the change
    (from below when the target is higher, from above when lower), so a held root gains
    forward momentum INTO a new chord. Returns (swara, oct), or None when there is no legal,
    distinct, non-subsonic step to walk (then the bass just holds its root). Pure."""
    cur_pitch = SWARAS[cur[0]] + 12 * cur[1]
    nxt_pitch = SWARAS[nxt[0]] + 12 * nxt[1]
    if cur_pitch == nxt_pitch:
        return None
    step = -1 if nxt_pitch > cur_pitch else 1              # approach the target from below / above
    sw, od = scale_step_up(nxt[0], raga, step)
    ap = (sw, nxt[1] + od)
    ap_pitch = SWARAS[sw] + 12 * ap[1]
    if ap[1] < _BASS_FLOOR or ap_pitch in (cur_pitch, nxt_pitch):
        return None                                        # subsonic, or no real step between roots
    if direction_violations([cur, ap, nxt], raga):         # respect directional varjya (aroha/avaroha)
        return None
    return ap


def bass_layer(arr: Arrangement, rhythm: Layer | None) -> Layer | None:
    """The bass — the metal low-end anchor, DERIVED from the riff. No LLM.

    A real bassist follows the riff but need NOT play every note: they lock to its
    ROOTS on the pulse. So this plays the riff notes whose onset lands on a whole
    beat, each SUSTAINED to the next — which DOUBLES a slow, on-beat riff but thins a
    busy tremolo riff down to a driving root line. The notes are the riff's own, so
    they are already raga-legal. Crucially the bass sounds an OCTAVE BELOW the rhythm
    guitar (floored so it never goes subsonic): in metal the bass underpins the guitar
    rather than doubling its exact pitch, which is what stops the guitar from reading
    as "just bass". Returns None when there is no rhythm layer (no riff -> no bass,
    e.g. a bare alaap). `arr` is unused today but kept so a future subgenre-aware bass
    (busier for prog, root-only for death) can read the chart without a call-site change.
    """
    if rhythm is None or not rhythm.notes:
        return None
    on_beat = [n for n in rhythm.notes if float(n.start).is_integer()]
    if not on_beat:                                   # fully syncopated riff -> anchor its first note
        on_beat = [rhythm.notes[0]]
    riff_end = max(n.start + n.dur for n in rhythm.notes)
    voice = VOICES["bass"]
    notes: list[Note] = []
    for i, n in enumerate(on_beat):
        end = on_beat[i + 1].start if i + 1 < len(on_beat) else riff_end
        b_oct = max(n.oct - 1, _BASS_FLOOR)
        vel = max(1, round(n.vel * _BASS_VEL_SCALE))
        dur = end - n.start
        nxt = on_beat[i + 1] if i + 1 < len(on_beat) else None
        approach = (_bass_approach((n.swara, b_oct), (nxt.swara, max(nxt.oct - 1, _BASS_FLOOR)),
                                   arr.raga)
                    if nxt is not None and dur >= _APPROACH_MIN_DUR else None)
        if approach is not None:                          # hold the root, then walk into the change
            notes.append(Note(swara=n.swara, oct=b_oct, start=n.start,
                              dur=round(dur - _APPROACH_BEATS, 4), vel=vel))
            notes.append(Note(swara=approach[0], oct=approach[1],
                              start=round(end - _APPROACH_BEATS, 4), dur=_APPROACH_BEATS,
                              vel=max(1, round(vel * _APPROACH_VEL_SCALE))))
        else:
            notes.append(Note(swara=n.swara, oct=b_oct, start=n.start,
                              dur=round(dur, 4), vel=vel))
    return Layer(role="bass", instrument=voice.instrument, program=voice.program,
                 channel=voice.channel, pan=voice.pan, notes=notes)


# --------------------------------------------------------------------------- #
# The riff-under-lead consonance guard — the riff YIELDS to the raga line.      #
# Deterministic: code never re-pitches a note (it never composes); it thins the #
# ACCOMPANIMENT so a clash reads as a percussive chug, not a sustained grind.   #
# --------------------------------------------------------------------------- #

# A lead note this long reads as a HELD tone the ear tunes to — a riff grinding a harsh
# interval underneath it is heard as wrong; under a fast passing note it is not.
_CLASH_SUSTAIN_MIN: Final[float] = 1.0
# Interval classes (mod 12) that grind under distortion against a held melody note:
# the semitone, the tritone, and the major seventh. Seconds/sevenths an octave out
# (add9-style colour) are deliberately NOT in this set.
HARSH_INTERVAL_CLASSES: Final[frozenset[int]] = frozenset({1, 6, 11})
_CLASH_CHUG_BEATS: Final[float] = 0.5    # a clashing riff note is clipped to a chug this long
_CLASH_VEL_SCALE: Final[float] = 0.9     # ...and softened a touch, under the melody


def sounding_pitch(note) -> int:
    """A note's pitch relative to Sa, as it is actually HEARD (sa cancels out of any
    interval). A meend sounds at its TARGET — the renderer anchors the note on the target
    sample and bends the wheel into it — so a glide's harmonic identity is where it LANDS,
    not the swara it was written as. Comparing the written swara judged the clash against a
    pitch nobody hears, which is what this guard used to do."""
    if note.meend_swara is not None:
        return SWARAS[note.meend_swara] + 12 * (note.oct if note.meend_oct is None
                                                else note.meend_oct)
    return SWARAS[note.swara] + 12 * note.oct


def harmonize_riff_to_lead(rhythm: Layer | None, lead_layers: list[Layer]) -> Layer | None:
    """Keep the riff CONSONANT under the melody. Pure — no LLM.

    The generators write lead and riff independently (both raga-legal, so no note is
    *illegal*), but a riff root a semitone/tritone under a HELD lead note grinds. The riff
    yields — the raga line is sacred: any rhythm note overlapping a sustained lead note at
    a harsh interval class loses its chord stack and is clipped to a short, slightly softer
    palm-mute chug, so the clash becomes a percussive touch instead of a sustained grind.
    Code owns the checkable (interval math); it never re-pitches a note. Runs BEFORE the
    bass/double-track derive, so the whole rhythm section inherits the softened figure.
    """
    if rhythm is None or not rhythm.notes:
        return rhythm
    held = [(n.start, n.start + n.dur, sounding_pitch(n))
            for layer in lead_layers for n in (layer.notes or [])
            if n.dur >= _CLASH_SUSTAIN_MIN]
    if not held:
        return rhythm
    notes = [damp_note(n) if _clashes(n, held) else n for n in rhythm.notes]
    return rhythm.model_copy(update={"notes": notes})


def _clashes(note, held: list[tuple[float, float, int]]) -> bool:
    """Does this riff note overlap a held lead note at a harsh interval class?"""
    end = note.start + note.dur
    pitch = sounding_pitch(note)
    return any(note.start < h_end and h_start < end and (pitch - h_pitch) % 12 in HARSH_INTERVAL_CLASSES
               for h_start, h_end, h_pitch in held)


def damp_note(note):
    """The clash treatment, and the one definition of it: strip the chord stack, clip to a
    chug, soften a touch, and make it PERCUSSIVE.

    The technique is forced to palm_mute rather than preserved. A damped note whose slide
    survived was still a sustained pitch fighting the melody — the gesture kept the clash
    alive and made no sense at half a beat anyway. Damping means "this becomes a touch", and
    a touch is a chug. Shared with `crew/repairs.py`, which offers this as a repair.
    """
    return note.model_copy(update={
        "chord": None,
        "dur": round(min(note.dur, _CLASH_CHUG_BEATS), 4),
        "vel": max(1, round(note.vel * _CLASH_VEL_SCALE)),
        "technique": "palm_mute",
    })


# --------------------------------------------------------------------------- #
# The double-tracked rhythm guitar — the hard-RIGHT half of the L/R wall. No LLM.#
# --------------------------------------------------------------------------- #

_DOUBLE_DT: Final[float] = 0.02          # ~10 ms at 120 bpm — a Haas offset that widens the pair
_DOUBLE_VEL_SCALE: Final[float] = 0.93   # a touch quieter, so the sum is decorrelated, not mono
_DOUBLE_DETUNE_CENTS: Final[int] = 8     # a hair sharp on the right take — two players, not a copy

# HUMANISATION — the difference between a double-track and a delay. A CONSTANT offset applied
# to every note is a copy of one performance, and the ear hears it as a slapback or a chorus,
# not as a second guitarist (external review, 2026-09-14: the right take was the same MIDI
# shifted by exactly 19 ticks throughout). A real second take lands a few milliseconds either
# side of the first, picks a given note slightly harder or softer, and holds it a touch
# longer or shorter. These are per-note and deterministic (same idiom as the drum machine's
# velocity jitter: keyed on the note, never an RNG, so re-renders stay reproducible).
_DOUBLE_DT_WOBBLE: Final[float] = 0.012  # beats: ±~6 ms at 120 bpm around the Haas offset
_DOUBLE_VEL_WOBBLE: Final[int] = 5       # a harder or softer pick on any given note
_DOUBLE_DUR_WOBBLE: Final[float] = 0.10  # ±10% on the note's length — a different fretting hand


def _wobble(index: int, start: float, salt: int) -> float:
    """A deterministic wobble in [-1, 1], keyed on the note and the quantity being varied.

    Keyed rather than random so two renders of one composition are identical, and salted per
    quantity so a note's timing, velocity and length drift INDEPENDENTLY — varying them in
    lockstep would just be a second copy with a different constant.
    """
    key = (int(round(start * 16)) * 2654435761 + index * 40503 + salt * 97) & 0xFFFFFFFF
    return (key % 2001) / 1000.0 - 1.0


def _second_take(index: int, note: Note) -> Note:
    """One note as the SECOND guitarist played it: a hair late, a touch quieter, and each of
    those wobbling per note so the pair reads as two performances rather than one delayed."""
    dt = _DOUBLE_DT + _DOUBLE_DT_WOBBLE * _wobble(index, note.start, 1)
    vel = note.vel * _DOUBLE_VEL_SCALE + _DOUBLE_VEL_WOBBLE * _wobble(index, note.start, 2)
    dur = note.dur * (1 + _DOUBLE_DUR_WOBBLE * _wobble(index, note.start, 3))
    return note.model_copy(update={"start": round(note.start + dt, 4),
                                   "dur": round(max(0.01, dur), 4),
                                   "vel": max(1, min(127, round(vel)))})


def double_track(rhythm: Layer | None) -> Layer | None:
    """The second rhythm-guitar track (hard right) — the riff on a DIFFERENT gain patch
    (`rhythm_double`), nudged a hair late, softer, and a few cents sharp. Two IDENTICAL
    hard-panned tracks would sum back to mono-centre; the different tone + the tiny timing
    offset + the detune are what make the pair read as a WIDE double-tracked wall (the
    detune matters most when a specialized bank routes BOTH sides to the same patch).
    No LLM. None when there is no riff.
    """
    if rhythm is None or not rhythm.notes:
        return None
    voice = VOICES["rhythm_double"]
    notes = [_second_take(i, n) for i, n in enumerate(rhythm.notes)]
    return Layer(role="rhythm", instrument=voice.instrument, program=voice.program,
                 channel=voice.channel, pan=voice.pan, detune_cents=_DOUBLE_DETUNE_CENTS,
                 notes=notes)


# --------------------------------------------------------------------------- #
# Assembly — fold the generated layers into the Composition the renderer reads.#
# --------------------------------------------------------------------------- #

def assemble_composition(arr: Arrangement, layers: list[Layer]) -> Composition:
    """Fold the generated layers into the Composition contract. Pure.

    A boundary mapping only: the Arrangement's raga/sa/bpm/tala carry straight
    across; the layers ARE the generators' output. STRUCTURAL validity (known
    swaras/drums, shape) is the Composition model's job; raga LEGALITY is a
    separate gate (`validate_composition`) the shell runs before it spends
    fluidsynth on the render.
    """
    return Composition(
        raga=arr.raga, sa=arr.sa, bpm=arr.bpm,
        tala={"name": arr.tala, "beats_per_bar": arr.beats_per_bar},
        layers=layers,
    )


# --------------------------------------------------------------------------- #
# The imperative edge — render to WAV, and a deterministic smoke.              #
# --------------------------------------------------------------------------- #

_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
_SOUNDFONT: Final[Path] = _ROOT / "soundfonts" / "GeneralUser-GS.sf2"
_OUT_DIR: Final[Path] = _ROOT / "out"


def render_composition(comp: Composition, *, out_dir: Path, name: str,
                       soundfont: Path) -> Path:
    """Render a Composition to WAV via the Phase-0 renderer. The shell edge.

    Dumps the validated contract to the plain dict `render.build_midi` expects
    (`exclude_none` so optional ornament keys stay ABSENT — the renderer probes
    `"meend" in note`, so a stray null key would arm pitch-bend it never needs),
    writes the .mid, and shells out to fluidsynth. Returns the WAV path.
    """
    from render import render  # lazy: keep midiutil/fluidsynth off the import path
    from soundfont import base_soundfont, present_extras, route_layers

    # The PREFERRED base (SGM Plus HQ — Sujit's ear, 2026-07-15) overrides the caller's
    # font when present; absent, base_soundfont() IS the GM base the callers pass.
    soundfont = base_soundfont()

    out_dir.mkdir(parents=True, exist_ok=True)
    # Save the SYMBOLIC composition beside the audio: the .mid is lossy (bank routing,
    # octave fixes, seated chord pitches), so diagnosing a live run needs the actual
    # contract — free to write now, free to inspect later (no re-run, no LLM).
    (out_dir / f"{name}.json").write_text(comp.model_dump_json(exclude_none=True, indent=2))
    payload = comp.model_dump(exclude_none=True)
    # Route voices to their dedicated banks (guitars -> Dethmetal, sitar/tabla -> Indian
    # Ensemble; each a no-op if that soundfont is absent) and stack every present extra
    # soundfont over the GM base.
    route_layers(payload["layers"], sa=payload["sa"])
    extra_soundfonts = [(str(e.path), e.bank_offset) for e in present_extras()]
    mid_path = out_dir / f"{name}.mid"
    wav_path = out_dir / f"{name}.wav"
    render(payload, str(mid_path), str(wav_path), str(soundfont), extra_soundfonts=extra_soundfonts)
    return wav_path


def _demo_arrangement() -> Arrangement:
    """A hand-authored chart (NO LLM) to prove the deterministic handoff.

    Malkauns on purpose: it has no Pa, so it exercises the drone's raga-aware
    companion rule (tuned Sa-ma, not Sa-Pa). Built through the real
    `build_arrangement` so the chart the renderer sees is the genuine contract.
    """
    draft = ArrangementDraft(
        raga="malkauns", subgenre="doom", tala="teentaal", bpm=72,
        motif=["d", "n", "S", "m"],
        sections=[
            Section(kind=SectionKind.ALAAP, bars=1, layers=["lead", "drone"],
                    foreground="lead", intent="unfold the raga over the bare drone"),
            Section(kind=SectionKind.RIFF, bars=2, layers=["rhythm", "drums", "drone"],
                    foreground="rhythm", intent="the crushing doom riff enters"),
        ],
    )
    return build_arrangement(draft, CompositionBrief(mood="dark"))


def _run() -> None:
    """Prove the chart -> Composition -> validate -> WAV spine with the drone only.

    Deterministic and free (no LLM). Renders if fluidsynth + the soundfont are
    present; otherwise reports the validated composition and skips the audio.
    """
    arr = _demo_arrangement()
    comp = assemble_composition(arr, [drone_layer(arr)])
    payload = comp.model_dump(exclude_none=True)
    violations = validate_composition(payload)
    print(f"chart: {arr.raga} x {arr.subgenre} in {arr.tala} @ {arr.bpm}bpm, "
          f"Sa={arr.sa}, {total_beats(arr):g} beats")
    print(f"drone tones: {' '.join(drone_swaras(arr.raga))} "
          f"(register {arr.registers['drone']:+d})")
    print(f"drone-only composition: {len(violations)} grammar violation(s)")

    if shutil.which("fluidsynth") and _SOUNDFONT.exists():
        wav = render_composition(comp, out_dir=_OUT_DIR, name="drone_only", soundfont=_SOUNDFONT)
        print(f"-> rendered {wav.relative_to(_ROOT)}")
    else:
        print("-> render skipped (fluidsynth or soundfont not found)")


def main(argv: list[str]) -> int:
    _run()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
