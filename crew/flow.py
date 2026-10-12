"""
The Flow (finishing step 6) — the whole pipeline as ONE visible, bounded CrewAI Flow.

This is the orchestration: interpret -> composers -> generate -> critics (Ustad in code,
Rasik consulting, the Producer deciding) -> (edit-based revise)* -> render, wired with CrewAI
Flow primitives so the propose->critique->revise loop is VISIBLE (and `flow.plot()`-able),
not autonomous magic. Three properties matter:

  * THE LOOP HAS A TERMINATOR IN CODE. Flows have no built-in loop cap (a documented
    footgun). Our `@router` reads `state.round` and ALWAYS returns "done" once the cap
    is hit — the clock. Never organic consensus.
  * ONE JUDGE DECIDES. Since the 2026-10-11 redesign there is no critic debate and no
    Conductor: an illegal piece is a forced revise decided by code, otherwise the Producer
    (who has read Rasik's consultation) accepts or issues ONE `RevisionPlan` (`crew/triage.py`).
  * THE REVISE IS EDIT-BASED. The plan's voice is regenerated with its instruction and its
    PRESERVE list threaded into the targeted sections' intent, and only those sections' new
    notes are spliced in (`crew/revision.py`); everything else stands, then the deterministic
    voices re-derive and the piece re-assembles.

Layering (pure core / imperative shell, and CLAUDE.md's "flow orchestration in its own
module"): this module holds ONLY orchestration. The agents/tasks live in their own
modules; the pipeline steps arrive as an injected `Stages` bundle (the composition
root), so the whole Flow — routing, the bounded loop, the surgical-revise wiring — is
tested with NO LLM and NO audio. `production_stages()` wires the real adapters.

Entry point (a bounded live run: fixed small chart, real generate/critique/decide/render):
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

from crew.anchor import with_realized_seeds
from crew.config import MAX_ROUNDS, listening_enabled, load_env
from crew.contracts import (
    Arrangement,
    Composition,
    CompositionBrief,
    DebateEvent,
    EventType,
    Layer,
    ProducerScores,
    ProducerVerdict,
    RasikVerdict,
    RevisionPlan,
    SectionCanvas,
    UstadVerdict,
    plan_layer,
)
from crew.live import publish, publish_all
from crew.rhythm_section import with_rhythm_section
from crew.revision import (
    is_stalled,
    revise_arrangement,
    splice_layer,
    splice_layers,
    target_sections,
)

_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
_SOUNDFONT: Final[Path] = _ROOT / "soundfonts" / "GeneralUser-GS.sf2"
_OUT_DIR: Final[Path] = _ROOT / "out"


# --------------------------------------------------------------------------- #
# The injected pipeline. Each stage is a thin wrapper over an existing module;  #
# bundling them lets the Flow be tested with fakes (no LLM, no audio).          #
# --------------------------------------------------------------------------- #

type Interpret = Callable[[str], tuple[CompositionBrief, list[DebateEvent]]]
type Compose = Callable[[CompositionBrief], tuple[Arrangement, list[DebateEvent]]]
# generate/regenerate also carry: the ORCHESTRA layers (the symphonic voice — empty when the
# chart doesn't use it), and the studio's per-section canvases (empty for the parallel path),
# both retained in Flow state so a surgical revise can re-assemble and stay CANVAS-AWARE.
type Generate = Callable[
    [Arrangement],
    tuple[list[Layer], Optional[Layer], list[Layer], list[DebateEvent], list[SectionCanvas]]]
type Assemble = Callable[[Arrangement, list[Layer], Optional[Layer], list[Layer]], Composition]
type Critique = Callable[
    [Composition, Arrangement],
    tuple[UstadVerdict, RasikVerdict, ProducerVerdict, list[DebateEvent]]]
# The final call: (the plan to carry out, or None to accept) + its VERDICT event.
type Decide = Callable[
    [UstadVerdict, RasikVerdict, ProducerVerdict, Composition, Arrangement],
    tuple[Optional[RevisionPlan], list[DebateEvent]]]
# (chart, lead, rhythm, orchestra, plan, canvases, history) — `history` is the run's events so
# far, from which a TARGETED revise reads what each voice realized (`crew.realized`).
type Regenerate = Callable[
    [Arrangement, list[Layer], Optional[Layer], list[Layer], RevisionPlan, list[SectionCanvas],
     list[DebateEvent]],
    tuple[list[Layer], Optional[Layer], list[Layer], list[DebateEvent], list[SectionCanvas]]]
type Render = Callable[[Composition], Optional[str]]
# The ADVISORY listening pass: (wav path, chart) -> its report as events. Post-render only, and
# never a gate — it is uncalibrated against Sujit's ear (DESIGN.md "THE REDESIGN").
type Listen = Callable[[str, Arrangement], list[DebateEvent]]


@dataclass(frozen=True)
class Stages:
    """The pipeline steps the Flow orchestrates — injected so the loop is testable."""
    interpret: Interpret
    compose: Compose
    generate: Generate
    assemble: Assemble
    critique: Critique
    decide: Decide
    regenerate: Regenerate
    render: Render
    listen: Optional[Listen] = None      # the advisory listening pass (None = off)


# The real adapters (lazy imports keep crewai off the light path until a stage runs).

def _interpret(query: str) -> tuple[CompositionBrief, list[DebateEvent]]:
    from crew.interpreter import interpret
    return interpret(query)


def _compose(brief: CompositionBrief) -> tuple[Arrangement, list[DebateEvent]]:
    """The chart. With `RMA_COMPOSER` the single Composer writes it in ONE seed call together with
    the main riff and the hook (carried on the chart); otherwise Pandit and Riffsmith negotiate it."""
    from crew.config import composer_enabled
    if composer_enabled():
        from crew.composer import compose_seed
        return compose_seed(brief)
    from crew.composers import compose
    return compose(brief)


def _creative_voices(arr: Arrangement) -> tuple[list[Layer], Optional[Layer], list[DebateEvent],
                                                list[SectionCanvas]]:
    """Lead + riff, by the configured path: the single Composer DEVELOPING its seed
    (`RMA_COMPOSER` — the studio is not used there: one owner is the point), the cooperative
    studio (`RMA_STUDIO`), or the parallel voices in anchor order (the default)."""
    from crew.config import canvas_passes, composer_enabled, rhythm_section_enabled, studio_enabled
    announce = lambda agent, text: publish(_running(agent, text))  # noqa: E731
    if rhythm_section_enabled() and (composer_enabled() or not studio_enabled()):
        return (*_voices_with_rhythm_section(arr, composer_enabled(), announce), [])
    if composer_enabled():
        from crew.composer import compose_seeded_voices
        lead_layers, rhythm, events = compose_seeded_voices(arr, announce=announce, emit=publish_all)
        return lead_layers, rhythm, events, []
    if studio_enabled():
        from crew.studio_session import compose_studio
        return compose_studio(arr, passes=canvas_passes())
    from crew.band import compose_creative_voices
    # Cross-voice seeding in ANCHOR order (gat_first: the riff reduces the head;
    # riff_first: the head quotes the riff). A RUNNING beat streams AHEAD of each slow
    # call, so the UI spotlights the voice WHILE it composes.
    lead_layers, rhythm, events = compose_creative_voices(arr, announce=announce, emit=publish_all)
    return lead_layers, rhythm, events, []


def _voices_with_rhythm_section(arr: Arrangement, composer: bool, announce: Callable[[str, str], None]
                                ) -> tuple[list[Layer], Optional[Layer], list[DebateEvent]]:
    """The sitar on the path's own composer, then ONE call for guitar + bass around it
    (`RMA_RHYTHM_SECTION`); the path's per-section riff is the fallback."""
    from crew.rhythm_section_call import compose_rhythm_section
    from crew.rhythm_voice import creative_voices_with_rhythm_section
    if composer:
        from crew.composer import compose_seeded_voices as voices
        from crew.riff import compose_seeded_riff

        def legacy(a: Arrangement, events: list[DebateEvent]):
            return compose_seeded_riff(with_realized_seeds(a, events))
    else:
        from crew.band import compose_creative_voices as voices
        from crew.lead import mukhada_cell_from_events
        from crew.riff import compose_riff

        def legacy(a: Arrangement, events: list[DebateEvent]):
            return compose_riff(a, mukhada_cell_from_events(events))
    return creative_voices_with_rhythm_section(arr, voices=voices, composer=composer,
                                               call=compose_rhythm_section, legacy_riff=legacy,
                                               announce=announce, emit=publish_all)


