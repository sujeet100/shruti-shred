"""
The single COMPOSER — one musician owns the music (DESIGN.md "THE REDESIGN", steps 2-3).

The evidence: one bare model call, writing the sitar, guitar, bass and drums together, beat the
multi-agent pipeline on riffs and climax (talk/HANDOVER.md §2). The riff, the hook and the form
are ONE idea; splitting them across Pandit⇄Riffsmith, a gat composer, a lead generator and a riff
generator fragmented it. So on this path:

  * SEED — ONE call (`compose_seed`) co-writes the chart (form, sections, motif, anchor, ending),
    the MAIN RIFF (one cycle of the slot that recurs), the sitar's part and the energy arc, in one
    context. The sitar's part is the HOOK in the song form (one avartan over the main riff) and only
    the gat HEAD'S IDEA in the gat form (sam swara, core cell, stroke line — `HeadIdea`): the head is
    the piece's most important object, so the gat call composes its notes with full attention
    (Sujit's Option A, 2026-10-12) instead of copying a head written as a fifth of this JSON. Code
    holds it to the same HARD lines as everything else — the chart's form rules and length budget,
    the riff's grammar and physical checks, the hook's grammar and the mukhada's hard checks, and
    in a riff_first piece the hook's quote of the riff — with a bounded retry.
  * DEVELOP — the existing generator loops (verified cells, placement, riff family, voicing) run
    around the seed instead of from scratch: the main riff slot IS the seed riff, the mukhada (or
    the song's recurring hook) IS the seed hook, and every other section is composed by the SAME
    `composer` persona, shown the whole seed (`{song_seed}` — "develop it, never replace it").
  * The seeds ride the Arrangement (`seed_riff`, `seed_hook`, `energy_arc`), so a revise hands them on.

The default path since 2026-10-18 (`RMA_COMPOSER=0` restores the legacy composers). The studio session
is not used on this path — ownership is the point. The LLM is injected everywhere, so every loop
here is tested with no key.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

import yaml

from crew.anchor import main_riff_slot, riff_accents
from crew.composers import brief_budget, chart_facts, chart_schema, draft_error
from crew.contracts import (
    Arrangement,
    CompositionBrief,
    DebateEvent,
    EventType,
    HeadIdea,
    Layer,
    LeadPhrase,
    RiffPattern,
    SongSeed,
    build_arrangement,
)
from crew.gat_verifier import check_mukhada, verify_riff_quote
from crew.riff_texture import verify_riff
from crew.riff_voicing import home_root, render_power_roots
from raga import RAGAS

_TASK: Final = "compose_seed"
_AGENT: Final = "composer"
_ROLE: Final = "composer"
_AGENT_NAME: Final = "Composer"


# --------------------------------------------------------------------------- #
# The seed prompt's facts. Pure.                                               #
# --------------------------------------------------------------------------- #

def _riff_palette_line(raga: str) -> str:
    from crew.riff import render_half_steps
    half = render_half_steps(raga).strip().split(" — ")[0]
    return (f"  {raga}: home root {home_root(raga)}; half-step neighbours {half}; "
            f"{render_power_roots(raga).strip()}")


def render_riff_palette(brief: CompositionBrief) -> str:
    """Each candidate raga's riff vocabulary — home root, half-step neighbours (the one-fret
    grind), which roots carry a full power chord — for the raga the brief fixes, else every
    raga on the menu (the Composer may pick). Pure."""
    ragas = [brief.raga] if brief.raga else sorted(RAGAS)
    return "\n".join(_riff_palette_line(r) for r in ragas)


# The gat head's IDEA as the seed prompt shows it (a `HeadIdea`). No notes: the gat call writes them.
_HEAD_SCHEMA: Final = """{
  "idea": "<one line: what this head is>",
  "sam_swara": "<the swara that sounds ON every sam — the head's first note>",
  "cell": ["<the few swaras of the core cell that recurs>"],
  "stroke_line": ["<one stroke token per matra of the avartan: a bol word or - (no chikari)>"]
}"""


class SeedContext:
    """The seed call's inputs: the brief-derived chart facts the composers always saw, plus the
    riff palette and the three output shapes (chart, riff cycle, lead phrase). Pure."""

    def __init__(self, brief: CompositionBrief, approach: str = "") -> None:
        from crew.lead import phrase_schema, render_seed_strokes
        from crew.riff import riff_schema
        self._inputs: dict[str, Any] = {
            **chart_facts(brief),
            "riff_palette": render_riff_palette(brief),
            "gat_strokes": render_seed_strokes(brief.bpm),
            "approach": approach or "none set — follow the idea wherever it starts",
            "chart_schema": chart_schema(),
            "riff_schema": riff_schema(),
            "phrase_schema": phrase_schema(),
            "head_schema": _HEAD_SCHEMA,
        }

    def inputs(self) -> dict[str, Any]:
        return dict(self._inputs)


# --------------------------------------------------------------------------- #
# The seed guardrail — the HARD lines, nothing else. Pure.                    #
# --------------------------------------------------------------------------- #

def _chart_error(seed: SongSeed, brief: CompositionBrief) -> str | None:
    if brief.raga and seed.chart.raga != brief.raga:
        return (f"the raga is FIXED as {brief.raga}, but the chart says {seed.chart.raga} — the "
                f"riff and the hook must be written in {brief.raga}")
    error = draft_error(seed.chart, brief_budget(brief))
    return f"in the chart: {error}" if error else None


def _riff_errors(riff: RiffPattern, arr: Arrangement) -> list[str]:
    from crew.riff import riff_grammar_error
    if main_riff_slot(arr) is None:
        return ["the chart has no rhythm section, so the main riff has nowhere to play"]
    grammar = riff_grammar_error(riff, arr.raga)
    errors = [grammar] if grammar else []
    return [f"in the main riff: {e}" for e in errors + verify_riff(riff, cycle_beats=arr.beats_per_bar)]


def _head_errors(head: HeadIdea, arr: Arrangement) -> list[str]:
    """The gat head's IDEA held to the one real constraint it can break: every swara in the raga.
    Whether the composed head keeps it is measured later (`check_head_idea`), never enforced here."""
    allowed = set(RAGAS[arr.raga]["allowed"])
    bad = sorted({sw for sw in [head.sam_swara, *head.cell] if sw not in allowed})
    return ([f"in the head: {' '.join(bad)} not in {arr.raga} (allowed: "
             f"{' '.join(RAGAS[arr.raga]['allowed'])})"] if bad else [])


def _sitar_errors(seed: SongSeed, arr: Arrangement) -> list[str]:
    """The sitar's part by form: the gat form writes the head's IDEA (its notes are the gat call's),
    the song form a finished hook over the main riff."""
    if arr.form == "gat":
        if seed.head is None:
            return ["in the gat form, write `head` — the gat head's IDEA (sam_swara, cell, "
                    "stroke_line); the gat composer writes its notes"]
        return _head_errors(seed.head, arr)
    if seed.hook is None:
        return ["in the song form, write `hook` — one avartan the sitar sings over the main riff"]
    return _hook_errors(seed.hook, seed.main_riff, arr)


def _hook_errors(hook: LeadPhrase, riff: RiffPattern, arr: Arrangement) -> list[str]:
    from crew.lead import phrase_grammar_error
    grammar = phrase_grammar_error(hook, arr.raga)
    errors = [grammar] if grammar else []
    errors += list(check_mukhada(hook, cycle_beats=arr.beats_per_bar, raga=arr.raga).hard)
    if arr.anchor == "riff_first":
        errors += verify_riff_quote(hook, riff_accents(riff, arr))
    return [f"in the hook: {e}" for e in errors]


def seed_errors(seed: SongSeed, brief: CompositionBrief) -> list[str]:
    """Every HARD fault of a seed, as retry messages (empty == a usable seed). The chart is held to
    the composers' form rules and length budget; the main riff to its raga grammar and the
    physical riff checks; a song-form hook to the lead grammar and the mukhada's hard checks (it
    fills one avartan, cadences, loops) and in a riff_first piece to quoting the riff; a gat-form
    head idea to the raga (its composed head meets the mukhada checks and the quote in the gat
    call). Craft is never a reason to reject — the riff's texture and the head's style stay the
    Composer's call."""
    chart = _chart_error(seed, brief)
    if chart:
        return [chart]                      # the riff and hook are judged against a valid chart
    arr = build_arrangement(seed.chart, brief)
    return _riff_errors(seed.main_riff, arr) + _sitar_errors(seed, arr)


