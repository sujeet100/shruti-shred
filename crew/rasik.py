"""
Rasik — the RAGA CONSULTANT (the redesign, 2026-10-11; agent #5 before it).

The pattern on show: LLM-AS-JUDGE, and the discipline it needs. Legality is a fact, so code
owns it (crew/ustad.py); but raga authenticity — is the raga's soul present, does the line
move idiomatically, does it serve the rasa — is NOT checkable, so here the model genuinely
judges. Rasik owns exactly ONE dimension: the RAGA AUTHENTICITY OF THE MELODIC LINE, the only
evidence it is given. Since the redesign it also CONSULTS: besides the rubric it names the few
concrete phrase-level edits to the LEAD (section, change, why) that would most raise it. It no
longer debates the Producer — the Producer reads these notes and, holding the final say, may
adopt one as its revision plan. Rasik never targets the riff, the form or another voice.
LLM judges are biased (verbosity, gestalt "vibe" scoring, self-preference), and the fix is
not to take the pen away but to DISCIPLINE the judgment:

  * a FIXED 1-5 rubric with three named authenticity criteria (a bounded scale beats a vibe number);
  * scores GROUNDED in the encoded pakad/chalan/rasa facts — criteria, not vibes;
  * a code-computed pakad hint handed to the judge so its pakad score is anchored;
  * a justification required per criterion (reasoning FIRST, then the numbers).

Layering follows the repo's pure-core / imperative-shell split:
  * pure       — `assess` is control flow over an injected `judge_fn` (tested with no
                 LLM); the `_render_*`/`_pakad_presence` helpers turn facts into prompt
                 text and are unit-tested directly.
  * imperative — `_RasikCrew` / `_LLMJudge` make the actual Gemini call.

Entry point (a single, cheap live call on a tiny pakad-quoting composition):
  uv run python -m crew.rasik
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final, Literal

import yaml
from crewai import Agent, Crew, Process, Task
from pydantic import ValidationError

from crew.config import AGENT_RETRY_LIMIT, CRITIC_MAX_ITER, critic_llm, load_env, structured_output
from crew.contracts import (
    Arrangement,
    Composition,
    DebateEvent,
    EventType,
    Note,
    RasikVerdict,
)
from crew.density import render_density
from crew.lead_notation import note_token
from crew.generators import section_spans
from crew.user_request import render_request
from raga import RAGAS, SWARAS, render_character, render_kan, render_nyas, render_register

# DebateEvent role for a critic turn (shared with Ustad).
_ROLE_CRITIC: Final = "critic"

# The exact JSON shape we want back, injected as an input so CrewAI's {placeholder}
# interpolation never has to parse these literal braces.
_RUBRIC_SCHEMA: Final = """{
  "reasoning": "criterion by criterion (pakad, idiom, rasa): the evidence in the notes that justifies each score",
  "scores": {"pakad": 4, "idiom": 3, "rasa": 4},
  "notes": "a short 2-3 sentence critique a musician can act on",
  "suggestions": [
    {"section": 2, "change": "end the phrase on komal dha, held", "why": "d is the raga's resting note; the phrase ends on a passing Ga"}
  ]
}"""
_MAX_SUGGESTIONS: Final = 3       # a consultant names the few edits that matter most


# --------------------------------------------------------------------------- #
# Grounding: the deterministic pakad hint. Whether the raga's signature phrase #
# surfaces in the lead line is a fact code can compute — so we hand it to the   #
# judge to anchor the pakad score. A LITERAL contiguous quote is the strongest  #
# signal, but a real rendition threads grace/passing notes through the phrase,  #
# so a strict literal match is too brittle (one kan mid-phrase breaks it). We    #
# add a FUZZY tier — the pakad swaras in order with a bounded gap between them — #
# and fall through to ABSENT. Three states, not a bald boolean: the judge still #
# decides whether an absent pakad is EVOKED in spirit. "Ground the LLM in facts".#
# --------------------------------------------------------------------------- #

PakadMatch = Literal["literal", "fuzzy", "absent"]

# Max intervening (grace/passing) notes tolerated between consecutive pakad swaras
# in the fuzzy tier. 2 admits an ornamented rendition without letting a phrase merely
# scattered across the whole line count as present.
_MAX_PAKAD_GAP: Final = 2


def _lead_swaras(comp: Composition) -> list[str]:
    """The primary lead voice's swaras, in time order (empty if there is no lead)."""
    for layer in comp.layers:
        if layer.role == "lead" and layer.notes:
            return [n.swara for n in sorted(layer.notes, key=lambda note: note.start)]
    return []