def _generate(arr: Arrangement) -> tuple[list[Layer], Optional[Layer], list[Layer],
                                          list[DebateEvent], list[SectionCanvas]]:
    """Generate the creative voices — one of two paths for lead + riff, selected by config:

      * COOPERATIVE (`RMA_STUDIO=1`): Lead and Riff compose TOGETHER on a shared canvas,
        each answering what the other just played (the studio session — DESIGN.md's second
        named pattern);
      * PARALLEL (default): each composes in isolation against the shared chart.

    Then, on EITHER path, the CAPABILITY-GATED Orchestra joins when the chart calls for it
    (`uses_orchestra`) — one whole-chart call, scoring AROUND the realized lead + riff.

    Returns (lead_layers, rhythm, orchestra_layers, events, canvases), so the rest of the Flow
    — assembly, critics, decision, render — is identical either way. The riff and the lead go
    on exactly as composed: their grinds are KEPT (Sujit, by ear) and only measured. `orchestra_layers` is
    empty off a symphonic/orchestral chart; `canvases` is empty for the parallel path and the
    per-section SectionCanvas list for the studio. Both live in Flow state so a surgical revise
    re-assembles correctly and stays CANVAS-AWARE.
    """
    lead_layers, rhythm, events, canvases = _creative_voices(arr)
    orchestra_layers: list[Layer] = []
    from crew.orchestra import compose_orchestra, uses_orchestra
    if uses_orchestra(arr):
        publish(_running("Orchestra", "scoring the orchestra…"))
        orchestra_layers, eo = compose_orchestra(arr, lead_layers=lead_layers, rhythm=rhythm)
        publish_all(eo)
        events = [*events, *eo]
    return lead_layers, rhythm, orchestra_layers, events, canvases


