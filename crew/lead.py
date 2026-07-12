"""
The Lead generator (step 4, generator #1) — the raga melodic voice.

Reads the shared Arrangement chart and, for each section where `lead` is active,
asks the LLM for ONE phrase (a `LeadPhrase`), then lays it onto that section's
window in the lead's register. The pattern on show: STRUCTURED GENERATION +
VALIDATION AT THE BOUNDARY — the same shape as the composers, but producing NOTES
now, not a plan.

The split the whole project preaches, applied to a generator:
  * the LLM supplies the MUSIC — which swaras, how long, which kan/meend — the part
    that is taste and idiom;
  * CODE owns the CHECKABLE — it places the phrase on the beat grid in the right
    register (`place_phrase`), and the legality guardrail (`validate_composition`'s
    core) bounces any out-of-raga swara back for one bounded retry.

Layering (pure core / imperative shell, as in composers.py):
  * pure          — `place_phrase`, the fact->prompt renderers, and `generate_lead`
                    (control flow over an injected `gen_fn`, so the loop tests with
                    no LLM);
  * imperative    — `_LeadCrew` / `_LLMLead` make the Gemini calls; `main` renders.

Entry point (ONE live LLM call — the lead over a bare drone):
  uv run python -m crew.lead
"""

from __future__ import annotations

import shutil
import sys
from collections.abc import Callable
from enum import Enum
from pathlib import Path
from typing import Any, Final

import yaml
from crewai import Agent, Crew, Process, Task
from pydantic import ValidationError

from crew.config import GENERATOR_MAX_ITER, GENERATOR_RETRIES, generator_llm, load_env
from crew.contracts import (
    Arrangement,
    DebateEvent,
    EventStream,
    EventType,
    Layer,
    LeadNote,
    LeadPhrase,
    Note,
    SectionKind,
    motif_illegal_in_raga,
)
from crew.generators import (
    VOICES,
    SectionSpan,
    assemble_composition,
    drone_layer,
    render_composition,
    section_spans,
)
from raga import RAGAS, scale_step_up, validate_composition

_LEAD_ROLE: Final = "lead"                 # the layer role this generator fills
_ROLE_GENERATOR: Final = "generator"       # DebateEvent role for a generator step

_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
_SOUNDFONT: Final[Path] = _ROOT / "soundfonts" / "MuseScore_General.sf3"
_OUT_DIR: Final[Path] = _ROOT / "out"

# The exact JSON shape we want back, injected as an input so CrewAI's {placeholder}
# interpolation never has to parse these literal braces (same trick as composers).
_OUTPUT_SCHEMA: Final = """{
  "reasoning": "the pakad/chalan idiom you build on and how you shape it to this section",
  "notes": [
    {"swara": "d", "oct": -1, "dur": 2.0, "vel": 80},
    {"swara": "g", "oct": 0, "dur": 1.5, "grace": ["S"], "meend": "m"},
    {"swara": "m", "oct": 0, "dur": 4.0, "meend": {"swara": "S", "oct": 1}}
  ]
}
"reasoning" comes FIRST. "oct" is your octave (0 = home; -1 mandra/lower, +1 taar/upper).
"vel", "grace" and "meend" are optional. "meend" is a swara to glide to within the same
octave, OR {"swara","oct"} to glide ACROSS octaves (that "oct" is in the same frame as a
note's "oct"). Durations are in beats and must be positive."""


# --------------------------------------------------------------------------- #
# Placement: LLM phrase -> notes on the section's window. Pure.                #
# --------------------------------------------------------------------------- #