def _contains(sequence: list[str], phrase: list[str]) -> bool:
    """True iff `phrase` occurs as a contiguous run inside `sequence` (octave-agnostic)."""
    if not phrase or len(phrase) > len(sequence):
        return False
    return any(sequence[i:i + len(phrase)] == phrase
               for i in range(len(sequence) - len(phrase) + 1))


def _next_within(sequence: list[str], swara: str, lo: int, max_gap: int) -> int | None:
    """Earliest index of `swara` at or after `lo` skipping at most `max_gap` notes, else None."""
    hi = min(len(sequence), lo + max_gap + 1)
    for i in range(lo, hi):
        if sequence[i] == swara:
            return i
    return None


def _fuzzy_contains(sequence: list[str], phrase: list[str], max_gap: int) -> bool:
    """True iff `phrase` occurs as an in-order subsequence of `sequence` with at most
    `max_gap` intervening notes between consecutive swaras (octave-agnostic).

    Anchored at each occurrence of the first swara; greedy-earliest for the rest, which
    minimises every gap and so never misses a valid bounded-gap match.
    """
    if not phrase or len(phrase) > len(sequence):
        return False
    for start in range(len(sequence)):
        if sequence[start] != phrase[0]:
            continue
        pos, matched = start, 1
        for swara in phrase[1:]:
            nxt = _next_within(sequence, swara, pos + 1, max_gap)
            if nxt is None:
                break
            pos, matched = nxt, matched + 1
        if matched == len(phrase):
            return True
    return False


def _match_pakad(lead: list[str], phrase: list[str]) -> PakadMatch:
    if _contains(lead, phrase):
        return "literal"
    if _fuzzy_contains(lead, phrase, _MAX_PAKAD_GAP):
        return "fuzzy"
    return "absent"


def pakad_presence(lead: list[str], raga: str) -> list[tuple[list[str], PakadMatch]]:
    """For each pakad phrase, how it surfaces in `lead`: literal / fuzzy / absent.

    Pure and testable. A literal contiguous quote is the strong signal; a fuzzy match
    tolerates grace/passing notes threaded through the phrase; absent means neither
    fired, and whether it is still present in spirit is the judgment left to Rasik —
    code supplies the fact, the LLM supplies the taste.
    """
    return [(phrase, _match_pakad(lead, phrase)) for phrase in RAGAS[raga]["pakad"]]


# --------------------------------------------------------------------------- #
# Pure renderers: FACTS -> prompt text. Rasik needs the raga's full character   #
# (to judge idiom/rasa) plus the actual lead line (to judge pakad). The ensemble #
# view belongs to the PRODUCER now (balance/independence), not here. The single  #
# source of truth stays in raga.py; the prompt quotes it. (The composers render  #
# a similar raga block; a shared facts->prompt module is the natural refactor     #
# once step 6 settles — deferred to avoid churn now.)                            #
# --------------------------------------------------------------------------- #