def _seed_from_output(output: Any) -> SongSeed | None:
    parsed = getattr(output, "pydantic", None)
    if isinstance(parsed, SongSeed):
        return parsed
    raw = getattr(output, "raw", None)
    try:
        return SongSeed.model_validate_json(raw) if raw else None
    except ValueError:
        return None


def seed_guardrail(brief: CompositionBrief) -> Callable[[Any], Any]:
    """The seed Task guardrail bound to one brief: (True, SongSeed) or (False, the faults). The
    return annotation is attached as a real object (CrewAI rejects a stringified hint)."""
    def guardrail(output: Any):
        seed = _seed_from_output(output)
        if seed is None:
            return (False, "Return a single valid SongSeed JSON object and nothing else.")
        errors = seed_errors(seed, brief)
        return (False, "; ".join(errors) + ". Fix and resend.") if errors else (True, seed)
    guardrail.__annotations__["return"] = tuple[bool, Any]
    return guardrail


# --------------------------------------------------------------------------- #
# The seed call (the imperative edge) and the seed -> chart step.             #
# --------------------------------------------------------------------------- #

type SeedFn = Callable[[CompositionBrief], SongSeed]


class _LLMSeed:
    """The real (LLM-backed) seed call — one `composer` agent, one task, the seed guardrail.
    `approach` nudges where the idea starts (the seed debate's riff-first / gat-first)."""

    def __call__(self, brief: CompositionBrief, approach: str = "") -> SongSeed:
        from crewai import Agent, Crew, Process, Task

        from crew.config import (AGENT_RETRY_LIMIT, COMPOSER_MAX_ITER, SEED_RETRIES, composer_llm,
                                 structured_output)
        config_dir = Path(__file__).parent / "config"
        agent = Agent(config=yaml.safe_load((config_dir / "agents.yaml").read_text())[_AGENT],
                      llm=composer_llm(), allow_delegation=False, max_iter=COMPOSER_MAX_ITER,
                      max_retry_limit=AGENT_RETRY_LIMIT, verbose=False)
        task = Task(config=yaml.safe_load((config_dir / "tasks.yaml").read_text())[_TASK],
                    agent=agent, **structured_output(SongSeed), guardrail=seed_guardrail(brief),
                    guardrail_max_retries=SEED_RETRIES)
        crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)
        seed = _seed_from_output(crew.kickoff(inputs=SeedContext(brief, approach).inputs()))
        if seed is None:
            raise ValueError("the Composer returned no parseable SongSeed")
        return seed