def _assemble(arr: Arrangement, lead_layers: list[Layer], rhythm: Optional[Layer],
              orchestra_layers: list[Layer]) -> Composition:
    from crew.band import band_layers
    from crew.generators import assemble_composition
    return assemble_composition(arr, band_layers(arr, lead_layers, rhythm, orchestra_layers))


def _critique(comp: Composition,
              arr: Arrangement) -> tuple[UstadVerdict, RasikVerdict, ProducerVerdict, list[DebateEvent]]:
    """Three dimensions, in order: Ustad (legality — code, instant), Rasik (raga authenticity,
    consulting with lead edits), then the Producer (song craft — the judge with the final say,
    who reads the chart AND Rasik's consultation)."""
    from crew.producer import critique_composition
    from crew.rasik import critique_taste
    from crew.ustad import critique_legality
    ustad, e1 = critique_legality(comp)
    publish_all(e1)
    publish(_running("Rasik", "consulting on the raga…", role="critic"))
    rasik, e2 = critique_taste(comp, arr.request, arr)
    publish_all(e2)
    publish(_running("Producer", "judging the song craft…", role="critic"))
    producer, e3 = critique_composition(comp, arr, rasik)
    publish_all(e3)
    return ustad, rasik, producer, [*e1, *e2, *e3]


def _decide(ustad: UstadVerdict, rasik: RasikVerdict, producer: ProducerVerdict,
            comp: Composition, arr: Arrangement) -> tuple[Optional[RevisionPlan], list[DebateEvent]]:
    """The final call — code triage (legality forces a revise) then the Producer's decision.
    Rasik's consultation already reached the Producer; the composition and chart are part of
    the stage signature so an injected decider can read them."""
    from crew.triage import decide
    return decide(ustad, producer, comp, arr)