def _render_raga_facts(raga: str) -> str:
    """The raga's encoded character — the criteria Rasik judges idiom and mood against."""
    r = RAGAS[raga]
    lines = [
        f"  {raga}: {r['display']} — {r['western_mode']}; allowed: {' '.join(r['allowed'])}",
        f"  aroha: {' '.join(r['aroha'])}   avaroha: {' '.join(r['avaroha'])}",
        f"  pakad: {' | '.join(' '.join(p) for p in r['pakad'])}",
        f"  chalan: {' | '.join(' '.join(p) for p in r['chalan'])}",
        f"  vadi {r['vadi']}, samvadi {r['samvadi']}; rasa/samay: {r['samay']}",
        f"  nyas (where its phrases rest): {render_nyas(raga)}",
    ]
    register = render_register(raga)
    if register:
        lines.append(f"  register (where it LIVES): {register}")
    if r.get("andolan"):
        lines.append(f"  andolan (swaras that oscillate — idiomatic): {' '.join(r['andolan'])}")
    kan = render_kan(raga)
    if kan:
        lines.append(f"  kan (how a swara is approached): {kan}")
    character = render_character(raga)
    if character:
        lines.append(f"  character (how it treats its swaras): {character}")
    return "\n".join(lines)


_PAKAD_MARK: Final[dict[PakadMatch, str]] = {
    "literal": "appears verbatim",
    "fuzzy": "appears with intervening grace/passing notes (ornamented)",
    "absent": "not found in the lead (may still be evoked in spirit)",
}


def _render_pakad_hint(comp: Composition) -> str:
    lead = _lead_swaras(comp)
    if not lead:
        return "  (no lead voice in this piece — score pakad from whatever melodic content exists)"
    return "\n".join(
        f"  - {' '.join(phrase)}: {_PAKAD_MARK[match]}"
        for phrase, match in pakad_presence(lead, comp.raga))


def _render_motion(comp: Composition) -> str:
    """The line's MOVEMENT, measured — the grounding that stops a pakad count standing in for
    raga character.

    `pakad_presence` answers "is the signature phrase here?", which a piece can satisfy once
    and then walk the scale for three minutes. These numbers answer the other half: how far
    the line travels in one unbroken stepwise direction (the scale tell), how often it turns
    (the vakra character), and how much of it sits inside the raga's OWN movements rather than
    merely its note set. Code measures; Rasik decides whether the numbers matter musically —
    a high scalar run in a fast dash is idiomatic, the same number across a whole piece is not.
    """
    from chalan import motion_report
    lead = [(n.swara, n.oct) for layer in comp.layers if layer.role == "lead"
            for n in sorted(layer.notes or [], key=lambda x: x.start)]
    if not lead:
        return "  (no lead voice to measure)"
    report = motion_report(lead, comp.raga)
    return "\n".join((
        f"  - {report.stepwise_share:.0%} of melodic moves are a single step of the raga's "
        f"ladder, and the longest unbroken stepwise run is {report.longest_scalar_run} notes "
        f"(a run is the SCALE showing through; one dash is idiomatic, a ladder is not)",
        f"  - {report.direction_changes:.0%} of moves change direction (the vakra character)",
        f"  - {report.ang_coverage:.0%} of the notes sit inside one of this raga's own encoded "
        f"movements (its pakad/chalan phrases), rather than merely using its swaras"))


def register_profile(notes: list[Note], home: int) -> dict[str, float]:
    """Where the line spends its TIME (duration-weighted): below home Sa (mandra), in the home
    octave (madhya), above it (taar), and in the lower tetrachord (S..m) at any octave. Pure."""
    total = sum(n.dur for n in notes) or 1.0

    def share(picked: list[Note]) -> float:
        return round(sum(n.dur for n in picked) / total, 3)

    return {"mandra": share([n for n in notes if n.oct < home]),
            "madhya": share([n for n in notes if n.oct == home]),
            "taar": share([n for n in notes if n.oct > home]),
            "poorvanga": share([n for n in notes if SWARAS[n.swara] < SWARAS["P"]])}


def _render_register_profile(comp: Composition, arr: Arrangement | None) -> str:
    notes = _lead_notes(comp)
    if not notes:
        return ""
    home = arr.registers.get("lead", 0) if arr is not None else 0
    p = register_profile(notes, home)
    return (f"\n  - by time, the line sits {p['mandra']:.0%} in the mandra (below home Sa), "
            f"{p['madhya']:.0%} in the madhya, {p['taar']:.0%} in the taar; {p['poorvanga']:.0%} "
            f"of it on the lower tetrachord (S..m) — read against the raga's register above")


