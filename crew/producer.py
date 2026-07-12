"""
Producer (agent #7) — the COMPOSITION-QUALITY critic. The third critic dimension.

The insight this agent fixes (Sujit, 2026-07-12): there are THREE different questions
about a piece of music, and Rasik was answering two of them at once.

  1. Is it LEGAL?                 -> Ustad  (code decides, LLM narrates)
  2. Does it sound like the RAGA? -> Rasik  (raga authenticity — LLM judges)
  3. Does it WORK AS A SONG?      -> Producer (composition quality — LLM judges)

So the Producer is RAGA-AGNOSTIC: it does not care whether it is Malkauns or Yaman, only
whether the arrangement holds together as music. It owns the songwriting/arrangement
questions nobody checked while Rasik was overloaded — an 8-criterion 1-5 rubric
(`ProducerScores`): structure, dynamics, climax, motif, hook, balance, independence,
mood_fit. Same LLM-as-judge discipline as Rasik: a fixed bounded rubric, a per-criterion
justification (reasoning FIRST), and grounding in the actual piece — here the whole
symbolic score (the section timeline, the motif, the riff, the lead, the ensemble),
NOT just the lead. (Chunk B will add code-computed metrics — motif similarity, active
voices per section, register overlap, the dynamics curve — as grounding facts the
Producer reasons over. "Code measures, the LLM evaluates.")

Unlike Rasik (which judges a `Composition`), the Producer needs the `Arrangement` too —
the chart is the score a musical director reads: which sections, in what order, with the
motif and the subgenre's intended feel. So `critique_composition(comp, arr)`.

Layering follows the repo's pure-core / imperative-shell split:
  * pure       — `assess` over an injected `judge_fn`; the `_render_*` helpers.
  * imperative — `_ProducerCrew` / `_LLMDirector` make the actual Gemini call.

Entry point (a single, cheap live call on a tiny two-section piece):
  uv run python -m crew.producer
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

import yaml
from crewai import Agent, Crew, Process, Task
from pydantic import ValidationError

from crew.config import CRITIC_MAX_ITER, critic_llm, load_env
from crew.contracts import (
    Arrangement,
    Composition,
    DebateEvent,
    EventType,
    ProducerVerdict,
)
from subgenres import SUBGENRES

_ROLE_CRITIC: Final = "critic"

# The exact JSON shape we want back, injected as an input so CrewAI's {placeholder}
# interpolation never has to parse these literal braces.
_RUBRIC_SCHEMA: Final = """{
  "reasoning": "criterion by criterion (structure, dynamics, climax, motif, hook, balance, independence, mood_fit): the evidence in the score that justifies each score",
  "scores": {"structure": 4, "dynamics": 3, "climax": 3, "motif": 4, "hook": 4, "balance": 3, "independence": 4, "mood_fit": 4},
  "notes": "a short 2-3 sentence critique a musician can act on"
}"""


# --------------------------------------------------------------------------- #
# Pure renderers: the SYMBOLIC SCORE -> prompt text. The Producer reads the     #
# whole arrangement (structure/motif/mood) plus the realized voices (hook/      #
# balance/independence), so it renders more of the piece than Rasik does.       #
# --------------------------------------------------------------------------- #

def _swara_with_oct(swara: str, oct_: int) -> str:
    return swara if oct_ == 0 else f"{swara}({oct_:+d})"


def _voice_notes(comp: Composition, role: str) -> list:
    """The named voice's notes in time order (empty if the voice is absent/percussive)."""
    for layer in comp.layers:
        if layer.role == role and layer.notes:
            return sorted(layer.notes, key=lambda note: note.start)
    return []


def _render_sections(arr: Arrangement) -> str:
    """The section timeline — the SHAPE of the song (for structure/dynamics/climax/mood).

    Each line names the section's role in the arc, its length, its spotlight voice, the
    voices playing (density), and the composer's intent/transition — everything the
    Producer needs to judge whether the piece BUILDS rather than sits flat."""
    lines = []
    for i, s in enumerate(arr.sections, start=1):
        bits = [f"  {i}. {s.kind.value} — {s.bars} bar(s), spotlight={s.foreground}",
                f"voices=[{', '.join(s.layers)}]"]
        if s.intent:
            bits.append(f"intent: {s.intent}")
        if s.transition:
            bits.append(f"-> {s.transition}")
        lines.append("; ".join(bits))
    return "\n".join(lines)


