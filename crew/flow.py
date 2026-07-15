"""
The Flow (finishing step 6) — the whole pipeline as ONE visible, bounded CrewAI Flow.

This is the orchestration the talk is really about: interpret -> composers -> generate
-> critics -> Conductor -> (surgical revise)* -> render, wired with CrewAI Flow
primitives so the propose->critique->revise loop is VISIBLE (and `flow.plot()`-able),
not autonomous magic. Two properties matter:

  * THE LOOP HAS A TERMINATOR IN CODE. Flows have no built-in loop cap (a documented
    footgun). Our `@router` reads `state.round` and ALWAYS returns "done" once the cap
    is hit — the referee and the clock. Never organic consensus.
  * THE REVISE IS SURGICAL. On a `revise` ruling we regenerate ONLY the flagged voice
    (lead or rhythm), thread the Conductor's directive through that section's `intent`,
    then re-derive the deterministic voices and re-assemble. The other voices stand.

Layering (pure core / imperative shell, and CLAUDE.md's "flow orchestration in its own
module"): this module holds ONLY orchestration. The agents/tasks live in their own
modules; the pipeline steps arrive as an injected `Stages` bundle (the composition
root), so the whole Flow — routing, the bounded loop, the surgical-revise wiring — is
tested with NO LLM and NO audio. `production_stages()` wires the real adapters.

Entry point (a bounded live run: fixed small chart, real generate/critique/conduct/render):
  uv run python -m crew.flow
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Optional

from crewai.flow.flow import Flow, listen, or_, router, start
from pydantic import BaseModel, Field

from crew.config import MAX_ROUNDS, load_env
from crew.contracts import (
    Arrangement,
    Composition,
    CompositionBrief,
    ConductorRuling,
    DebateEvent,
    EventType,
    Layer,
    ProducerVerdict,
    RasikVerdict,
    SectionCanvas,
    UstadVerdict,
)
from crew.live import publish, publish_all

_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
_SOUNDFONT: Final[Path] = _ROOT / "soundfonts" / "GeneralUser-GS.sf2"
_OUT_DIR: Final[Path] = _ROOT / "out"


# --------------------------------------------------------------------------- #
# Pure helpers: the SURGICAL revise. Thread the Conductor's directive into the #
# flagged voice's section intents (the existing generator hook) so a re-run    #
# actually addresses the critique — no generator change needed.                #
# --------------------------------------------------------------------------- #

def revise_arrangement(arr: Arrangement, ruling: ConductorRuling) -> Arrangement:
    """A COPY of the chart with the Conductor's directive appended to the intent of
    every section where the flagged voice plays — so re-running that generator reads
    the directive as creative intent. Pure; the original chart is untouched."""
    revised = arr.model_copy(deep=True)
    note = f" [REVISE — {ruling.reason}]" if ruling.reason else " [REVISE]"
    for section in revised.sections:
        if ruling.layer and ruling.layer in section.layers:
            section.intent = (section.intent or "") + note
    return revised


# --------------------------------------------------------------------------- #
# The injected pipeline. Each stage is a thin wrapper over an existing module;  #
# bundling them lets the Flow be tested with fakes (no LLM, no audio).          #
# --------------------------------------------------------------------------- #

type Interpret = Callable[[str], tuple[CompositionBrief, list[DebateEvent]]]
type Compose = Callable[[CompositionBrief], tuple[Arrangement, list[DebateEvent]]]
# generate/regenerate also carry the studio's per-section canvases (empty for the parallel
# path), retained in Flow state so a surgical revise can stay CANVAS-AWARE.
type Generate = Callable[
    [Arrangement],
    tuple[list[Layer], Optional[Layer], list[DebateEvent], list[SectionCanvas]]]
type Assemble = Callable[[Arrangement, list[Layer], Optional[Layer]], Composition]
type Critique = Callable[
    [Composition, Arrangement],
    tuple[UstadVerdict, RasikVerdict, ProducerVerdict, list[DebateEvent]]]
type Arbitrate = Callable[
    [UstadVerdict, RasikVerdict, ProducerVerdict, Composition],
    tuple[ConductorRuling, list[DebateEvent]]]
type Regenerate = Callable[
    [Arrangement, list[Layer], Optional[Layer], ConductorRuling, list[SectionCanvas]],
    tuple[list[Layer], Optional[Layer], list[DebateEvent], list[SectionCanvas]]]
type Render = Callable[[Composition], Optional[str]]


@dataclass(frozen=True)
class Stages:
    """The pipeline steps the Flow orchestrates — injected so the loop is testable."""
    interpret: Interpret
    compose: Compose
    generate: Generate
    assemble: Assemble
    critique: Critique
    arbitrate: Arbitrate
    regenerate: Regenerate
    render: Render


# The real adapters (lazy imports keep crewai off the light path until a stage runs).

def _interpret(query: str) -> tuple[CompositionBrief, list[DebateEvent]]:
    from crew.interpreter import interpret
    return interpret(query)


def _compose(brief: CompositionBrief) -> tuple[Arrangement, list[DebateEvent]]:
    from crew.composers import compose
    return compose(brief)


def _generate(arr: Arrangement) -> tuple[list[Layer], Optional[Layer], list[DebateEvent],
                                          list[SectionCanvas]]:
    """Generate the two creative voices — one of two paths, selected by config:

      * COOPERATIVE (`RMA_STUDIO=1`): Lead and Riff compose TOGETHER on a shared canvas,
        each answering what the other just played (the studio session — DESIGN.md's second
        named pattern);
      * PARALLEL (default): each composes in isolation against the shared chart.

    Both return (lead_layers, rhythm, events, canvases), so the rest of the Flow — assembly,
    critics, Conductor, render — is identical either way. `canvases` is empty for the parallel
    path and the per-section SectionCanvas list for the studio; the Flow keeps it in state so
    a surgical revise can regenerate the flagged voice CANVAS-AWARE (the collaboration
    survives the critique loop), while the parallel path revises standalone.
    """
    from crew.config import canvas_passes, studio_enabled
    if studio_enabled():
        from crew.studio_session import compose_studio
        return compose_studio(arr, passes=canvas_passes())
    from crew.lead import compose_lead, mukhada_cell_from_events
    from crew.riff import compose_riff
    publish(_running("Lead", "composing the gat…"))   # a RUNNING beat streams AHEAD of the slow work,
    lead_layers, e1 = compose_lead(arr)               # so the UI spotlights Lead WHILE it composes
    publish_all(e1)
    publish(_running("Riff", "laying down the riff…"))
    # Cross-voice seeding: the riff reduces the cached gat head (fished from the lead's
    # events), so the band hears the mukhada IN the riff.
    rhythm, e2 = compose_riff(arr, mukhada=mukhada_cell_from_events(e1))
    publish_all(e2)
    return lead_layers, rhythm, [*e1, *e2], []


def _assemble(arr: Arrangement, lead_layers: list[Layer], rhythm: Optional[Layer]) -> Composition:
    from crew.band import band_layers
    from crew.generators import assemble_composition
    return assemble_composition(arr, band_layers(arr, lead_layers, rhythm))


def _critique(comp: Composition,
              arr: Arrangement) -> tuple[UstadVerdict, RasikVerdict, ProducerVerdict, list[DebateEvent]]:
    """Three critics, three dimensions: Ustad (legality) and Rasik (raga authenticity)
    judge the Composition; the Producer (composition quality) also reads the Arrangement —
    the chart is the score a musical director needs."""
    from crew.producer import critique_composition
    from crew.rasik import critique_taste
    from crew.ustad import critique_legality
    publish(_running("Ustad", "checking the raga's legality…", role="critic"))
    ustad, e1 = critique_legality(comp)
    publish_all(e1)
    publish(_running("Rasik", "judging the raga authenticity…", role="critic"))
    rasik, e2 = critique_taste(comp)
    publish_all(e2)
    publish(_running("Producer", "judging the song craft…", role="critic"))
    producer, e3 = critique_composition(comp, arr)
    publish_all(e3)
    return ustad, rasik, producer, [*e1, *e2, *e3]


def _arbitrate(ustad: UstadVerdict, rasik: RasikVerdict, producer: ProducerVerdict,
               comp: Composition) -> tuple[ConductorRuling, list[DebateEvent]]:
    from crew.conductor import conduct
    publish(_running("Conductor", "weighing the critics…", role="conductor"))
    return conduct(ustad, rasik, producer, comp)


def _regenerate(arr: Arrangement, lead_layers: list[Layer], rhythm: Optional[Layer],
                ruling: ConductorRuling, canvases: list[SectionCanvas]
                ) -> tuple[list[Layer], Optional[Layer], list[DebateEvent], list[SectionCanvas]]:
    """Regenerate ONLY the flagged creative voice, steered by the directive. If the studio
    produced canvases (the cooperative path), regenerate CANVAS-AWARE — the voice still sees
    the other's line, so the collaboration survives the revise; otherwise (the parallel path)
    do the standalone surgical fix. The derivable voices (drone/bass/drums/tabla) re-derive at
    reassembly either way. A ruling targeting a non-creative voice has nothing to regenerate."""
    revised = revise_arrangement(arr, ruling)
    if canvases:
        from crew.studio_session import regenerate_layer
        return regenerate_layer(revised, canvases, ruling.layer)
    from crew.lead import compose_lead
    from crew.riff import compose_riff
    if ruling.layer == "rhythm":
        publish(_running("Riff", "reworking the riff…"))
        new_rhythm, events = compose_riff(revised)
        return lead_layers, new_rhythm, events, canvases
    if ruling.layer == "lead":
        publish(_running("Lead", "reworking the gat…"))
        new_lead, events = compose_lead(revised)
        return new_lead, rhythm, events, canvases
    return lead_layers, rhythm, [], canvases


def _render(comp: Composition, *, soundfont: Path, out_dir: Path, name: str) -> Optional[str]:
    import shutil
    from crew.generators import render_composition
    if not (shutil.which("fluidsynth") and soundfont.exists()):
        return None
    return str(render_composition(comp, out_dir=out_dir, name=name, soundfont=soundfont))


def _default_render_name() -> str:
    """A unique per-run render name (fusion_YYYYMMDD_HHMMSS), so a new live render never
    OVERWRITES an earlier one — each run's .wav/.mid/.json triplet stays comparable
    against its predecessors (Sujit's rule, 2026-07-15). Called at wiring time, never
    at import (no import-time side effects)."""
    from datetime import datetime
    return f"fusion_{datetime.now():%Y%m%d_%H%M%S}"


def production_stages(*, soundfont: Path = _SOUNDFONT, out_dir: Path = _OUT_DIR,
                      name: str | None = None) -> Stages:
    """Wire the real adapters (the composition root). `name` defaults to a unique
    timestamped render name; pass one explicitly to pin it."""
    name = name or _default_render_name()
    return Stages(
        interpret=_interpret, compose=_compose, generate=_generate, assemble=_assemble,
        critique=_critique, arbitrate=_arbitrate, regenerate=_regenerate,
        render=lambda comp: _render(comp, soundfont=soundfont, out_dir=out_dir, name=name))


# --------------------------------------------------------------------------- #
# Flow state (a Pydantic model, per CLAUDE.md) + the events.                   #
# --------------------------------------------------------------------------- #

class ComposeState(BaseModel):
    """The Flow's typed state (an `id` field is auto-added by CrewAI)."""
    query: str = ""
    round: int = 0                                    # revise rounds so far — the router's clock
    arrangement: Optional[Arrangement] = None
    lead_layers: list[Layer] = Field(default_factory=list)
    rhythm: Optional[Layer] = None
    canvases: list[SectionCanvas] = Field(default_factory=list)   # studio canvases (empty if parallel) — kept so a revise stays canvas-aware
    composition: Optional[Composition] = None
    ustad: Optional[UstadVerdict] = None
    rasik: Optional[RasikVerdict] = None
    producer: Optional[ProducerVerdict] = None
    ruling: Optional[ConductorRuling] = None
    events: list[DebateEvent] = Field(default_factory=list)
    wav_path: Optional[str] = None


def _flow_event(text: str) -> DebateEvent:
    return DebateEvent(type=EventType.INFO, agent="Flow", role="system", text=text)


def _running(agent: str, text: str, role: str = "generator") -> DebateEvent:
    """A 'component STARTED working' beat, `publish()`ed to the live sink IMMEDIATELY before an
    agent's slow LLM work — so the UI spotlights the right mascot and shows a 'composing…'
    placeholder WHILE it works, instead of only jumping after it finishes. Named per agent so the
    spotlight lands correctly (the old vague agent='Flow' narration hijacked it). Live-only: it is
    published, never added to `state.events`, so the persisted stream / replay contract is unchanged."""
    return DebateEvent(type=EventType.RUNNING, agent=agent, role=role, text=text)


# --------------------------------------------------------------------------- #
# The Flow. The bounded loop is driven by ROUTER LABELS, not method completions:  #
# CrewAI re-arms an or_() listener for a repeat only when a ROUTER re-emits a      #
# label the listener references (a plain method-completion or_ fires just once).   #
# So `revise_layer` is a @router that re-emits "recritique", and `critique`        #
# listens to or_(begin, "recritique") to re-enter each round. Method order still   #
# matters for the method refs: `begin` precedes `critique`; the string labels      #
# ("revise"/"recritique"/"done") need no forward reference.                        #
# --------------------------------------------------------------------------- #

class ComposeFlow(Flow[ComposeState]):
    """propose -> critique -> arbitrate -> (surgical revise -> critique)* -> render.

    The `@router` is the guaranteed terminator: it returns "done" on an accept OR once
    `state.round` hits the cap, so the revise loop can never run away. The revise step
    feeds back into `critique` via `or_(begin, revise)` — the visible bounded loop.
    """

    def __init__(self, stages: Stages, *, max_rounds: int = MAX_ROUNDS) -> None:
        super().__init__()
        self._stages = stages
        self._max_rounds = max_rounds

    @start()
    def begin(self) -> None:
        """interpret the query, arrange the chart, generate the creative voices, assemble."""
        st = self.state
        publish(_running("Interpreter", "reading your request…", role="system"))
        brief, e1 = self._stages.interpret(st.query)
        publish_all(e1)                               # stream each phase as it completes
        publish(_running("Pandit", "negotiating the chart with Riffsmith…", role="composer"))
        arr, e2 = self._stages.compose(brief)
        publish_all(e2)
        lead_layers, rhythm, e3, canvases = self._stages.generate(arr)   # emits its own RUNNING beats
        st.arrangement = arr
        st.lead_layers = lead_layers
        st.rhythm = rhythm
        st.canvases = canvases
        st.composition = self._stages.assemble(arr, lead_layers, rhythm)
        st.events.extend([*e1, *e2, *e3])

    @router("revise")
    def revise_layer(self) -> str:
        """Surgical revise: regenerate ONLY the flagged voice, re-derive + re-assemble,
        then re-emit "recritique" to send the new composition back through the critics.

        This is a @router (not a plain @listen) on purpose: the loop only re-fires
        `critique` when a ROUTER re-emits a label it listens to, so the re-entry label
        must come from here. Named distinctly from the "revise" LABEL it consumes — a
        method named `revise` listening to "revise" reads to CrewAI as a self-reference.
        """
        st = self.state
        assert st.arrangement is not None and st.ruling is not None
        lead_layers, rhythm, events, canvases = self._stages.regenerate(
            st.arrangement, st.lead_layers, st.rhythm, st.ruling, st.canvases)
        st.lead_layers = lead_layers
        st.rhythm = rhythm
        st.canvases = canvases
        st.composition = self._stages.assemble(st.arrangement, lead_layers, rhythm)
        publish_all(events)
        st.events.extend(events)
        return "recritique"

    @listen(or_(begin, "recritique"))
    def critique(self) -> None:
        """Three critics judge the current composition: Ustad (legality), Rasik (raga
        authenticity), Producer (composition quality — reads the chart too)."""
        st = self.state
        assert st.composition is not None and st.arrangement is not None
        # _critique streams each critic's RUNNING beat + events itself (per-critic spotlighting),
        # so we do NOT publish_all(events) again here — that would double them on the live stream.
        ustad, rasik, producer, events = self._stages.critique(st.composition, st.arrangement)
        st.ustad = ustad
        st.rasik = rasik
        st.producer = producer
        st.events.extend(events)

    @listen(critique)
    def arbitrate(self) -> None:
        """The Conductor triages, runs the Rasik vs Producer debate on a conflict, and
        rules accept | revise."""
        st = self.state
        assert (st.ustad is not None and st.rasik is not None
                and st.producer is not None and st.composition is not None)
        ruling, events = self._stages.arbitrate(st.ustad, st.rasik, st.producer, st.composition)
        st.ruling = ruling
        publish_all(events)
        st.events.extend(events)

    @router(arbitrate)
    def route(self) -> str:
        """The terminator: accept, or revise until the round cap — then done, always."""
        st = self.state
        assert st.ruling is not None
        if st.ruling.directive == "accept":
            return "done"
        if st.round >= self._max_rounds:
            capped = _flow_event(f"Revise cap ({self._max_rounds}) reached — accepting the last version.")
            st.events.append(capped)
            publish(capped)
            return "done"
        st.round += 1
        revising = _flow_event(
            f"Revise round {st.round}: regenerating '{st.ruling.layer}' per the Conductor.")
        st.events.append(revising)
        publish(revising)
        return "revise"

    @listen("done")
    def finish(self) -> None:
        """Render the accepted composition to a WAV (skipped if fluidsynth is absent)."""
        st = self.state
        assert st.composition is not None
        publish(_running("System", "rendering the audio…", role="system"))
        st.wav_path = self._stages.render(st.composition)


def compose_flow(query: str, *, stages: Optional[Stages] = None,
                 max_rounds: int = MAX_ROUNDS) -> ComposeState:
    """Run the full pipeline as a Flow and return its final state (composition, the
    event stream, the ruling, the rendered WAV path). `stages` is injectable — defaults
    to the real adapters."""
    flow = ComposeFlow(stages or production_stages(), max_rounds=max_rounds)
    flow.kickoff(inputs={"query": query})
    return flow.state


# --------------------------------------------------------------------------- #
# Entry point — a BOUNDED live run: a fixed small chart (so interpret/composers  #
# aren't re-billed — already confirmed), real generate/critique/conduct/render.  #
# This exercises the NEW integration end-to-end for a handful of LLM calls.      #
# --------------------------------------------------------------------------- #

def _demo_arrangement() -> Arrangement:
    """A 3-section fusion arc that SHOWCASES the cooperative studio: a riff-LED opener
    (the Riff proposes the main hook, the Lead answers it), a lead-LED taan (the Lead
    proposes, the Riff beds it), and a RETURN of the main riff (a reprise — the hook comes
    back and the Lead answers it fresh). Both creative voices are active in every section so
    the collaboration actually happens; the shared 'main' slot makes the third section a
    reprise rather than a new riff."""
    from crew.contracts import ArrangementDraft, Section, SectionKind, build_arrangement
    band = ["rhythm", "lead", "drums", "drone"]
    draft = ArrangementDraft(
        raga="darbari", subgenre="progressive", tala="teentaal", bpm=120,
        motif=["S", "R", "g", "R", "g", "m", "P"],
        sections=[
            Section(kind=SectionKind.RIFF, bars=1, layers=band, foreground="rhythm",
                    riff_slot="main", intent="the main riff — heavy and root-driven",
                    transition="lift into the taan"),
            Section(kind=SectionKind.TAAN, bars=1, layers=band, foreground="lead",
                    intent="a harmonized taan climbing to the climax",
                    transition="crash back to the main riff"),
            Section(kind=SectionKind.RIFF, bars=1, layers=band, foreground="rhythm",
                    riff_slot="main", intent="the main riff returns as the outro hook"),
        ])
    return build_arrangement(draft, CompositionBrief(mood="dark"))


def _demo_stages() -> Stages:
    """Real downstream, but interpret/compose are stubbed to a fixed chart so the live
    run doesn't re-bill the already-confirmed intake + composer dialogue."""
    from dataclasses import replace
    arr = _demo_arrangement()
    return replace(production_stages(name="flow_demo"),
                   interpret=lambda query: (CompositionBrief(mood="dark"), []),
                   compose=lambda brief: (arr, []))


def _run() -> None:
    from crew.contracts import EventStream
    stream = EventStream()
    state = compose_flow("a dark progressive fusion in Darbari", stages=_demo_stages())
    for event in state.events:
        stream.emit(event)
    ruling = state.ruling
    print(f"\nfinal ruling: {ruling.directive if ruling else '?'} "
          f"(after {state.round} revise round(s))")
    print(f"rendered: {state.wav_path or '(render skipped — no fluidsynth/soundfont)'}")


def main(argv: list[str]) -> int:
    load_env()  # entry point loads .env
    from contextlib import nullcontext

    from crew.tracing import traced, tracing_enabled
    ctx = traced("flow-demo") if tracing_enabled() else nullcontext()
    with ctx:
        _run()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