def _lead_notes(comp: Composition) -> list:
    for layer in comp.layers:
        if layer.role == "lead" and layer.notes:
            return sorted(layer.notes, key=lambda note: note.start)
    return []


def _render_lead_line(comp: Composition, arr: Arrangement | None = None) -> str:
    """The lead line, in order — grouped by SECTION (index, kind, form role) when the chart is
    given, so a suggestion can name the section it edits."""
    notes = _lead_notes(comp)
    if not notes:
        return "  (no lead voice in this piece)"
    if arr is None:
        return "  " + " ".join(note_token(n) for n in notes)
    lines = []
    for span in section_spans(arr):
        inside = [n for n in notes if span.start <= n.start < span.end]
        if inside:
            label = span.section.form_role or span.section.kind.value
            phrase = " ".join(note_token(n) for n in inside)
            lines.append(f"  section {span.index} ({label}): {phrase}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Boundary parsing. output_pydantic targets RasikVerdict; this recovers it (or  #
# None) so the shell fails loud on an unparseable answer.                       #
# --------------------------------------------------------------------------- #

def _verdict_from_output(output: Any) -> RasikVerdict | None:
    parsed = getattr(output, "pydantic", None)
    if isinstance(parsed, RasikVerdict):
        return parsed
    raw = getattr(output, "raw", None)
    try:
        return RasikVerdict.model_validate_json(raw) if raw else None
    except ValidationError:
        return None


def judge_inputs(comp: Composition, request: str = "",
                 arr: Arrangement | None = None) -> dict[str, Any]:
    """The assess_taste prompt inputs — the grounded facts, the lead (by section when the chart
    is given), and the user's request."""
    return {
        "raga": comp.raga,
        "raga_facts": _render_raga_facts(comp.raga),
        "pakad_hint": _render_pakad_hint(comp),
        "motion": (_render_motion(comp) + _render_register_profile(comp, arr)
                   + (f"\n{render_density(comp, arr)}" if arr is not None else "")),
        "lead_line": _render_lead_line(comp, arr),
        "user_request": render_request(request),
        "output_schema": _RUBRIC_SCHEMA,
    }


class _RasikCrew:
    """Runs ONE taste critique as an isolated, single-agent crew.

    No tool: unlike Ustad, Rasik judges from the prompt (the raga facts, the lead
    line, the pakad hint, the ensemble) — taste is not a lookup. Structured output is
    CrewAI's job (`output_pydantic=RasikVerdict`); the rubric's fixed scale is what
    disciplines the judgment. Config is read once at construction.
    """

    def __init__(self) -> None:
        config_dir = Path(__file__).parent / "config"
        self._agent_config = yaml.safe_load((config_dir / "agents.yaml").read_text())["rasik"]
        self._task_config = yaml.safe_load((config_dir / "tasks.yaml").read_text())["assess_taste"]

    def run(self, comp: Composition, request: str = "",
            arr: Arrangement | None = None) -> RasikVerdict:
        agent = Agent(config=self._agent_config, llm=critic_llm(),
                      allow_delegation=False, max_iter=CRITIC_MAX_ITER,
                      max_retry_limit=AGENT_RETRY_LIMIT, verbose=False)
        task = Task(config=self._task_config, agent=agent, **structured_output(RasikVerdict))
        crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)
        result = crew.kickoff(inputs=judge_inputs(comp, request, arr))
        verdict = _verdict_from_output(result)
        if verdict is None:
            raise ValueError("Rasik returned no parseable RasikVerdict")
        return verdict


# A judge provider: given the composition, return Rasik's verdict. Injected so
# `assess` is tested with no LLM.
type JudgeFn = Callable[[Composition], RasikVerdict]


