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
from collections.abc import Callable
from typing import Final

from crew.contracts import (
    Arrangement,
    Composition,
    DebateEvent,
    EventStream,
    Layer,
    LeadPhrase,
    RiffPattern,
)
from crew.generators import (
    assemble_composition,
    bass_layer,
    double_track,
    drone_layer,
    render_composition,
)
from crew.articulation import articulate
from crew.chikari import chikari_layer, without_chikari
from crew.chord_floor import lift_antara, on_floor
from crew.dynamics import apply_dynamics, apply_taan_exposure
from crew.groove import groove_layer, tabla_layer
from crew.harmonic_guide import harmonic_guide
from crew.rhythm_section import realise, with_rhythm_section
from crew.ending import apply_ending
from crew.harmony import clean_layer
from raga import validate_composition

_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
_SOUNDFONT: Final[Path] = _ROOT / "soundfonts" / "GeneralUser-GS.sf2"
_OUT_DIR: Final[Path] = _ROOT / "out"


def _tabla_if_enabled(arr: Arrangement) -> Layer | None:
    """The tabla, when it is switched on (`config.tabla_enabled`, default OFF since
    2026-09-14). Kept as a gate rather than a deletion — the theka generation and its
    soundfont routing are wanted back once the part responds to the section it is under."""
    from crew.config import tabla_enabled
    return tabla_layer(arr) if tabla_enabled() else None


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

    The sitar's CHIKARI strokes (crew/chikari.py) leave the melody here: the written ones are
    lifted off the lead line and, with the strokes the planner places around the sitar's
    phrases, sound on their own unbent strings beside it.
    """
    melody_layers = without_chikari(lead_layers)
    chikari = chikari_layer(arr, lead_layers)
    layers: list[Layer] = [drone_layer(arr)]
    layers.extend(melody_layers)
    layers.extend([chikari] if chikari is not None else [])
    layers.extend(orchestra_layers)   # the cinematic voices (symphonic; sparse colour elsewhere)
    # A COMPOSED rhythm section (written from the placed sitar, carried on the chart) plays as
    # written, its bass included. Otherwise the guitar's roots come from a slow chord floor under
    # the sitar — home held long, the head's one recurring move, the manjha and antara moving
    # (`crew/chord_floor.py`) — and the bass is derived from it.
    composed = arr.rhythm_section is not None
    floor = rhythm if composed else on_floor(rhythm, melody_layers, arr)
    if rhythm is not None:
        # Nothing damps a pitch against the sitar (Sujit kept the grinds by ear, 2026-10-11;
        # `crew/coexistence.py` measures the friction for the Producer). The floor only CHOOSES
        # its departures away from a held note's grind. Then WHEN it strikes: under a sitar-led
        # section the guitar rings through the sitar's held notes, ornaments and bursts instead
        # of striking through them (`crew/articulation.py`), and the antara climbs an octave.
        played = floor if composed else lift_antara(articulate(floor, melody_layers, arr), arr)
        layers.append(played)                        # the hard-left rhythm track
        double = double_track(played)                # the hard-right double (different gain patch)
        if double is not None:
            layers.append(double)
    # Bass, groove and tabla derive from the FLOORED riff (never the double, the ringing
    # articulation or the antara's lift), so the low end holds the floor and the kit keeps
    # driving while the guitar rings over them. The
    # clean guitar realises the chart's per-section HARMONY plan (crew/harmony.py) —
    # deterministic like the rest: the composers decided the modes, code plays them.
    # ONE harmonic guide, read by every accompanying voice: what the melody settles on, and
    # what must not sustain under it. Derived from the realized lead, so it exists only now —
    # which is exactly why the composers' colour choices could not have known it.
    guide = harmonic_guide(melody_layers, arr)
    bass = realise(arr.rhythm_section, arr)[1] if composed else bass_layer(arr, floor)
    for derived in (clean_layer(arr, guide=guide), bass,
                    groove_layer(arr, floor), _tabla_if_enabled(arr)):
        if derived is not None:
            layers.append(derived)
    # The taan exposure runs BEFORE the balance pass: the band-drop window empties first, then
    # the energy/foreground gains shape whatever still sounds. The ending comes LAST: its final
    # stroke sits past every section, so no balance gain should ever touch it.
    return apply_ending(apply_dynamics(apply_taan_exposure(layers, arr), arr), arr)


# The two creative LLM voices, injectable so their ORDER is tested with no LLM. Each takes the
# other voice's seed (None when it is the source): the lead may be handed the main riff to
# quote, the riff the cached gat head to reduce.
type LeadVoiceFn = Callable[[Arrangement, RiffPattern | None], tuple[list[Layer], list[DebateEvent]]]
type RiffVoiceFn = Callable[[Arrangement, LeadPhrase | None], tuple[Layer | None, list[DebateEvent]]]


def _quiet(agent: str, text: str) -> None:
    """The default `announce` — `compose_band` has no live stream to beat on."""


def _keep(events: list[DebateEvent]) -> None:
    """The default `emit` — the events are returned anyway; nothing to publish early."""


def compose_creative_voices(
        arr: Arrangement, *, lead_fn: LeadVoiceFn | None = None, riff_fn: RiffVoiceFn | None = None,
        announce: Callable[[str, str], None] = _quiet,
        emit: Callable[[list[DebateEvent]], None] = _keep,
) -> tuple[list[Layer], Layer | None, list[DebateEvent]]:
    """Compose the lead and the riff IN ANCHOR ORDER — the source first, then the voice that
    derives from it, handed the source's seed.

    `gat_first` (the default): the gat is composed, and the riff REDUCES its cached head.
    `riff_first`: the riff is composed, and the gat's head QUOTES the mukhada section's riff
    (verified in `lead._compose_gat`). Same calls, same cost — only the order and the seed
    change, so the composers' anchor finally decides how the piece is built. `announce`
    (agent, text) fires before each slow call and `emit` after it, so the Flow can stream
    progress while the work runs. Returns (lead_layers, rhythm, events) in composition order."""
    from crew.lead import compose_lead, mukhada_cell_from_events
    from crew.riff import compose_riff, mukhada_riff_from_events
    lead = lead_fn or compose_lead
    riff = riff_fn or compose_riff

    if arr.anchor == "riff_first":
        announce("Riff", "laying down the main riff — it seeds the gat…")
        rhythm, riff_events = riff(arr, None)
        emit(riff_events)
        announce("Lead", "composing the gat on the riff…")
        lead_layers, lead_events = lead(arr, mukhada_riff_from_events(riff_events))
        emit(lead_events)
        return lead_layers, rhythm, [*riff_events, *lead_events]

    announce("Lead", "composing the gat…")
    lead_layers, lead_events = lead(arr, None)
    emit(lead_events)
    announce("Riff", "laying down the riff…")
    rhythm, riff_events = riff(arr, mukhada_cell_from_events(lead_events))
    emit(riff_events)
    return lead_layers, rhythm, [*lead_events, *riff_events]


def _creative_voices(arr: Arrangement) -> tuple[list[Layer], Layer | None, list[DebateEvent]]:
    """The parallel path's lead + riff, or — with `RMA_RHYTHM_SECTION` — the lead and then ONE
    rhythm-section call around it (the riff the fallback)."""
    from crew.config import rhythm_section_enabled
    if not rhythm_section_enabled():
        return compose_creative_voices(arr)
    from crew.lead import mukhada_cell_from_events
    from crew.rhythm_section_call import compose_rhythm_section
    from crew.rhythm_voice import creative_voices_with_rhythm_section
    from crew.riff import compose_riff
    return creative_voices_with_rhythm_section(
        arr, voices=compose_creative_voices, composer=False, call=compose_rhythm_section,
        legacy_riff=lambda a, events: compose_riff(a, mukhada_cell_from_events(events)))


def compose_band(arr: Arrangement) -> tuple[Composition, list[DebateEvent]]:
    """Generate every voice for a chart and assemble the full Composition.

    The Lead and the Riff are the LLM calls (one per active section each); the bass,
    drums, tabla and drone are deterministic. Imports the LLM generators lazily so
    this module stays importable without paying the crewai import cost.
    """
    from crew.orchestra import compose_orchestra, uses_orchestra

    # Cross-voice seeding in ANCHOR order: the source voice first, the other derived from it.
    # The two lines go on as composed — their friction is measured, never repaired. With
    # `RMA_RHYTHM_SECTION` the guitar + bass are ONE call written around the placed sitar.
    lead_layers, rhythm, events = _creative_voices(arr)
    arr = with_rhythm_section(arr, events)
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
