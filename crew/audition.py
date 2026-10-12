"""
A seed AUDITION — the musical identity alone, so Sujit can rank seeds blind by ear.

The seed debate's verdict is his ear, not an LLM's (`crew/seed_debate.py`), and a full piece would
bury the seed under twenty develop calls. So a seed is auditioned as itself: one avartan of the
main riff alone, then the sitar's hook over it for three avartans, with the deterministic band
(drone, bass, drums) code derives. No model is called — the riff and the hook are replayed from
the seed through the same generators, voicing and renderer the real piece uses, so what is heard
is what the piece would be built on.

`audition_composition` is pure; `render_audition` is the shell edge (fluidsynth).
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from crew.contracts import (
    Arrangement,
    Composition,
    CompositionBrief,
    Section,
    SectionKind,
    SongSeed,
    build_arrangement,
)
from crew.realized import KeptLead

_SLOT: Final = "main"
_RIFF_BARS: Final = 1
_HOOK_BARS: Final = 3
_BAND: Final = ["rhythm", "drums", "drone"]


def _never(*_args, **_kwargs):
    raise AssertionError("an audition replays its seed — it never calls a model")


def audition_arrangement(seed: SongSeed, brief: CompositionBrief) -> Arrangement:
    """The seed's chart cut down to the audition: the main riff alone, then the hook over it as
    a mukhada (sitar alone, looped) — the seed's own raga, tala, tempo and subgenre. A gat seed that
    holds only its head's IDEA has no notes to replay (the gat call composes them), so it cannot be
    auditioned on its own. Pure."""
    if seed.hook is None:
        raise ValueError("this seed holds only the gat head's idea — compose the head before auditioning")
    sections = [
        Section(kind=SectionKind.RIFF, bars=_RIFF_BARS, layers=list(_BAND), foreground="rhythm",
                riff_slot=_SLOT, intent="the main riff alone"),
        Section(kind=SectionKind.MELODY, bars=_HOOK_BARS, layers=["lead", *_BAND],
                foreground="lead", riff_slot=_SLOT, form_role="mukhada",
                intent="the hook over the main riff"),
    ]
    draft = seed.chart.model_copy(update={"sections": sections, "form": "gat"})
    arr = build_arrangement(draft, brief)
    return arr.model_copy(update={"seed_riff": seed.main_riff, "seed_hook": seed.hook})


def audition_composition(seed: SongSeed, brief: CompositionBrief) -> Composition:
    """The audition as a Composition — the seed replayed through the real generators. Pure."""
    from crew.band import band_layers
    from crew.generators import assemble_composition
    from crew.lead import generate_lead
    from crew.riff import generate_riff, voiced_and_verified
    arr = audition_arrangement(seed, brief)
    riff = voiced_and_verified(lambda feedback: seed.main_riff, arr.sections[0], arr)
    rhythm, _ = generate_riff(arr, gen_fn=_never, keep={_SLOT: riff})
    lead_layers, _ = generate_lead(arr, gen_fn=_never, keep=KeptLead(phrases={1: seed.hook}))
    return assemble_composition(arr, band_layers(arr, lead_layers, rhythm))


def render_audition(seed: SongSeed, brief: CompositionBrief, *, out_dir: Path, name: str,
                    soundfont: Path) -> Path:
    """Render one seed's audition to `out_dir/name.wav` (the shell edge)."""
    from crew.generators import render_composition
    comp = audition_composition(seed, brief)
    return render_composition(comp, out_dir=out_dir, name=name, soundfont=soundfont,
                              arrangement=audition_arrangement(seed, brief))