def _render_subgenre(arr: Arrangement) -> str:
    """The subgenre's intended feel — the target the mood_fit criterion judges against."""
    s = SUBGENRES[arr.subgenre]
    return (f"  {s['display']} at ~{arr.bpm} bpm — feel: {s['feel']}; character: {s['character']}; "
            f"subdivision: {s['subdivision']}")


def _render_riff_line(comp: Composition, arr: Arrangement) -> str:
    """One cycle of the rhythm riff, with power chords / techniques noted — for the HOOK.

    The riff loops, so only the first cycle carries information; a chord (`+P`) or a
    technique (`.palm_mute`) is what makes a riff catchy, so surface both."""
    notes = [n for n in _voice_notes(comp, "rhythm") if n.start < arr.beats_per_bar]
    if not notes:
        return "  (no rhythm riff in this piece)"
    parts = []
    for n in notes:
        tok = _swara_with_oct(n.swara, n.oct)
        if n.chord:
            tok += "+" + "+".join(n.chord)
        if n.technique:
            tok += f".{n.technique}"
        parts.append(tok)
    return "  " + " ".join(parts)


def _render_lead_line(comp: Composition) -> str:
    """The lead melody in order — for independence (lead must not merely double the riff)."""
    notes = _voice_notes(comp, "lead")
    if not notes:
        return "  (no lead voice in this piece)"
    return "  " + " ".join(_swara_with_oct(n.swara, n.oct) for n in notes)


def _render_ensemble(comp: Composition) -> str:
    """Every voice's weight and register — for balance and independence. A voice that
    plays through the whole piece crowds the mix; two voices in one octave collide.
    (The BASS deliberately shadows the riff root — that lock is idiomatic, not a fault.)"""
    lines = []
    for layer in comp.layers:
        if layer.notes:
            octs = [n.oct for n in layer.notes]
            lines.append(f"  - {layer.role}: {len(layer.notes)} notes, octaves {min(octs)}..{max(octs)}")
        elif layer.hits:
            lines.append(f"  - {layer.role}: {len(layer.hits)} hits (percussion, no pitch)")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Boundary parsing. output_pydantic targets ProducerVerdict; recover it or None #
# so the shell fails loud on an unparseable answer.                            #
# --------------------------------------------------------------------------- #

def _verdict_from_output(output: Any) -> ProducerVerdict | None:
    parsed = getattr(output, "pydantic", None)
    if isinstance(parsed, ProducerVerdict):
        return parsed
    raw = getattr(output, "raw", None)
    try:
        return ProducerVerdict.model_validate_json(raw) if raw else None
    except ValidationError:
        return None


class _ProducerCrew:
    """Runs ONE composition-quality critique as an isolated, single-agent crew. No tool:
    like Rasik, the Producer judges from the rendered score — songwriting craft is not a
    lookup. Config is read once at construction."""

    def __init__(self) -> None:
        config_dir = Path(__file__).parent / "config"
        self._agent_config = yaml.safe_load((config_dir / "agents.yaml").read_text())["producer"]
        self._task_config = yaml.safe_load((config_dir / "tasks.yaml").read_text())["assess_composition"]

    def run(self, comp: Composition, arr: Arrangement) -> ProducerVerdict:
        agent = Agent(config=self._agent_config, llm=critic_llm(),
                      allow_delegation=False, max_iter=CRITIC_MAX_ITER, verbose=False)
        task = Task(config=self._task_config, agent=agent, output_pydantic=ProducerVerdict)
        crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)
        result = crew.kickoff(inputs={
            "subgenre": SUBGENRES[arr.subgenre]["display"],
            "subgenre_facts": _render_subgenre(arr),
            "sections": _render_sections(arr),
            "motif": " ".join(arr.motif),
            "riff_line": _render_riff_line(comp, arr),
            "lead_line": _render_lead_line(comp),
            "ensemble": _render_ensemble(comp),
            "output_schema": _RUBRIC_SCHEMA,
        })
        verdict = _verdict_from_output(result)
        if verdict is None:
            raise ValueError("Producer returned no parseable ProducerVerdict")
        return verdict


# A judge provider: given the composition + its chart, return the Producer's verdict.
# Injected so `assess` is tested with no LLM.
type JudgeFn = Callable[[Composition, Arrangement], ProducerVerdict]


class _LLMDirector:
    """The real (LLM-backed) `judge_fn` — holds the crew across calls."""

    def __init__(self) -> None:
        self._crew = _ProducerCrew()

    def __call__(self, comp: Composition, arr: Arrangement) -> ProducerVerdict:
        return self._crew.run(comp, arr)