class _LLMJudge:
    """The real (LLM-backed) `judge_fn` — holds the crew across calls."""

    def __init__(self, request: str = "", arr: Arrangement | None = None) -> None:
        self._crew = _RasikCrew()
        self._request = request
        self._arr = arr

    def __call__(self, comp: Composition) -> RasikVerdict:
        return self._crew.run(comp, self._request, self._arr)


# --------------------------------------------------------------------------- #
# The critique — thin, because the verdict is the LLM's (the contrast with      #
# Ustad, where code assembled the verdict). We stream the rubric as scores on   #
# the CRITIQUE event; the Conductor interprets a low score in step 6.           #
# --------------------------------------------------------------------------- #

def _verdict_event(verdict: RasikVerdict) -> DebateEvent:
    s = verdict.scores
    return DebateEvent(
        type=EventType.CRITIQUE, agent="Rasik", role=_ROLE_CRITIC,
        text=verdict.notes,
        scores={"pakad": float(s.pakad), "idiom": float(s.idiom), "rasa": float(s.rasa)},
        data={"reasoning": verdict.reasoning,
              "suggestions": [x.model_dump() for x in verdict.suggestions]})


def assess(comp: Composition, *, judge_fn: JudgeFn) -> tuple[RasikVerdict, list[DebateEvent]]:
    """Judge a composition's taste on the fixed rubric and stream it as one CRITIQUE.

    The verdict IS the model's (taste is not checkable) — the shell only renders the
    grounded prompt, wraps the result, and emits the event. `judge_fn` is injected so
    this plumbing is tested with no LLM.
    """
    verdict = judge_fn(comp)
    verdict = verdict.model_copy(update={"suggestions": verdict.suggestions[:_MAX_SUGGESTIONS]})
    return verdict, [_verdict_event(verdict)]


def critique_taste(comp: Composition, request: str = "",
                   arr: Arrangement | None = None) -> tuple[RasikVerdict, list[DebateEvent]]:
    """Run the real (LLM-backed) Rasik consultation on a composition, told what the user asked;
    with the chart, its lead is shown by section so its suggestions can name one."""
    return assess(comp, judge_fn=_LLMJudge(request, arr))


# --------------------------------------------------------------------------- #
# Entry point — a single cheap live call on a tiny composition whose lead QUOTES #
# the raga's pakad, so the grounding hint fires and Rasik has real music to score.#
# --------------------------------------------------------------------------- #

def _demo_composition(raga: str = "darbari") -> Composition:
    """A hand-built drone + lead piece whose lead line literally quotes the raga's
    pakad phrases — small, legal by construction, and enough for one cheap live score."""
    from crew.contracts import Layer, Note
    lead_swaras = [sw for phrase in RAGAS[raga]["pakad"] for sw in phrase]
    lead = [Note(swara=sw, oct=0, start=float(i), dur=1.0) for i, sw in enumerate(lead_swaras)]
    total = float(len(lead_swaras))
    drone = Note(swara=RAGAS[raga]["allowed"][0], oct=-2, start=0.0, dur=total)
    return Composition(
        raga=raga, sa=62, bpm=90, tala={"name": "teentaal", "beats_per_bar": 16.0},
        layers=[Layer(role="drone", notes=[drone]), Layer(role="lead", notes=lead)])


def _run() -> None:
    from crew.contracts import EventStream
    comp = _demo_composition()
    stream = EventStream()
    verdict, events = critique_taste(comp)
    for event in events:
        stream.emit(event)
    s = verdict.scores
    print(f"\nRasik scores: pakad={s.pakad} idiom={s.idiom} rasa={s.rasa}")
    print(f"  notes: {verdict.notes}")


def main(argv: list[str]) -> int:
    load_env()  # entry point loads .env
    from contextlib import nullcontext

    from crew.tracing import traced, tracing_enabled
    ctx = traced("rasik-demo") if tracing_enabled() else nullcontext()
    with ctx:
        _run()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