def place_phrase(notes: list[LeadNote], *, start: float, end: float,
                 register: int) -> list[Note]:
    """Lay a phrase's notes end-to-end from `start`, seat them in `register`, and
    TRUNCATE at `end` so the lead never spills past its section window.

    The "code enforces" half of the split: the LLM aims for the window length, but
    code guarantees the phrase stays inside it and in the right octave. Each note's
    absolute octave is the lead's register plus the note's LOCAL octave; a straddling
    final note is clipped to the window edge; notes beyond it are dropped.
    """
    placed: list[Note] = []
    t = start
    for ln in notes:
        if t >= end:
            break
        dur = min(ln.dur, end - t)          # clip the note that straddles the edge
        placed.append(Note(swara=ln.swara, oct=register + ln.oct, start=round(t, 4),
                           dur=round(dur, 4), vel=ln.vel, grace=ln.grace,
                           meend=_place_meend(ln, register)))
        t += ln.dur
    return placed


def _place_meend(ln: LeadNote, register: int):
    """Register-shift a cross-octave meend target; leave a same-octave one alone.

    A `{"swara","oct"}` meend carries a LOCAL octave (same frame as the note); it is
    shifted into the absolute octave the renderer expects, exactly as the note's own
    octave is. A bare-string meend needs no shift — the renderer glides to it in the
    note's octave (already register-seated). Returns None when there is no meend.
    """
    meend = ln.meend
    if isinstance(meend, dict):
        return {"swara": meend["swara"], "oct": register + meend.get("oct", ln.oct)}
    return meend


# --------------------------------------------------------------------------- #
# Voicing: render ONE melodic line as sitar and/or lead guitar. Pure.          #
# The Lead generator writes one line per section; the voicing decides which     #
# timbre(s) play it and whether the guitar harmonizes — a texture choice keyed   #
# to the section kind (an alaap sings on sitar; a taan is a harmonized shred).   #
# --------------------------------------------------------------------------- #

class Voicing(Enum):
    """How a section's lead line is voiced across sitar and lead guitar."""
    SITAR = "sitar"          # solo sitar — the raga voice
    GUITAR = "guitar"        # solo lead guitar — the metal shred voice
    UNISON = "unison"        # both, the same line (thickened)
    OCTAVE = "octave"        # both, an octave apart
    THIRD = "third"          # both, a raga-diatonic third apart (harmonized)


# Default voicing per section kind: the raga-idiom sections sing on sitar, the
# virtuosic metal sections move to (harmonized) lead guitar. A sensible default,
# not a law — a section could carry its own voicing hint later.
_VOICING_BY_KIND: Final[dict[SectionKind, Voicing]] = {
    SectionKind.ALAAP: Voicing.SITAR,
    SectionKind.MELODY: Voicing.UNISON,
    SectionKind.TAAN: Voicing.THIRD,
    SectionKind.SOLO: Voicing.GUITAR,
    SectionKind.BREAKDOWN: Voicing.GUITAR,
    SectionKind.OUTRO: Voicing.SITAR,
    SectionKind.RIFF: Voicing.SITAR,
}


def _voicing_for(kind: SectionKind) -> Voicing:
    return _VOICING_BY_KIND.get(kind, Voicing.SITAR)


def _harmony_note(base: Note, swara: str, octave: int) -> Note:
    """A clean harmony note taken from a base note — NO kan/meend (the ornaments live
    on the melody line; doubling them on the harmony would clash)."""
    return Note(swara=swara, oct=octave, start=base.start, dur=base.dur, vel=base.vel)


def _voice_line(line: list[Note], voicing: Voicing, raga: str) -> tuple[list[Note], list[Note]]:
    """Split one melodic line into (sitar_notes, guitar_notes) per the voicing.

    Harmony is computed IN THE RAGA — octave = the same swara one octave up; third =
    two scale-degrees up the raga's ladder (`scale_step_up`) — so every harmony note
    is legal by construction. Unison copies the line verbatim (ornaments and all);
    octave and third strip ornaments for a clean double.
    """
    if voicing is Voicing.SITAR:
        return line, []
    if voicing is Voicing.GUITAR:
        return [], line
    if voicing is Voicing.UNISON:
        return line, [n.model_copy() for n in line]
    if voicing is Voicing.OCTAVE:
        return line, [_harmony_note(n, n.swara, n.oct + 1) for n in line]
    if voicing is Voicing.THIRD:
        harmony: list[Note] = []
        for n in line:
            swara, octave_delta = scale_step_up(n.swara, raga, 2)
            harmony.append(_harmony_note(n, swara, n.oct + octave_delta))
        return line, harmony
    raise ValueError(f"unknown voicing {voicing!r}")


