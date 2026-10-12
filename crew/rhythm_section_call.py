"""
The RHYTHM SECTION call — one LLM call writes guitar and bass for the whole piece from the realised
sitar line (the pure half — what it sees, what it may return, how it becomes layers — is
`crew/rhythm_section.py`).

  * `rhythm_section_inputs` — the prompt inputs: the raga's riff facts (the riff prompt's own
    renderers), the tala's marked beats, the chart with each section's harmony plan, the seed's
    main riff, and the timed sitar line. Pure.
  * the guardrail — `part_errors` fed back for ONE bounded retry (the project's rule: validate at
    the boundary, one retry, not a loop).
  * `compose_rhythm_section` — the LLM-backed `RhythmSectionFn`, at the conception tier: this call
    conceives the arrangement, it does not fill in a template.

The Flow wiring, the fallback to the per-section riff and the revise path come later (step 3).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final, Protocol, Sequence

import yaml
from crewai import Agent, Crew, Process, Task
from pydantic import ValidationError

from crew.config import (
    AGENT_RETRY_LIMIT,
    GENERATOR_MAX_ITER,
    GENERATOR_RETRIES,
    composer_llm,
    structured_output,
)
from crew.contracts import Arrangement, Layer, RhythmSection
from crew.generators import section_spans
from crew.lead import render_direction_rule
from crew.rhythm_section import part_errors, render_timed_lead
from crew.riff import render_half_steps, render_home_root
from crew.riff_playability import render_playability
from crew.riff_voicing import render_power_roots
from crew.user_request import render_request
from raga import RAGAS, directional_varjya
from subgenres import SUBGENRES
from talas import TALAS

_MAX_FEEDBACK: Final = 12         # the retry names at most this many faults (the first few matter)

_OUTPUT_SCHEMA: Final = """{
  "reasoning": "the arrangement plan, FIRST: the home chord and where it holds; the head's chord pattern (it recurs with every mukhada); how the manjha and antara move, and the antara's climb; where the guitar rings under the sitar and where it answers",
  "parts": [
    {"section": <section index>, "role": "<what the guitar does here, and why>",
     "guitar": [[<one avartan of notes>], [<the next avartan>]],
     "bass": [[<one avartan of single notes>]]},
    {"section": <section index>, "role": "<what the guitar does here, and why>",
     "same_as": <the section whose part this replays exactly>}
  ]
}
A note: {"swara": "<raga swara>", "oct": <octave>, "dur": <beats>} with optional "chord",
"technique" and "vel"; a silence: {"rest": true, "swara": "S", "dur": <beats>}.
(Format only — every musical choice is yours.)
"guitar" and "bass" are lists of AVARTAN CYCLES: cycle 1 plays the section's first avartan,
cycle 2 its second, and a section longer than its cycles repeats the last one — write as many
cycles as the section needs to develop, or one if it holds. Each cycle's durations, rests
included, add up to exactly one avartan. Durations are in beats (0.25 = 16th, 0.5 = 8th, 1 =
quarter). "oct" for the guitar: 0 = its low home register, 1 = an octave up (the antara's
climb); for the bass: 0 = an octave under the guitar's home. "chord" — leave it EMPTY for weight:
code voices every bare stroke as a power chord inside the raga. Write a chord only for a
deliberate colour (extra raga swaras sounded with the root). "technique" = palm_mute (a tight
chug, a beat or shorter), slide, long_slide, pick_scrape, bend, hammer_on, pull_off — on single
notes; omit it for a plain picked note, and give a ringing chord no technique and a long
"dur". "vel" (optional, 1-127) shapes the accents. "same_as" replays another section's part —
use it for every return of the head. A section where the guitar does not play needs no part."""


# --------------------------------------------------------------------------- #
# What the call sees — pure                                                   #
# --------------------------------------------------------------------------- #

def _render_accents(arr: Arrangement) -> str:
    return ", ".join(f"beat {a.beat:g} {a.kind}" for a in arr.accent_grid)


def _render_chart(arr: Arrangement) -> str:
    """Every section in order — what the call plans its parts against."""
    lines = []
    for span in section_spans(arr):
        sec = span.section
        plan = sec.harmony
        harmony = (f"harmony {plan.mode}" + (f" on {' '.join(plan.roots)}" if plan.roots else "")
                   if plan else "harmony modal_pedal")
        guitar = "guitar plays" if "rhythm" in sec.layers else "NO guitar"
        lines.append(f"  section {span.index}: {sec.form_role or sec.kind.value}, {sec.bars} "
                     f"avartan{'s' if sec.bars != 1 else ''}, {guitar}, foreground "
                     f"{sec.foreground}, {harmony} — {sec.intent or 'no intent given'}")
    return "\n".join(lines)


def _render_seed_riff(arr: Arrangement) -> str:
    if arr.seed_riff is None:
        return "  (none — the rhythm section is yours to invent)"
    tokens = []
    for n in arr.seed_riff.notes:
        if n.rest:
            tokens.append(f"rest({n.dur:g})")
            continue
        tok = n.swara if n.oct == 0 else f"{n.swara}({n.oct:+d})"
        tok += ("+" + "+".join(n.chord)) if n.chord else ""
        tok += f"({n.dur:g}{', ' + n.technique if n.technique else ''})"
        tokens.append(tok)
    return "  " + " ".join(tokens)


def _render_repair(feedback: Sequence[str] | None) -> str:
    if not feedback:
        return "(first take — nothing to repair)"
    issues = "\n".join(f"  - {v}" for v in list(feedback)[:_MAX_FEEDBACK])
    return "YOUR PREVIOUS ANSWER FAILED these hard checks — fix exactly these, keep the rest:\n" + issues


def rhythm_section_inputs(arr: Arrangement, lead_layers: Sequence[Layer],
                          feedback: Sequence[str] | None = None) -> dict[str, Any]:
    """Every input the `compose_rhythm_section` template names. Pure."""
    raga, sub = RAGAS[arr.raga], SUBGENRES[arr.subgenre]
    return {
        "raga": raga["display"],
        "allowed": " ".join(raga["allowed"]),
        "direction_rule": render_direction_rule(directional_varjya(arr.raga))
                          or "(every swara moves freely both ways)",
        "home_root": render_home_root(arr.raga),
        "power_roots": render_power_roots(arr.raga),
        "half_steps": render_half_steps(arr.raga),
        "pakad": " | ".join(" ".join(p) for p in raga["pakad"]),
        "chalan": " | ".join(" ".join(p) for p in raga["chalan"]),
        "subgenre": sub["display"],
        "subgenre_feel": sub["feel"],
        "subdivision": sub["subdivision"],
        "groove_brief": sub["groove_brief"],
        "techniques": ", ".join(sub["techniques"]),
        "bpm": arr.bpm,
        "tala": TALAS[arr.tala]["display"],
        "cycle_beats": f"{arr.beats_per_bar:g}",
        "accents": _render_accents(arr),
        "playability": render_playability(arr),
        "user_request": render_request(arr.request),
        "chart": _render_chart(arr),
        "energy_arc": arr.energy_arc or "(none given)",
        "seed_riff": _render_seed_riff(arr),
        "sitar_line": render_timed_lead(lead_layers, arr),
        "repair": _render_repair(feedback),
        "output_schema": _OUTPUT_SCHEMA,
    }


# --------------------------------------------------------------------------- #
# The boundary: parse, then the hard checks as one bounded retry              #
# --------------------------------------------------------------------------- #

def _section_from_output(output: Any) -> RhythmSection | None:
    parsed = getattr(output, "pydantic", None)
    if isinstance(parsed, RhythmSection):
        return parsed
    raw = getattr(output, "raw", None)
    try:
        return RhythmSection.model_validate_json(raw) if raw else None
    except ValidationError:
        return None


def rhythm_section_guardrail(arr: Arrangement):
    """The Task guardrail: (True, RhythmSection) when it can be played, else (False, the faults)."""
    def guard(output: Any):
        rs = _section_from_output(output)
        if rs is None:
            return (False, "Return a single valid RhythmSection JSON object and nothing else.")
        errors = part_errors(rs, arr)
        if errors:
            return (False, "Fix these and resend:\n" + "\n".join(errors[:_MAX_FEEDBACK]))
        return (True, rs)

    guard.__annotations__["return"] = tuple[bool, Any]
    return guard


# --------------------------------------------------------------------------- #
# The LLM-backed call                                                         #
# --------------------------------------------------------------------------- #

class RhythmSectionFn(Protocol):
    """A rhythm-section provider: the chart and the placed sitar in, guitar + bass parts out."""

    def __call__(self, arr: Arrangement, lead_layers: Sequence[Layer], *,
                 feedback: Sequence[str] | None = None) -> RhythmSection: ...


class _RhythmSectionCrew:
    """The isolated single-agent crew — config read once, `RhythmSection` as structured output,
    the playability guardrail for one bounded retry (mirrors `_OrchestraCrew`)."""

    def __init__(self) -> None:
        config_dir = Path(__file__).parent / "config"
        self._agent_config = yaml.safe_load((config_dir / "agents.yaml").read_text())["rhythm_section"]
        self._task_config = yaml.safe_load(
            (config_dir / "tasks.yaml").read_text())["compose_rhythm_section"]

    def run(self, arr: Arrangement, inputs: dict[str, Any]) -> RhythmSection:
        agent = Agent(config=self._agent_config, llm=composer_llm(), allow_delegation=False,
                      max_iter=GENERATOR_MAX_ITER, max_retry_limit=AGENT_RETRY_LIMIT, verbose=False)
        task = Task(config=self._task_config, agent=agent, **structured_output(RhythmSection),
                    guardrail=rhythm_section_guardrail(arr), guardrail_max_retries=GENERATOR_RETRIES)
        crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)
        rs = _section_from_output(crew.kickoff(inputs=inputs))
        if rs is None:
            raise ValueError("the rhythm section returned no parseable RhythmSection")
        return rs


def compose_rhythm_section(arr: Arrangement, lead_layers: Sequence[Layer], *,
                           feedback: Sequence[str] | None = None) -> RhythmSection:
    """The real `RhythmSectionFn`: one call, guitar + bass for the whole piece."""
    return _RhythmSectionCrew().run(arr, rhythm_section_inputs(arr, lead_layers, feedback))