def _regenerate(arr: Arrangement, lead_layers: list[Layer], rhythm: Optional[Layer],
                orchestra_layers: list[Layer], plan: RevisionPlan,
                canvases: list[SectionCanvas], history: list[DebateEvent] | None = None
                ) -> tuple[list[Layer], Optional[Layer], list[Layer], list[DebateEvent],
                           list[SectionCanvas]]:
    """Rework ONLY the plan's voice, steered by its instruction + preserve list, and splice the
    new notes into ONLY the plan's sections; the other voices stand and re-derive at
    reassembly. The studio path regenerates CANVAS-AWARE (the collaboration survives).

    The lead and the riff revise is TARGETED: the model is called only for the plan's sections
    (`_revise_lead` / `_revise_riff`), every other section replayed from what the voice realized
    (read from `history`), by the persona that wrote it — `composer` on the single-Composer path."""
    revised = revise_arrangement(arr, plan)
    if plan.voice == "orchestra":
        from crew.orchestra import compose_orchestra
        publish(_running("Orchestra", "reworking the orchestra…"))
        new_orch, events = compose_orchestra(revised, lead_layers=lead_layers, rhythm=rhythm)
        return (lead_layers, rhythm, splice_layers(arr, plan, orchestra_layers, new_orch),
                events, canvases)
    if canvases:
        from crew.studio_session import regenerate_layer
        new_lead, new_rhythm, events, new_canvases = regenerate_layer(revised, canvases,
                                                                       plan_layer(plan))
        return (_spliced_lead(arr, plan, lead_layers, new_lead),
                _spliced_riff(arr, plan, rhythm, new_rhythm), orchestra_layers, events,
                new_canvases)
    if plan.voice == "riff" and arr.rhythm_section is not None:
        from crew.rhythm_section_call import compose_rhythm_section
        from crew.rhythm_voice import revise_rhythm_voice
        announce = lambda agent, text: publish(_running(agent, text))  # noqa: E731
        new_rhythm, events = revise_rhythm_voice(arr, revised, plan, lead_layers,
                                                 call=compose_rhythm_section, announce=announce)
        return lead_layers, new_rhythm, orchestra_layers, events, canvases
    if plan.voice == "riff":
        new_rhythm, events = _revise_riff(arr, revised, plan, list(history or []))
        return lead_layers, splice_layer(arr, plan, rhythm, new_rhythm), orchestra_layers, events, canvases
    new_lead, events, edited = _revise_lead(arr, revised, plan, list(history or []))
    return (splice_layers(arr, edited, lead_layers, new_lead), rhythm, orchestra_layers, events,
            canvases)


def _persona(voice: str) -> str:
    from crew.config import composer_enabled
    return "composer" if composer_enabled() else voice


def _revise_riff(arr: Arrangement, revised: Arrangement, plan: RevisionPlan,
                 history: list[DebateEvent]) -> tuple[Optional[Layer], list[DebateEvent]]:
    """The riff revise: only the targeted sections' slots are re-composed when a realized library
    is on record; with none (a run that never published one), the whole voice, as before."""
    from crew.realized import realized_riffs
    from crew.riff import compose_riff, revise_riff
    library = realized_riffs(history)
    targets = target_sections(arr, plan)
    publish(_running("Riff", f"reworking the riff in section(s) {targets}…"))
    if library is None:
        return compose_riff(revised)
    return revise_riff(revised, library, targets, agent_key=_persona("riff"))


def _revise_lead(arr: Arrangement, revised: Arrangement, plan: RevisionPlan,
                 history: list[DebateEvent]) -> tuple[list[Layer], list[DebateEvent], RevisionPlan]:
    """The lead revise: only the targeted sections (widened to every hook section when the plan
    names the head) are re-composed. Returns the layers, the events, and the plan as actually
    carried out — its sections widened — so the splice takes exactly what was re-composed."""
    from crew.lead import compose_lead, lead_revise_targets, revise_lead
    from crew.realized import kept_lead, realized_lead
    targets = lead_revise_targets(arr, target_sections(arr, plan))
    edited = plan.model_copy(update={"sections": targets})
    publish(_running("Lead", f"reworking the lead in section(s) {targets}…"))
    kept = realized_lead(history)
    if kept is None:
        new_lead, events = compose_lead(revised)
        return new_lead, events, edited
    new_lead, events = revise_lead(revised, kept_lead(kept, targets), agent_key=_persona("lead"))
    return new_lead, events, edited


def _spliced_lead(arr: Arrangement, plan: RevisionPlan, old: list[Layer],
                  new: list[Layer]) -> list[Layer]:
    return splice_layers(arr, plan, old, new) if plan.voice == "lead" else new