# --------------------------------------------------------------------------- #
# Facts -> prompt text. Pure. (Shares shape with composers' raga renderer; when #
# the Riff generator lands as the third user, extract a shared fact-renderer.)  #
# --------------------------------------------------------------------------- #

def _render_raga_facts(raga: str) -> str:
    """The raga's facts the lead composes from — the single source of truth."""
    r = RAGAS[raga]
    lines = [
        f"  {r['display']} ({r['western_mode']}) — allowed swaras: {' '.join(r['allowed'])}",
        f"  aroha: {' '.join(r['aroha'])}   avaroha: {' '.join(r['avaroha'])}",
        f"  vadi {r['vadi']}, samvadi {r['samvadi']}",
        f"  pakad: {' | '.join(' '.join(p) for p in r['pakad'])}",
        f"  chalan: {' | '.join(' '.join(p) for p in r['chalan'])}",
    ]
    if r.get("andolan"):
        lines.append(f"  andolan (oscillate these — idiomatic): {' '.join(r['andolan'])}")
    if r.get("kan"):
        kan = "; ".join(f"{sw}: kan {v['aroha']} ascending, {v['avaroha']} descending"
                        for sw, v in r["kan"].items())
        lines.append(f"  kan conventions: {kan}")
    return "\n".join(lines)


class _LeadContext:
    """Assembles a lead turn's prompt inputs. The piece-level facts (raga, motif,
    register, tempo) are CONSTANT across a run, so they render once; only the
    per-section fields change. Pure — no I/O."""

    def __init__(self, arr: Arrangement) -> None:
        from subgenres import SUBGENRES
        self._static: dict[str, Any] = {
            "raga_block": _render_raga_facts(arr.raga),
            "motif": " ".join(arr.motif),
            "subgenre_feel": SUBGENRES[arr.subgenre]["feel"],
            "bpm": arr.bpm,
            "output_schema": _OUTPUT_SCHEMA,
        }

    def inputs_for(self, span: SectionSpan) -> dict[str, Any]:
        section = span.section
        return {
            **self._static,
            "section_kind": section.kind.value,
            "section_intent": section.intent or "(none given — use your judgment for this kind)",
            "window_beats": f"{span.length:g}",
        }


# --------------------------------------------------------------------------- #
# Boundary parsing + the legality guardrail (the hard line). Imperative-ish.   #
# --------------------------------------------------------------------------- #

def _phrase_from_output(output: Any) -> LeadPhrase | None:
    """The LeadPhrase CrewAI parsed via output_pydantic (or None if parsing failed)."""
    parsed = getattr(output, "pydantic", None)
    if isinstance(parsed, LeadPhrase):
        return parsed
    raw = getattr(output, "raw", None)
    try:
        return LeadPhrase.model_validate_json(raw) if raw else None
    except ValidationError:
        return None


def _phrase_swaras(phrase: LeadPhrase) -> list[str]:
    """Every swara the phrase actually sounds — the note, its kan, its meend target
    — flattened so the raga grammar can judge them all (no ornament blind spot)."""
    swaras: list[str] = []
    for note in phrase.notes:
        swaras.append(note.swara)
        swaras.extend(note.grace or [])
        if note.meend is not None:
            swaras.append(note.meend["swara"] if isinstance(note.meend, dict) else note.meend)
    return swaras