def seed_arrangement(seed: SongSeed, brief: CompositionBrief) -> Arrangement:
    """The chart the seed describes, carrying its core idea (riff, the sitar's part, energy arc):
    the gat form carries the head's IDEA and no hook, so the gat call composes the head. Pure."""
    arr = build_arrangement(seed.chart, brief)
    gat = arr.form == "gat" and seed.head is not None
    return arr.model_copy(update={"seed_riff": seed.main_riff,
                                  "seed_hook": None if gat else seed.hook,
                                  "seed_head": seed.head if gat else None,
                                  "energy_arc": seed.energy_arc})


def _seed_event(seed: SongSeed, arr: Arrangement) -> DebateEvent:
    sections = " → ".join(s.form_role or s.kind.value for s in arr.sections)
    return DebateEvent(
        type=EventType.PROPOSE, agent=_AGENT_NAME, role=_ROLE,
        text=f"the core idea: {arr.form} form in {arr.raga}, {arr.tala} @ {arr.bpm} — {sections}",
        data={"reasoning": seed.reasoning, "energy_arc": seed.energy_arc, "form": arr.form,
              "anchor": arr.anchor, "main_slot": main_riff_slot(arr),
              "main_riff": [n.swara for n in seed.main_riff.notes],
              "hook": [n.swara for n in seed.hook.notes] if seed.hook else None,
              "head": seed.head.model_dump() if seed.head else None})