def _spliced_riff(arr: Arrangement, plan: RevisionPlan, old: Optional[Layer],
                  new: Optional[Layer]) -> Optional[Layer]:
    return splice_layer(arr, plan, old, new) if plan.voice == "riff" else new


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
        critique=_critique, decide=_decide, regenerate=_regenerate,
        render=lambda comp: _render(comp, soundfont=soundfont, out_dir=out_dir, name=name),
        listen=_listen if listening_enabled() else None)


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
    orchestra_layers: list[Layer] = Field(default_factory=list)   # the symphonic voice (empty off an orchestral chart)
    canvases: list[SectionCanvas] = Field(default_factory=list)   # studio canvases (empty if parallel) — kept so a revise stays canvas-aware
    composition: Optional[Composition] = None
    ustad: Optional[UstadVerdict] = None
    rasik: Optional[RasikVerdict] = None
    producer: Optional[ProducerVerdict] = None
    decision: str = ""                                # "accept" | "revise" — the last final call
    plan: Optional[RevisionPlan] = None               # the revision being carried out (None = accept)
    asked_plan: Optional[RevisionPlan] = None         # the judge's last plan that was carried out...
    asked_scores: Optional[ProducerScores] = None     # ...and the scores it was asked from (the stop rule)
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
    """propose -> critique -> decide -> (edit-based revise -> critique)* -> render.

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
        publish(_compose_beat())
        arr, e2 = self._stages.compose(brief)
        publish_all(e2)
        lead_layers, rhythm, orchestra_layers, e3, canvases = self._stages.generate(arr)   # emits its own RUNNING beats
        # The chart keeps the REALIZED head + main riff as its seeds (a Composer's seeds are kept
        # as they are), so a revise hands the riff its head and the gat its riff, never nothing.
        # A composed rhythm section rides the chart too, so assembly realises its bass.
        st.arrangement = with_rhythm_section(with_realized_seeds(arr, e3), e3)
        st.lead_layers = lead_layers
        st.rhythm = rhythm
        st.orchestra_layers = orchestra_layers
        st.canvases = canvases
        st.composition = self._stages.assemble(st.arrangement, lead_layers, rhythm, orchestra_layers)
        st.events.extend([*e1, *e2, *e3])

    @router("revise")
    def revise_layer(self) -> str:
        """Edit-based revise: rework ONLY the plan's voice in the plan's sections, re-derive +
        re-assemble, then re-emit "recritique" to send the new composition back to the critics.

        This is a @router (not a plain @listen) on purpose: the loop only re-fires
        `critique` when a ROUTER re-emits a label it listens to, so the re-entry label
        must come from here. Named distinctly from the "revise" LABEL it consumes — a
        method named `revise` listening to "revise" reads to CrewAI as a self-reference.
        """
        st = self.state
        assert st.arrangement is not None and st.plan is not None
        lead_layers, rhythm, orchestra_layers, events, canvases = self._stages.regenerate(
            st.arrangement, st.lead_layers, st.rhythm, st.orchestra_layers, st.plan, st.canvases,
            st.events)
        st.arrangement = with_rhythm_section(st.arrangement, events)   # a rhythm revise rewrote it
        st.lead_layers = lead_layers
        st.rhythm = rhythm
        st.orchestra_layers = orchestra_layers
        st.canvases = canvases
        st.composition = self._stages.assemble(st.arrangement, lead_layers, rhythm, orchestra_layers)
        publish_all(events)
        st.events.extend(events)
        return "recritique"

    @listen(or_(begin, "recritique"))
    def critique(self) -> None:
        """The critics judge the current composition: Ustad (legality, code), Rasik (raga
        consultation), the Producer (song craft — reads the chart and Rasik, then decides)."""
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
    def decide(self) -> None:
        """The final call: an illegal piece is a forced revise (code); otherwise the Producer's
        accept | ONE revision plan stands."""
        st = self.state
        assert (st.ustad is not None and st.rasik is not None and st.producer is not None
                and st.composition is not None and st.arrangement is not None)
        plan, events = self._stages.decide(st.ustad, st.rasik, st.producer, st.composition,
                                           st.arrangement)
        st.plan = plan
        st.decision = "revise" if plan is not None else "accept"
        publish_all(events)
        st.events.extend(events)

    @router(decide)
    def route(self) -> str:
        """The terminator: accept, or revise until the round cap — then done, always."""
        st = self.state
        if st.plan is None:
            return "done"
        if self._stalled():
            stalled = _flow_event("The judge asked for the same edit again and the last one did not "
                                  "raise its scores — accepting rather than paying for the same answer.")
            st.events.append(stalled)
            publish(stalled)
            return "done"
        if st.round >= self._max_rounds:
            capped = _flow_event(f"Revise cap ({self._max_rounds}) reached — accepting the last version.")
            st.events.append(capped)
            publish(capped)
            return "done"
        st.round += 1
        if self._judges_plan():
            st.asked_plan, st.asked_scores = st.plan, st.producer.scores
        revising = _flow_event(
            f"Revise round {st.round}: reworking the {st.plan.voice} — {st.plan.instruction}")
        st.events.append(revising)
        publish(revising)
        return "revise"

    def _judges_plan(self) -> bool:
        """The plan is the Producer's own (not a code-forced revise for an illegal or starved
        piece — those are physical faults and keep their rounds up to the cap)."""
        st = self.state
        return st.producer is not None and st.plan is not None and st.plan == st.producer.plan

    def _stalled(self) -> bool:
        """The STOP RULE (`revision.is_stalled`): the judge's same edit, asked again, unimproved."""
        st = self.state
        if not self._judges_plan() or st.arrangement is None:
            return False
        assert st.plan is not None and st.producer is not None
        return is_stalled(st.arrangement, st.asked_plan, st.asked_scores, st.plan,
                          st.producer.scores)

    @listen("done")
    def finish(self) -> None:
        """Render the accepted composition to a WAV (skipped if fluidsynth is absent), and
        save the CHART beside it.

        The composition alone cannot say where a section begins, so diagnosing a finished
        render meant guessing at boundaries — "the lead vanishes for twenty beats" could not
        be attributed to a section without the arrangement (2026-09-14). Writing it costs
        nothing and makes the pair replayable and measurable with no LLM.
        """
        st = self.state
        assert st.composition is not None
        publish(_running("System", "rendering the audio…", role="system"))
        st.wav_path = self._stages.render(st.composition)
        _save_arrangement(st.wav_path, st.arrangement)
        if self._stages.listen and st.wav_path and st.arrangement is not None:
            publish(_running("Listener", "listening to the render…", role="critic"))
            heard = self._stages.listen(st.wav_path, st.arrangement)
            publish_all(heard)
            st.events.extend(heard)