def _lead_guardrail(raga: str):
    """Build the Task guardrail for a given raga: the ONE domain rule — every swara
    the phrase sounds must be legal in the raga. `output_pydantic` guarantees the
    SHAPE; this checks the grammar and, on a violation, returns the precise error so
    CrewAI re-runs the section (a bounded retry, not a loop).

    Contract: returns (True, LeadPhrase) or (False, error-message). CrewAI reads the
    guardrail's RETURN ANNOTATION and requires the literal object tuple[bool, Any];
    `from __future__ import annotations` would stringify a normal hint, so it is set
    as a real object on the closure below.
    """
    def guard(output: Any):
        phrase = _phrase_from_output(output)
        if phrase is None:
            return (False, "Return a single valid LeadPhrase JSON object and nothing else.")
        illegal = motif_illegal_in_raga(_phrase_swaras(phrase), raga)
        if illegal:
            allowed = " ".join(RAGAS[raga]["allowed"])
            return (False, f"swaras {sorted(set(illegal))} are illegal in raga {raga}. "
                           f"Use only these swaras: {allowed}. Fix and resend.")
        return (True, phrase)

    guard.__annotations__["return"] = tuple[bool, Any]
    return guard


class _LeadCrew:
    """Runs ONE section's lead generation as an isolated single-agent crew.

    Config is read once at construction; each call builds the per-section task with
    the raga-bound guardrail. Structured output is CrewAI's job (`output_pydantic`),
    so there is no hand-rolled JSON parsing beyond the defensive fallback.
    """

    def __init__(self) -> None:
        config_dir = Path(__file__).parent / "config"
        self._agent_config = yaml.safe_load((config_dir / "agents.yaml").read_text())["lead"]
        self._task_config = yaml.safe_load((config_dir / "tasks.yaml").read_text())["generate_lead"]

    def run(self, raga: str, inputs: dict[str, Any]) -> LeadPhrase:
        agent = Agent(config=self._agent_config, llm=generator_llm(),
                      allow_delegation=False, max_iter=GENERATOR_MAX_ITER, verbose=False)
        task = Task(config=self._task_config, agent=agent, output_pydantic=LeadPhrase,
                    guardrail=_lead_guardrail(raga), guardrail_max_retries=GENERATOR_RETRIES)
        crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)
        phrase = _phrase_from_output(crew.kickoff(inputs=inputs))
        if phrase is None:
            raise ValueError("lead generator returned no parseable LeadPhrase")
        return phrase


# A phrase provider: given a section span and the chart, return its lead phrase.
type LeadFn = Callable[[SectionSpan, Arrangement], LeadPhrase]


class _LLMLead:
    """The real (LLM-backed) `gen_fn` — holds the crew and the precomputed context."""

    def __init__(self, arr: Arrangement) -> None:
        self._crew = _LeadCrew()
        self._context = _LeadContext(arr)

    def __call__(self, span: SectionSpan, arr: Arrangement) -> LeadPhrase:
        return self._crew.run(arr.raga, self._context.inputs_for(span))


# --------------------------------------------------------------------------- #
# The generator loop — pure control flow, LLM injected via `gen_fn`.           #
# --------------------------------------------------------------------------- #

def _lead_event(span: SectionSpan, phrase: LeadPhrase, line: list[Note],
                voicing: Voicing) -> DebateEvent:
    return DebateEvent(
        type=EventType.PROPOSE, agent="Lead", role=_ROLE_GENERATOR,
        text=f"{span.section.kind.value}: {len(line)} notes over {span.length:g} beats "
             f"[{voicing.value}]",
        data={"reasoning": phrase.reasoning, "voicing": voicing.value,
              "swaras": [n.swara for n in line]})


def _lead_layer(voice_name: str, notes: list[Note]) -> Layer:
    """Build a lead Layer for one timbre (sitar or lead_guitar). Both carry the
    `lead` role; the patch, channel, and pan differ (sitar left / lead guitar right,
    so a harmonized third separates across the stereo field)."""
    voice = VOICES[voice_name]
    return Layer(role=_LEAD_ROLE, instrument=voice.instrument, program=voice.program,
                 channel=voice.channel, pan=voice.pan, notes=notes)