def compose_seed(brief: CompositionBrief, *,
                 seed_fn: SeedFn | None = None) -> tuple[Arrangement, list[DebateEvent]]:
    """The SEED: one call writes the chart, the main riff, the hook and the energy arc together.
    `seed_fn` is injected (the LLM by default) so this is tested with no key."""
    seed = (seed_fn or _LLMSeed())(brief)
    arr = seed_arrangement(seed, brief)
    return arr, [_seed_event(seed, arr)]


# --------------------------------------------------------------------------- #
# DEVELOP — the existing generators, around the seed.                         #
# --------------------------------------------------------------------------- #

type LeadDevelop = Callable[[Arrangement], tuple[list[Layer], list[DebateEvent]]]
type RiffDevelop = Callable[[Arrangement], tuple[Layer | None, list[DebateEvent]]]


def _quiet(agent: str, text: str) -> None:
    """The default `announce` — nothing to stream outside the Flow."""


def _keep(events: list[DebateEvent]) -> None:
    """The default `emit` — the events are returned anyway."""


def compose_seeded_voices(
        arr: Arrangement, *, lead_fn: LeadDevelop | None = None, riff_fn: RiffDevelop | None = None,
        announce: Callable[[str, str], None] = _quiet,
        emit: Callable[[list[DebateEvent]], None] = _keep,
) -> tuple[list[Layer], Layer | None, list[DebateEvent]]:
    """DEVELOP the seed into the two creative voices — the main riff slot IS the seed riff, the
    mukhada / recurring hook IS the seed hook, the rest is composed by the same `composer` persona
    shown the whole seed. When the seed holds a finished hook neither voice waits on the other. When
    it holds only the gat head's IDEA, the lead goes FIRST — the gat call composes the head — and the
    riff is handed the realized head (`with_realized_seeds`), so a gat_first riff still reduces it.
    Returns (lead_layers, rhythm, events)."""
    from crew.anchor import with_realized_seeds
    from crew.lead import compose_seeded_lead
    from crew.riff import compose_seeded_riff
    if arr.seed_hook is None and arr.seed_head is not None:
        announce(_AGENT_NAME, "composing the gat head from its idea…")
        lead_layers, lead_events = (lead_fn or compose_seeded_lead)(arr)
        emit(lead_events)
        announce(_AGENT_NAME, "developing the riff around the seed…")
        rhythm, riff_events = (riff_fn or compose_seeded_riff)(with_realized_seeds(arr, lead_events))
        emit(riff_events)
        return lead_layers, rhythm, [*lead_events, *riff_events]
    announce(_AGENT_NAME, "developing the riff around the seed…")
    rhythm, riff_events = (riff_fn or compose_seeded_riff)(arr)
    emit(riff_events)
    announce(_AGENT_NAME, "developing the melody around the hook…")
    lead_layers, lead_events = (lead_fn or compose_seeded_lead)(arr)
    emit(lead_events)
    return lead_layers, rhythm, [*riff_events, *lead_events]