def _compose_beat() -> DebateEvent:
    """The RUNNING beat before the chart is written — names whoever actually writes it."""
    from crew.config import composer_enabled
    if composer_enabled():
        return _running("Composer", "writing the core idea — riff, hook and form…", role="composer")
    return _running("Pandit", "negotiating the chart with Riffsmith…", role="composer")


def _listen(wav_path: str, arr: Arrangement) -> list[DebateEvent]:
    """The real listening stage: measure each section's loudness, let the audio judge listen
    (blind to the score), cross-check what it says against the measurements and the chart, and
    save the report beside the WAV. ADVISORY and never fatal: a failed listen is a note, not a
    failed run."""
    from crew.listening import GeminiAudioJudge, cross_check, listen, render_listening
    from crew.loudness import measure_sections, render_arc
    wav = Path(wav_path)
    try:
        arc = measure_sections(wav, arr)
        report = listen(wav, arr, client=GeminiAudioJudge())
        check = cross_check(report, arr, arc)
    except Exception as exc:  # noqa: BLE001 — a diagnostic must not fail a finished run
        return [DebateEvent(type=EventType.INFO, agent="Listener", role="critic",
                            text=f"listening pass skipped: {exc}")]
    text = render_listening(report, check) + "\n" + render_arc(arc)
    _save_beside(wav, ".listening.json", report.model_dump_json(indent=2))
    return [DebateEvent(type=EventType.CRITIQUE, agent="Listener", role="critic", text=text,
                        data={"advisory": True, "consistency": check.consistency,
                              "report": report.model_dump()})]


def _save_beside(wav: Path, suffix: str, content: str) -> None:
    """Write a diagnostic next to a render; never fatal."""
    try:
        wav.with_suffix("").with_suffix(suffix).write_text(content)
    except OSError:
        pass


def _save_arrangement(wav_path: Optional[str], arrangement: Optional[Arrangement]) -> None:
    """Write the chart next to a rendered WAV. Silent when there is no render (a test or a
    machine without fluidsynth) and never fatal: a diagnostic must not fail a finished run."""
    if not wav_path or arrangement is None:
        return
    try:
        path = Path(wav_path).with_suffix("").with_suffix(".arrangement.json")
        path.write_text(arrangement.model_dump_json(exclude_none=True, indent=2))
    except OSError:
        pass


def compose_flow(query: str, *, stages: Optional[Stages] = None,
                 max_rounds: int = MAX_ROUNDS) -> ComposeState:
    """Run the full pipeline as a Flow and return its final state (composition, the
    event stream, the final decision, the rendered WAV path). `stages` is injectable —
    defaults to the real adapters."""
    flow = ComposeFlow(stages or production_stages(), max_rounds=max_rounds)
    flow.kickoff(inputs={"query": query})
    return flow.state


# --------------------------------------------------------------------------- #
# Entry point — a BOUNDED live run: a fixed small chart (so interpret/composers  #
# aren't re-billed — already confirmed), real generate/critique/decide/render.   #
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
    print(f"\nfinal decision: {state.decision or '?'} (after {state.round} revise round(s))")
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