# --------------------------------------------------------------------------- #
# The critique — thin, because the verdict is the LLM's (like Rasik). We stream #
# the rubric as scores on the CRITIQUE event; the Conductor reads a low score.  #
# --------------------------------------------------------------------------- #

def _verdict_event(verdict: ProducerVerdict) -> DebateEvent:
    s = verdict.scores
    return DebateEvent(
        type=EventType.CRITIQUE, agent="Producer", role=_ROLE_CRITIC,
        text=verdict.notes,
        scores={"structure": float(s.structure), "dynamics": float(s.dynamics),
                "climax": float(s.climax), "motif": float(s.motif), "hook": float(s.hook),
                "balance": float(s.balance), "independence": float(s.independence),
                "mood_fit": float(s.mood_fit)},
        data={"reasoning": verdict.reasoning})


def assess(comp: Composition, arr: Arrangement, *,
           judge_fn: JudgeFn) -> tuple[ProducerVerdict, list[DebateEvent]]:
    """Judge a composition's craft on the fixed rubric and stream it as one CRITIQUE.

    The verdict IS the model's (songwriting quality is not checkable) — the shell only
    renders the score, wraps the result, and emits the event. `judge_fn` is injected so
    this plumbing is tested with no LLM."""
    verdict = judge_fn(comp, arr)
    return verdict, [_verdict_event(verdict)]


def critique_composition(comp: Composition, arr: Arrangement) -> tuple[ProducerVerdict, list[DebateEvent]]:
    """Run the real (LLM-backed) Producer critique on a composition + its chart."""
    return assess(comp, arr, judge_fn=_LLMDirector())


# --------------------------------------------------------------------------- #
# Entry point — a single cheap live call on a tiny two-section piece, so the    #
# Producer has a real ARC (a riff into a taan) to judge structure/climax on.    #
# --------------------------------------------------------------------------- #

def _demo_case() -> tuple[Composition, Arrangement]:
    from crew.contracts import (
        ArrangementDraft,
        CompositionBrief,
        Layer,
        Note,
        Section,
        SectionKind,
        build_arrangement,
    )
    draft = ArrangementDraft(
        raga="darbari", subgenre="doom", tala="teentaal", bpm=72,
        motif=["S", "R", "g", "m", "P"],
        sections=[
            Section(kind=SectionKind.RIFF, bars=1, layers=["rhythm", "drone"],
                    foreground="rhythm", intent="a crushing main riff", transition="lift into the taan"),
            Section(kind=SectionKind.TAAN, bars=1, layers=["lead", "rhythm", "drone"],
                    foreground="lead", intent="an expressive lead to the peak"),
        ])
    arr = build_arrangement(draft, CompositionBrief(mood="dark"))
    riff = [Note(swara="S", oct=-2, start=0.0, dur=1.0, chord=["S"], technique="palm_mute"),
            Note(swara="g", oct=-2, start=1.0, dur=1.0, technique="palm_mute")]
    lead = [Note(swara=sw, oct=0, start=float(i), dur=1.0)
            for i, sw in enumerate(["S", "R", "g", "m", "P", "m", "g", "R"])]
    comp = Composition(
        raga="darbari", sa=62, bpm=72, tala={"name": "teentaal", "beats_per_bar": 16.0},
        layers=[Layer(role="drone", notes=[Note(swara="S", oct=-2, start=0.0, dur=16.0)]),
                Layer(role="rhythm", notes=riff), Layer(role="lead", notes=lead)])
    return comp, arr


def _run() -> None:
    from crew.contracts import EventStream
    comp, arr = _demo_case()
    stream = EventStream()
    verdict, events = critique_composition(comp, arr)
    for event in events:
        stream.emit(event)
    s = verdict.scores
    print(f"\nProducer scores: structure={s.structure} dynamics={s.dynamics} climax={s.climax} "
          f"motif={s.motif} hook={s.hook} balance={s.balance} independence={s.independence} "
          f"mood_fit={s.mood_fit}")
    print(f"  notes: {verdict.notes}")


def main(argv: list[str]) -> int:
    load_env()  # entry point loads .env
    from contextlib import nullcontext

    from crew.tracing import traced, tracing_enabled
    ctx = traced("producer-demo") if tracing_enabled() else nullcontext()
    with ctx:
        _run()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
