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
from raga import drone_swaras, validate_composition


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


# --------------------------------------------------------------------------- #
# The Bass — a DETERMINISTIC shadow of the riff, no agent (see DESIGN.md).      #
# --------------------------------------------------------------------------- #

_BASS_VEL_SCALE: Final[float] = 0.9    # the bass sits just under the guitar it follows
_BASS_FLOOR: Final[int] = -3           # deepest octave the bass drops to (~D1) — never subsonic


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
        notes.append(Note(swara=n.swara, oct=max(n.oct - 1, _BASS_FLOOR),
                          start=n.start, dur=round(end - n.start, 4),
                          vel=max(1, round(n.vel * _BASS_VEL_SCALE))))
    return Layer(role="bass", instrument=voice.instrument, program=voice.program,
                 channel=voice.channel, pan=voice.pan, notes=notes)


# --------------------------------------------------------------------------- #
# The double-tracked rhythm guitar — the hard-RIGHT half of the L/R wall. No LLM.#
# --------------------------------------------------------------------------- #

_DOUBLE_DT: Final[float] = 0.02          # ~10 ms at 120 bpm — a Haas offset that widens the pair
_DOUBLE_VEL_SCALE: Final[float] = 0.93   # a touch quieter, so the sum is decorrelated, not mono


def double_track(rhythm: Layer | None) -> Layer | None:
    """The second rhythm-guitar track (hard right) — the riff on a DIFFERENT gain patch
    (`rhythm_double`), nudged a hair late and softer. Two IDENTICAL hard-panned tracks
    would sum back to mono-centre; the different tone + the tiny timing offset are what
    make the pair read as a WIDE double-tracked wall. No LLM. None when there is no riff.
    """
    if rhythm is None or not rhythm.notes:
        return None
    voice = VOICES["rhythm_double"]
    notes = [n.model_copy(update={"start": round(n.start + _DOUBLE_DT, 4),
                                  "vel": max(1, round(n.vel * _DOUBLE_VEL_SCALE))})
             for n in rhythm.notes]
    return Layer(role="rhythm", instrument=voice.instrument, program=voice.program,
                 channel=voice.channel, pan=voice.pan, notes=notes)


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
_SOUNDFONT: Final[Path] = _ROOT / "soundfonts" / "MuseScore_General.sf3"
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
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = comp.model_dump(exclude_none=True)
    mid_path = out_dir / f"{name}.mid"
    wav_path = out_dir / f"{name}.wav"
    render(payload, str(mid_path), str(wav_path), str(soundfont))
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
