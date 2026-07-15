"""Soundfont assets + routing — the single source of truth for what FluidSynth loads.

Kept deliberately light (pathlib + a dataclass) so both the pure core (`src/demo.py`)
and the crew shell can import it without dragging midiutil/fluidsynth onto their import
path. The soundfont binaries are gitignored and fetched by `setup.sh`.

The render stacks soundfonts: a GM base plus zero or more specialized banks layered on
top (FluidSynth keeps them as a stack, and a preset is chosen by (bank, program)). Each
extra bank is addressed by a MIDI Bank Select on its channel, so a voice can pull from a
dedicated soundfont (e.g. the rhythm/lead guitars from a real distorted-guitar bank) while
everything else stays on the GM base. A missing extra file degrades to the base — the
routing only fires for soundfonts actually present on disk.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_SF_DIR: Path = Path(__file__).resolve().parents[1] / "soundfonts"

# The GM base. GeneralUser GS 2.0.3 (License v2.0). Overdrive=29, Distortion=30,
# Finger Bass=33, Strings=48, Sitar=104 — our voices map to it transparently.
BASE_SOUNDFONT: Path = _SF_DIR / "GeneralUser-GS.sf2"

# SGM Plus HQ — Songsterr's own build of the SGM megafont (their FluidSynth player's
# font; fetched from their public static URL by setup.sh; license = SGM freeware family,
# this build UNVERIFIED — demo-only). Sujit A/B'd it against GeneralUser/Dethmetal/SGM
# V2.01 on 2026-07-15 and picked it BY EAR — when present it is the PREFERRED BASE for
# the whole band: GM-compatible programs, its bank 1:28 "Muted Dis.Gt" carries the
# palm-mute chugs, and the Indian Ensemble still stacks on top for sitar/tabla.
SGM_HQ: Path = _SF_DIR / "SGM_Plus_HQ.sf3"
_SGM_HQ_PM_BANK: int = 1                  # internal bank 1 (no offset — it IS the base)
_SGM_HQ_PM_PROGRAM: int = 28              # "Muted Dis.Gt"


def hq_present(override: bool | None = None) -> bool:
    """Is the preferred (SGM Plus HQ) base on disk? `override` is the test seam."""
    return override if override is not None else SGM_HQ.exists()


def base_soundfont(*, hq: bool | None = None) -> Path:
    """The base soundfont the render should load — SGM Plus HQ when present."""
    return SGM_HQ if hq_present(hq) else BASE_SOUNDFONT

# FluidSynth bank-select mode used when extras are stacked: 'mma' makes the 14-bit bank
# addressable as bank = (CC0 << 7) | CC32, so high SF2 banks (e.g. Dethmetal's 126) resolve.
BANK_SELECT_MODE: str = "mma"


@dataclass(frozen=True)
class ExtraSoundfont:
    """A specialized bank layered over the GM base on the FluidSynth stack.

    `bank_offset` is FluidSynth's `-b` positional flag: it shifts this soundfont's internal
    banks into a unique range so they never collide with GM bank 0 (or each other).
    """

    name: str
    path: Path
    bank_offset: int


# Dethmetal — a dedicated distorted electric guitar. Its four presets live at internal
# bank 126 (0=Distorted, 1=Clean, 2=Chords, 3=Bass); GeneralUser GS uses no bank 126, so
# offset 0 is already collision-free. We route the single-note "Distorted" patch (program 0)
# to both rhythm and lead — the renderer stacks power-chord tones itself, so we want a
# single-note patch, not a pre-baked chord one. License is UNVERIFIED (source disclaims it);
# accepted for the demo, not for commercial redistribution.
DETHMETAL: ExtraSoundfont = ExtraSoundfont("dethmetal", _SF_DIR / "Dethmetal.sf2", bank_offset=0)
_DETHMETAL_BANK: int = 126  # internal bank + offset 0
_DETHMETAL_DISTORTED: int = 0

# Indian Ensemble (E-mu, attribution license) — a multi-sampled sitar + a real tabla for the
# classical side (the drone stays on GM strings, which sound better than this tamboura). It
# can't be auto-downloaded (members-only); fetched manually to soundfonts/Indian-Ensemble.sf2
# (see setup.sh / soundfonts/README.md). Its presets sit at internal bank 0 (same as GM), so
# it's given a bank offset to avoid clobbering the GM base.
INDIAN: ExtraSoundfont = ExtraSoundfont("indian", _SF_DIR / "Indian-Ensemble.sf2", bank_offset=50)
_INDIAN_BANK: int = 0 + 50                # internal bank 0 + offset 50
_INDIAN_TABLA_PRESET: int = 0             # preset 0 ("Tamboura/Tabla") — tabla strokes on keys 53-96
_INDIAN_SITAR: int = 2                    # preset 2 — the multi-sampled sitar
# This soundfont is pitched an OCTAVE LOW, so the melodic sitar is transposed UP one octave to
# sound in the band's register. (The drone is NOT routed here — GM strings sound better than the
# tamboura; the tabla is a natural-pitch percussion map, tuned to Sa separately below.)
_INDIAN_SITAR_OCTAVE_FIX: int = 1         # +1 octave on sitar notes to correct the octave-low SF
_TABLA_MELODIC_CHANNEL: int = 8           # move the tabla OFF GM perc (ch9) to a melodic channel
# The dayan (treble tabla) is a TUNED drum. This soundfont's strokes are fixed near C (key 60
# sounds ~C), so to play the tabla "in key" we shift the whole tabla channel to the piece's Sa
# via MIDI RPN coarse-tuning (NOT by picking a different key — adjacent keys are different
# strokes, not pitches). Reference: the dayan sits at ~key 60 (C).
_DAYAN_NATURAL_KEY: int = 60

# Our tabla generator emits two stroke voices (crew/groove.py `_bol_voices`): treble (dayan)
# and bass (banya). Map each to a representative key in preset 0's tabla range — a "both"-hand
# bol plays both together, which is exactly a `dha`. (Congas remain the fallback when absent.)
TABLA_KEYS: dict[str, int] = {"tabla_hi": 60, "tabla_lo": 80}

# SGM V2.01 (Shan's GM megafont, freeware; fetched from archive.org — see setup.sh). This
# is the soundfont FAMILY Songsterr's FluidSynth-WASM player uses ("SGM Plus HQ", split per
# preset): its GS-style bank 1 holds ARTICULATION variants, and 1:28 "Muted Dis.Gt" is a
# real palm-muted DISTORTED guitar multisample — the chug "chunk" is in the recording, not
# a synthesis trick. The renderer routes palm-muted rhythm notes there (`pm_bank` below);
# missing file degrades to the GM muted-guitar layering. Offset 300 keeps SGM's banks
# (0, 1, ..., 128) clear of GeneralUser, Dethmetal (126) and Indian (50).
SGM: ExtraSoundfont = ExtraSoundfont("sgm", _SF_DIR / "SGM-V2.01.sf2", bank_offset=300)
_SGM_PM_BANK: int = 1 + 300               # internal bank 1 (the PM variants) + offset
_SGM_MUTED_DIST: int = 28                 # preset 28 "Muted Dis.Gt" — the palm-muted distortion

_EXTRAS: tuple[ExtraSoundfont, ...] = (DETHMETAL, INDIAN, SGM)

# Voice `instrument` names (from crew.generators.VOICES) that should play through Dethmetal
# when it is present. Sitar (also role "lead") is deliberately excluded — it stays on the base.
_GUITAR_INSTRUMENTS: frozenset[str] = frozenset({"overdrive_guitar", "dist_guitar", "dist_guitar_lead"})


def present_extras() -> list[ExtraSoundfont]:
    """The extra soundfonts actually on disk — so a missing file degrades to the base.

    When SGM Plus HQ is the base, the stacked SGM V2.01 is SKIPPED: the HQ base already
    supplies the guitar tone and the palm-mute bank, and loading a redundant 247MB
    font would only slow every render."""
    extras = [e for e in _EXTRAS if e.path.exists()]
    if hq_present(None):
        extras = [e for e in extras if e is not SGM]
    return extras


def fluidsynth_soundfont_args() -> list[str]:
    """FluidSynth CLI args: the base first, then each present extra with its `-b` offset."""
    args: list[str] = [str(BASE_SOUNDFONT)]
    for extra in present_extras():
        args += ["-b", str(extra.bank_offset), str(extra.path)]
    return args


def bank_select_cc(bank: int) -> tuple[int, int]:
    """(CC0 MSB, CC32 LSB) that select `bank` under the 'mma' bank-select mode."""
    return bank // 128, bank % 128


def tabla_coarse_tune(sa: int) -> int:
    """Semitones to shift the tabla channel so the dayan (~C) sounds at the piece's Sa.

    The nearest signed offset (±6) mapping the dayan's natural pitch class (C) to Sa's, so the
    tabla stays in its own register while ringing in key. Applied via MIDI RPN coarse-tuning.
    """
    return ((sa - _DAYAN_NATURAL_KEY + 6) % 12) - 6


def route_guitars(layers: list[dict], *, dethmetal_present: bool | None = None,
                  sgm_present: bool | None = None) -> None:
    """Route the guitar layers to the best distorted bank present, IN PLACE.

    Preference (Sujit picked SGM's tone by ear, 2026-07-15 — it is what Songsterr plays):
      1. SGM — GM-COMPATIBLE, so each guitar keeps its OWN program (Overdriven left take,
         Distortion right take + lead) and just bank-selects to SGM's offset: the classic
         two-tone double-track survives the swap.
      2. Dethmetal's Distorted (all guitars on one patch, decorrelated by detune).
      3. Nothing — the GM base's overdrive/distortion.
    The `*_present` flags override the on-disk checks (injectable seams for tests).
    """
    sgm = sgm_present if sgm_present is not None else (SGM in present_extras())
    if sgm:
        for layer in layers:
            if layer.get("instrument") in _GUITAR_INSTRUMENTS:
                layer["bank"] = SGM.bank_offset       # internal bank 0 + offset: same GM
                                                      # programs, SGM's samples
        return
    present = dethmetal_present if dethmetal_present is not None else (DETHMETAL in present_extras())
    if not present:
        return
    bank = _DETHMETAL_BANK + DETHMETAL.bank_offset
    for layer in layers:
        if layer.get("instrument") in _GUITAR_INSTRUMENTS:
            layer["bank"] = bank
            layer["program"] = _DETHMETAL_DISTORTED


def route_indian(layers: list[dict], *, sa: int, indian_present: bool | None = None) -> None:
    """Route the classical voices to the Indian Ensemble, IN PLACE, if it is present.

    Sitar -> the multi-sampled sitar, transposed up one octave (this soundfont is pitched an
    octave low, so a melodic voice needs correcting). Tabla -> the real tabla, moved onto a
    melodic channel (bank-selected) with its stroke keys sounding instead of GM congas, and
    the whole channel tuned to the piece's Sa. The DRONE is left on the GM base (strings sound
    better than the tamboura). No-op when the file is absent (GM strings + congas remain).
    """
    present = indian_present if indian_present is not None else (INDIAN in present_extras())
    if not present:
        return
    for layer in layers:
        if layer.get("instrument") == "sitar":
            layer["bank"], layer["program"] = _INDIAN_BANK, _INDIAN_SITAR
            for note in layer.get("notes") or []:
                note["oct"] = note.get("oct", 0) + _INDIAN_SITAR_OCTAVE_FIX
                if note.get("meend_oct") is not None:
                    note["meend_oct"] += _INDIAN_SITAR_OCTAVE_FIX
        elif layer.get("role") == "tabla":
            layer["bank"], layer["program"] = _INDIAN_BANK, _INDIAN_TABLA_PRESET
            layer["channel"] = _TABLA_MELODIC_CHANNEL
            layer["coarse_tune"] = tabla_coarse_tune(sa)   # tune the dayan to Sa (in key)


def route_palm_mutes(layers: list[dict], *, sgm_present: bool | None = None,
                     hq: bool | None = None) -> None:
    """Give the guitar layers a PALM-MUTE bank, IN PLACE.

    Sets `pm_bank`/`pm_program` on each guitar layer; the renderer's chug companion
    channel bank-selects there, so palm-muted notes play a real muted-DISTORTION
    sample (the Songsterr articulation trick) instead of the layered GM clean mute.
    With the SGM Plus HQ BASE it is the base's own bank 1; else the stacked SGM V2.01
    at its offset; no-op when neither is present (the renderer keeps its GM fallback).
    """
    if hq_present(hq):
        bank, program = _SGM_HQ_PM_BANK, _SGM_HQ_PM_PROGRAM
    else:
        present = sgm_present if sgm_present is not None else (SGM in present_extras())
        if not present:
            return
        bank, program = _SGM_PM_BANK, _SGM_MUTED_DIST
    for layer in layers:
        if layer.get("instrument") in _GUITAR_INSTRUMENTS:
            layer["pm_bank"] = bank
            layer["pm_program"] = program


_POWER_KIT: int = 16   # GS drum kit 16 "POWER" — the rock/metal kit (SGM carries it)


def route_drum_kit(layers: list[dict], *, hq: bool | None = None) -> None:
    """Select the POWER kit for the metal drums, IN PLACE, when the HQ base carries
    it. The tabla stays on the default kit (its GM-conga fallback voices live there)."""
    if not hq_present(hq):
        return
    for layer in layers:
        if layer.get("role") == "drums" and layer.get("program") is None:
            layer["program"] = _POWER_KIT


def route_layers(layers: list[dict], *, sa: int, hq: bool | None = None) -> None:
    """Apply all soundfont routing. With the SGM Plus HQ base (Sujit's pick), the
    guitars stay on their own GM programs (the base IS the tone) and the kit goes
    POWER; otherwise guitars route to the stacked SGM V2.01 / Dethmetal as before."""
    if not hq_present(hq):
        route_guitars(layers)
    route_palm_mutes(layers, hq=hq)
    route_drum_kit(layers, hq=hq)
    route_indian(layers, sa=sa)