def generate_lead(arr: Arrangement, *, gen_fn: LeadFn) -> tuple[list[Layer], list[DebateEvent]]:
    """Fill the lead across the arrangement's lead-active sections, VOICED.

    For each section that lists `lead`: get a phrase from `gen_fn`, place it as ONE
    melodic line, then VOICE it per the section kind (solo sitar, solo lead guitar,
    unison, octave, or a raga-diatonic third) into a sitar line and/or a lead-guitar
    line. Returns up to TWO layers — a sitar layer and a lead-guitar layer — and an
    empty list when no section uses the lead. `gen_fn` is injected so this loop is
    tested with no LLM.
    """
    events: list[DebateEvent] = []
    sitar_notes: list[Note] = []
    guitar_notes: list[Note] = []
    for span in section_spans(arr):
        if _LEAD_ROLE not in span.section.layers:
            continue
        phrase = gen_fn(span, arr)
        line = place_phrase(phrase.notes, start=span.start, end=span.end,
                            register=arr.registers[_LEAD_ROLE])
        voicing = _voicing_for(span.section.kind)
        sitar_line, guitar_line = _voice_line(line, voicing, arr.raga)
        sitar_notes.extend(sitar_line)
        guitar_notes.extend(guitar_line)
        events.append(_lead_event(span, phrase, line, voicing))

    layers: list[Layer] = []
    if sitar_notes:
        layers.append(_lead_layer("sitar", sitar_notes))
    if guitar_notes:
        layers.append(_lead_layer("lead_guitar", guitar_notes))
    if not layers:
        events.append(DebateEvent(type=EventType.INFO, agent="Lead", role=_ROLE_GENERATOR,
                                  text="no lead-active sections in this arrangement"))
    return layers, events


def compose_lead(arr: Arrangement) -> tuple[list[Layer], list[DebateEvent]]:
    """Run the real (LLM-backed) lead generation for a chart."""
    return generate_lead(arr, gen_fn=_LLMLead(arr))


# --------------------------------------------------------------------------- #
# The imperative edge — a single live confirmation: lead over a bare drone.    #
# --------------------------------------------------------------------------- #

def _lead_demo_arrangement() -> Arrangement:
    """A one-section chart (lead + drone) so the live confirmation is ONE LLM call.

    A harmonized TAAN in Darbari on purpose: a taan maps to the THIRD voicing, and
    Darbari is a seven-note raga, so the diatonic third is clean — the confirmation
    shows the lead voiced as sitar + lead guitar a raga-third apart. Built through the
    real composer contract (no LLM here).
    """
    from crew.contracts import ArrangementDraft, CompositionBrief, Section, SectionKind, build_arrangement
    draft = ArrangementDraft(
        raga="darbari", subgenre="thrash", tala="teentaal", bpm=180,
        motif=["S", "R", "g", "R", "g", "m", "P"],
        sections=[Section(kind=SectionKind.TAAN, bars=1, layers=["lead", "drone"],
                          foreground="lead",
                          intent="a fast virtuosic taan climbing toward the taar")],
    )
    return build_arrangement(draft, CompositionBrief(mood="dark"))


def _run() -> None:
    arr = _lead_demo_arrangement()
    stream = EventStream()
    lead_layers, events = compose_lead(arr)
    for event in events:
        stream.emit(event)

    layers = [drone_layer(arr)] + lead_layers
    comp = assemble_composition(arr, layers)
    payload = comp.model_dump(exclude_none=True)
    violations = validate_composition(payload)
    print(f"lead+drone composition ({len(layers)} layers): {len(violations)} grammar violation(s)")

    if shutil.which("fluidsynth") and _SOUNDFONT.exists():
        wav = render_composition(comp, out_dir=_OUT_DIR, name="lead_taan", soundfont=_SOUNDFONT)
        print(f"-> rendered {wav.relative_to(_ROOT)}")
    else:
        print("-> render skipped (fluidsynth or soundfont not found)")


def main(argv: list[str]) -> int:
    load_env()  # entry point loads .env
    # Trace by default — every live run is captured for the portal (RMA_TRACE=0 opts out).
    from contextlib import nullcontext

    from crew.tracing import traced, tracing_enabled
    ctx = traced("lead-demo") if tracing_enabled() else nullcontext()
    with ctx:
        _run()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
