"""
Full-band assembly — the chart -> every voice -> one Composition -> WAV.

This is where the generators come together. Two voices are the creative LLM work
(the Lead melody and the Riff); everything else is derivable and deterministic (the
Drone from the chart; the Bass, the Drums, and — following the tala — the Tabla). The
assembly just collects them, in a stable layer order, into the Composition the proven
renderer consumes.

Layering (pure core / imperative shell): `band_layers` is pure — given the LLM voices
(the lead layers and the riff) it derives the rest and returns the ordered list, so it
is unit-tested with no key. `compose_band` is the shell that actually calls the two
LLM generators; `compose_from_query` is the whole pipeline (interpret -> composers ->
band). `main` renders a fixed demo chart so the confirmation is a bounded LLM spend.

Entry point (a full-band render; lead + riff are the LLM calls, the rest is code):
  uv run python -m crew.band
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Final

from crew.contracts import Arrangement, Composition, DebateEvent, EventStream, Layer
from crew.generators import (
    assemble_composition,
    bass_layer,
    double_track,
    drone_layer,
    harmonize_riff_to_lead,
    intro_jod_layer,
    render_composition,
)
from crew.dynamics import apply_dynamics, apply_taan_exposure
from crew.groove import groove_layer, tabla_layer
from crew.harmonic_guide import harmonic_guide
from crew.harmony import clean_layer
from raga import validate_composition

_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
_SOUNDFONT: Final[Path] = _ROOT / "soundfonts" / "GeneralUser-GS.sf2"
_OUT_DIR: Final[Path] = _ROOT / "out"


def band_layers(arr: Arrangement, lead_layers: list[Layer], rhythm: Layer | None,
                orchestra_layers: list[Layer] = ()) -> list[Layer]:
    """Collect every voice into the stable layer order, then BALANCE it. Pure — no LLM.

    Takes the CREATIVE voices already generated (the lead layer(s), the riff, and — for a
    symphonic chart — the orchestra's expanded Layers) and derives the rest around them: the
    drone from the chart, the bass and drums from the riff, and the tabla from the tala.
    Drone leads the list; the orchestra sits with the melodic voices; percussion trails it.
    Then two deterministic post-assembly passes, each needing every voice at once:
    `apply_taan_exposure` drops the metal band out of the long taan's final avartan (the
    band-drop window — sitar, drone, tabla AND the orchestra carry the peak alone), and
    `apply_dynamics` shapes the energy arc + layer-by-function balance across the sections
    (both no-ops on a chart with no declared gat form). `orchestra_layers` defaults empty,
    so every existing caller and fixture is unchanged.
    """
    layers: list[Layer] = [drone_layer(arr)]
    layers.extend(lead_layers)
    layers.extend(orchestra_layers)   # the cinematic voices (symphonic; sparse colour elsewhere)
    if rhythm is not None:
        # The riff yields to the raga line (clashing notes thin to a chug), so the double
        # track and the derived low end all inherit the consonant figure. This is the LAST
        # line of defence: the Arranger (crew/arranger.py) has normally already repaired
        # these clashes upstream, choosing among legal options; what reaches here is
        # whatever it judged expressive or could not fix.
        rhythm = harmonize_riff_to_lead(rhythm, lead_layers)
        layers.append(rhythm)                        # the hard-left rhythm track
        double = double_track(rhythm)                # the hard-right double (different gain patch)
        if double is not None:
            layers.append(double)
    # Bass, groove and tabla derive from the ORIGINAL riff (never the double), so the
    # low end and kit stay locked to one rhythm-guitar line, not a smeared pair. The
    # clean guitar realises the chart's per-section HARMONY plan (crew/harmony.py) —
    # deterministic like the rest: the composers decided the modes, code plays them.
    # ONE harmonic guide, read by every accompanying voice: what the melody settles on, and
    # what must not sustain under it. Derived from the realized lead, so it exists only now —
    # which is exactly why the composers' colour choices could not have known it.
    guide = harmonic_guide(lead_layers, arr)
    for derived in (clean_layer(arr, guide=guide), intro_jod_layer(arr, lead_layers),
                    bass_layer(arr, rhythm),
                    groove_layer(arr, rhythm), tabla_layer(arr)):
        if derived is not None:
            layers.append(derived)
    # The taan exposure runs BEFORE the balance pass: the band-drop window empties first, then
    # the energy/foreground gains shape whatever still sounds.
    return apply_dynamics(apply_taan_exposure(layers, arr), arr)


def compose_band(arr: Arrangement) -> tuple[Composition, list[DebateEvent]]:
    """Generate every voice for a chart and assemble the full Composition.

    The Lead and the Riff are the LLM calls (one per active section each); the bass,
    drums, tabla and drone are deterministic. Imports the LLM generators lazily so
    this module stays importable without paying the crewai import cost.
    """
    from crew.lead import compose_lead, mukhada_cell_from_events
    from crew.orchestra import compose_orchestra, uses_orchestra
    from crew.riff import compose_riff

    events: list[DebateEvent] = []
    lead_layers, lead_events = compose_lead(arr)
    # Cross-voice seeding: the riff runs AFTER the lead and reduces the cached gat head
    # (fished from the lead's events), so the band hears the mukhada IN the riff.
    rhythm, riff_events = compose_riff(arr, mukhada=mukhada_cell_from_events(lead_events))
    events.extend(lead_events)
    events.extend(riff_events)
    # THE ARRANGER — the third question, asked only once both lines are real: do they
    # coexist? The riff was composed before this lead existed, so it could not know what
    # the sitar actually sounds on any given beat. It repairs surgically (one note at a
    # time, never a rhythm), the right-of-way rule decides who gives way, and a piece with
    # no clashes makes no call at all. It runs BEFORE the orchestra, so the cinematic
    # voices answer the repaired lines rather than the fighting ones.
    from crew.arranger import arrange_against_lead

    rhythm, lead_layers, arranger_events = arrange_against_lead(rhythm, lead_layers, arr)
    events.extend(arranger_events)
    # The Orchestra is CAPABILITY-GATED: it joins ONLY when the chart calls for it (symphonic
    # charts always; other subgenres where the composers added it as colour). It runs after
    # the creative voices so it can ANSWER the realized lead + riff rather than double them.
    orchestra_layers: list[Layer] = []
    if uses_orchestra(arr):
        orchestra_layers, orch_events = compose_orchestra(arr, lead_layers=lead_layers, rhythm=rhythm)
        events.extend(orch_events)
    return (assemble_composition(arr, band_layers(arr, lead_layers, rhythm, orchestra_layers)),
            events)


def compose_from_query(query: str) -> tuple[Composition, list[DebateEvent]]:
    """The whole pipeline: free-text query -> brief -> composer chart -> full band.

    interpret (LLM) -> Pandit/Riffsmith dialogue (LLM) -> the generators (LLM lead +
    riff, deterministic rest). Returns the Composition plus the full event stream
    (intake + dialogue + generation) the UI would render.
    """
    from crew.composers import compose
    from crew.interpreter import interpret

    brief, intake_events = interpret(query)
    arr, dialogue_events = compose(brief)
    comp, gen_events = compose_band(arr)
    return comp, [*intake_events, *dialogue_events, *gen_events]


def _band_demo_arrangement() -> Arrangement:
    """A fixed, representative fusion arc so the confirmation is a bounded 4 LLM calls:
    an alaap (sitar over tabla), the band dropping into the main riff (kit + tabla +
    bass), and a harmonized taan. Darbari (seven notes, clean third) x progressive.
    Built through the real composer contract — no LLM here."""
    from crew.contracts import ArrangementDraft, CompositionBrief, Section, SectionKind, build_arrangement
    draft = ArrangementDraft(
        raga="darbari", subgenre="progressive", tala="teentaal", bpm=120,
        motif=["S", "R", "g", "R", "g", "m", "P"],
        sections=[
            Section(kind=SectionKind.ALAAP, bars=1, layers=["lead", "tabla", "drone"],
                    foreground="lead", intent="unfold Darbari over a soft tabla theka",
                    transition="the band crashes in"),
            Section(kind=SectionKind.RIFF, bars=2, layers=["rhythm", "drums", "tabla", "drone"],
                    foreground="rhythm", intent="the main riff, tabla under the groove",
                    transition="a fill lifts into the taan"),
            Section(kind=SectionKind.TAAN, bars=1, layers=["lead", "rhythm", "drums", "drone"],
                    foreground="lead", intent="a harmonized taan climbing to the climax"),
        ],
    )
    return build_arrangement(draft, CompositionBrief(mood="dark"))


def _run() -> None:
    arr = _band_demo_arrangement()
    stream = EventStream()
    comp, events = compose_band(arr)
    for event in events:
        stream.emit(event)

    payload = comp.model_dump(exclude_none=True)
    violations = validate_composition(payload)
    roles = [layer.role for layer in comp.layers]
    print(f"full band: {len(comp.layers)} layers {roles}; {len(violations)} grammar violation(s)")

    if shutil.which("fluidsynth") and _SOUNDFONT.exists():
        wav = render_composition(comp, out_dir=_OUT_DIR, name="full_band", soundfont=_SOUNDFONT)
        print(f"-> rendered {wav.relative_to(_ROOT)}")
    else:
        print("-> render skipped (fluidsynth or soundfont not found)")


def main(argv: list[str]) -> int:
    from crew.config import load_env
    load_env()
    from contextlib import nullcontext

    from crew.tracing import traced, tracing_enabled
    ctx = traced("band-demo") if tracing_enabled() else nullcontext()
    with ctx:
        _run()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
