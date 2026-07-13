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

_EXTRAS: tuple[ExtraSoundfont, ...] = (DETHMETAL, INDIAN)

# Voice `instrument` names (from crew.generators.VOICES) that should play through Dethmetal
# when it is present. Sitar (also role "lead") is deliberately excluded — it stays on the base.
_GUITAR_INSTRUMENTS: frozenset[str] = frozenset({"overdrive_guitar", "dist_guitar", "dist_guitar_lead"})


def present_extras() -> list[ExtraSoundfont]:
    """The extra soundfonts actually on disk — so a missing file degrades to the base."""
    return [e for e in _EXTRAS if e.path.exists()]


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


def route_guitars(layers: list[dict], *, dethmetal_present: bool | None = None) -> None:
    """Route the guitar layers to Dethmetal's distorted patch, IN PLACE, if it is present.

    Sets each guitar layer's `bank`/`program` to Dethmetal's (bank 126, Distorted). No-op
    when the file is absent, so the guitars fall back to the GM base's overdrive/distortion.
    `dethmetal_present` overrides the on-disk check (an injectable seam for tests).
    """
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


def route_layers(layers: list[dict], *, sa: int) -> None:
    """Apply all soundfont routing (guitars -> Dethmetal, sitar/tabla -> Indian Ensemble)."""
    route_guitars(layers)
    route_indian(layers, sa=sa)
