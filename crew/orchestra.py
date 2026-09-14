"""
The Orchestra generator — the symphonic-metal CINEMATIC voice.

The talk's third named idea beside the critique loop and the studio collaboration:
CAPABILITY-GATED agent instantiation. The crew's roster is not fixed — a specialist
joins ONLY when the input calls for it. A symphonic chart spawns an Orchestra; a thrash
chart never pays for one. `uses_orchestra(arr)` is that gate (any section that lists the
`orchestra` layer), decided by the composers per the per-subgenre role brief.

The split the whole project preaches, applied once more:
  * the LLM (ONE whole-chart call — orchestration is HOLISTIC: long arcs, the choir/brass
    reserved for the peak) decides the per-section INTENT — what the strings/brass/choir
    DO, when they enter, the dynamic arc, and an optional raga-legal countermelody;
  * CODE (this module, pure) EXPANDS that intent into real Layers — a wide string section,
    brass, choir, timpani — every pitch a raga swara, seated so an upward voicing never
    enters a descent-only tone. The RAGA is the hard constraint that keeps it Hindustani,
    not generic film score: the harmony stays DRONE/MODAL, never Western functional motion.

Layering (pure core / imperative shell, as in lead.py):
  * pure       — the expander (`orchestra_layers_from` + the family realisers) and
                 `generate_orchestra` (control flow over an injected `gen_fn`, tested with
                 no LLM);
  * imperative — `_LLMOrchestra` / `_OrchestraCrew` make the Gemini call; `main` renders.

Sound check (NO LLM, no API cost — a hand-authored symphonic chart + orchestral intent):
  uv run python -m crew.orchestra   ->  out/orchestra_demo.wav
"""

from __future__ import annotations

import shutil
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Final, Protocol

import yaml
from crewai import Agent, Crew, Process, Task
from pydantic import ValidationError

from crew.config import (
    AGENT_RETRY_LIMIT,
    GENERATOR_MAX_ITER,
    GENERATOR_RETRIES,
    generator_llm,
)
from crew.contracts import (
    Arrangement,
    DebateEvent,
    EventType,
    Layer,
    LeadNote,
    Note,
    OrchestraScore,
    SectionOrchestra,
    motif_illegal_in_raga,
)
from crew.harmonic_guide import HarmonicWindow, avoided_at, harmonic_guide, supported
from crew.generators import (
    VOICES,
    SectionSpan,
    assemble_composition,
    render_composition,
    section_spans,
)
from raga import RAGAS, SWARAS, ascent_step, direction_violations, directional_varjya

# The section-level activation token (Section.layers), and the four render roles the
# expander emits — each its own VOICES entry / GM program / channel.
_SECTION_ROLE: Final = "orchestra"
_STRINGS: Final = "orch_strings"
_BRASS: Final = "orch_brass"
_CHOIR: Final = "orch_choir"
_TIMPANI: Final = "orch_timpani"
_ORCH_ROLES: Final = (_STRINGS, _BRASS, _CHOIR, _TIMPANI)

_ROLE_GENERATOR: Final = "generator"

# A fixed dynamic marking -> a base velocity the families scale from.
_DYNAMIC_VEL: Final[dict[str, int]] = {
    "pp": 40, "p": 52, "mp": 64, "mf": 78, "f": 94, "ff": 110,
}
# Per-family scale off the section dynamic — the orchestra is an ACCOMPANIST: the string
# pad shimmers under the band, brass punches its accents, the choir washes, timpani lands.
_STRINGS_VEL: Final = 0.85
_BRASS_VEL: Final = 1.00
_CHOIR_VEL: Final = 0.90
_TIMPANI_VEL: Final = 1.00

_TREMOLO_STEP: Final = 0.5      # a tremolo wash re-bows every 8th note
_OSTINATO_STEP: Final = 0.5     # an ostinato rolls its tones in 8ths
_STAB_DUR: Final = 0.5          # a brass stab is short and punchy
_TIMP_HIT_DUR: Final = 0.5      # a timpani reinforcement on the sam
_TIMP_ROLL_STEPS: Final = 6     # a roll into the next section — this many fast strokes over...
_TIMP_ROLL_BEATS: Final = 1.0   # ...the section's final beat
_TIMP_FLOOR: Final = -2         # the timpani never sinks below this octave (defined, not subsonic)

_ORCH_REPAIR_TRIES: Final = 1   # extra re-rolls of an out-of-raga intent (bounded; best-of-N kept)

_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
_SOUNDFONT: Final[Path] = _ROOT / "soundfonts" / "GeneralUser-GS.sf2"
_OUT_DIR: Final[Path] = _ROOT / "out"


def uses_orchestra(arr: Arrangement) -> bool:
    """Whether this chart calls for the Orchestra — any section that lists the `orchestra`
    layer. The CAPABILITY GATE: the crew spawns the Orchestra agent only when this is True
    (symphonic charts always; other subgenres only where the composers add it as colour)."""
    return any(_SECTION_ROLE in section.layers for section in arr.sections)


# --------------------------------------------------------------------------- #
# The expander — SectionOrchestra intent -> raga-legal Notes. Pure.            #
# Every voicing tone is drawn from the raga's own ladder and seated so an       #
# upward voicing never sustains a descent-only swara — legal by construction.   #
# --------------------------------------------------------------------------- #

def _seat(swara: str, raga: str) -> tuple[str, int]:
    """Seat a voicing tone legal-and-holdable: a descent-only swara (directional varjya —
    Bageshree's P) is lifted to the next swara enterable from below, so the orchestra never
    SUSTAINS a one-directional tone in the wrong place. Any other tone keeps its seat. Pure."""
    if directional_varjya(raga).get(swara) != "avaroha":
        return swara, 0
    return ascent_step(swara, raga)


def _voicing(swaras: list[str], raga: str, *, default: list[str],
             avoid: frozenset[str] = frozenset()) -> list[tuple[str, int]]:
    """A section's orchestral voicing: the given swaras (or a raga-derived default when the
    LLM left them empty), each seated ascendable, deduped. (swara, octave-delta) pairs.

    `avoid` is the harmonic guide's verdict for this section — swaras that would grind under
    what the melody settles on. The orchestra scores before it can know the finished melody
    note by note, and four accompanying voices each choosing legally is how a piece ends up
    sustaining a cluster nobody designed. Filtering here keeps the orchestration and drops
    only the colours that fight; it can never empty a voicing."""
    tones = [t for t in swaras if t in SWARAS] or default
    seated = [_seat(sw, raga) for sw in supported(tones, avoid)]
    return list(dict.fromkeys(seated)) or [("S", 0)]


def _vel(base_vel: int, scale: float) -> int:
    return max(1, min(127, round(base_vel * scale)))


def _bars(span: SectionSpan, cycle: float) -> list[tuple[float, float]]:
    """(start, end) for each avartan of the section — the windows a per-bar texture fills."""
    return [(span.start + b * cycle, span.start + (b + 1) * cycle)
            for b in range(span.section.bars)]


def _held(voicing: list[tuple[str, int]], bars: list[tuple[float, float]], base: int,
          vel: int, *, low_root: bool = True) -> list[Note]:
    """The voicing HELD across each avartan — the string/choir PAD. Optionally doubles the
    root an octave below (the cello foundation of a string section)."""
    notes: list[Note] = []
    for start, end in bars:
        for sw, od in voicing:
            notes.append(Note(swara=sw, oct=base + od, start=round(start, 4),
                              dur=round(end - start, 4), vel=vel))
        if low_root:
            notes.append(Note(swara="S", oct=base - 1, start=round(start, 4),
                              dur=round(end - start, 4), vel=vel))
    return notes


def _tremolo(voicing: list[tuple[str, int]], bars: list[tuple[float, float]], base: int,
             vel: int) -> list[Note]:
    """A tremolo wash — the voicing re-bowed every 8th note across each avartan."""
    notes: list[Note] = []
    for start, end in bars:
        t = start
        while t < end - 1e-9:
            dur = min(_TREMOLO_STEP, end - t)
            for sw, od in voicing:
                notes.append(Note(swara=sw, oct=base + od, start=round(t, 4),
                                  dur=round(dur * 0.9, 4), vel=vel))
            t += _TREMOLO_STEP
    return notes


def _ostinato(voicing: list[tuple[str, int]], bars: list[tuple[float, float]], base: int,
              vel: int) -> list[Note]:
    """A rolling ostinato — the voicing's tones cycled as an 8th-note figure (a driving
    string engine, the Nightwish/Fleshgod motor)."""
    tones = voicing or [("S", 0)]
    notes: list[Note] = []
    for start, end in bars:
        t, i = start, 0
        while t < end - 1e-9:
            sw, od = tones[i % len(tones)]
            dur = min(_OSTINATO_STEP, end - t)
            notes.append(Note(swara=sw, oct=base + od, start=round(t, 4),
                              dur=round(dur * 0.95, 4), vel=vel))
            t += _OSTINATO_STEP
            i += 1
    return notes


def _stab_beats(accent_beats: list[float], bar_index: int) -> list[float]:
    """WHICH accents this avartan's brass answers — a hierarchy, not reinforcement everywhere.

    The tala's accents are candidate locations, not a schedule. Punching the guitar, kick,
    tabla AND brass together on every sam and every tali is the "epic soundtrack" tell:
    everything arrives at once, every cycle, so nothing is an arrival. So the brass takes the
    sam every avartan (the cycle's one true downbeat) and answers a LATER accent only on
    alternate cycles — the bar you expect it and the bar you don't, which is what makes the
    hit land. Pure."""
    if not accent_beats:
        return []
    sam = accent_beats[:1]
    if bar_index % 2 == 0 or len(accent_beats) < 2:
        return sam
    return sam + accent_beats[-1:]


def _stabs(voicing: list[tuple[str, int]], bars: list[tuple[float, float]],
           accent_beats: list[float], base: int, vel: int) -> list[Note]:
    """Brass STABS — short accented hits on the tala's structural beats, so the brass locks
    to the kick and the riff's accents (register-separated above the guitars). It answers a
    CHOSEN few of the accents rather than all of them (see `_stab_beats`)."""
    notes: list[Note] = []
    for bar_index, (start, end) in enumerate(bars):
        for beat in _stab_beats(accent_beats, bar_index):
            hit = start + beat
            if hit >= end - 1e-9:
                continue
            for sw, od in voicing:
                notes.append(Note(swara=sw, oct=base + od, start=round(hit, 4),
                                  dur=_STAB_DUR, vel=vel))
    return notes


def _choir_swell(voicing: list[tuple[str, int]], bars: list[tuple[float, float]], base: int,
                 base_vel: int) -> list[Note]:
    """A choir SWELL — the voicing held per avartan with a velocity crescendo across the
    section (soft entry, arriving full — the cinematic build)."""
    n = max(1, len(bars))
    notes: list[Note] = []
    for i, (start, end) in enumerate(bars):
        vel = _vel(base_vel, _CHOIR_VEL * (0.55 + 0.45 * (i + 1) / n))
        for sw, od in voicing:
            notes.append(Note(swara=sw, oct=base + od, start=round(start, 4),
                              dur=round(end - start, 4), vel=vel))
    return notes


def _place_countermelody(notes: list[LeadNote], *, start: float, end: float,
                         base: int) -> list[Note]:
    """Lay a raga-legal countermelody end-to-end from `start`, seated at the orchestra
    register, truncated at the section edge. Plain notes only — no sitar ornament or meend
    (strings share their channel with the pad; a channel-wide wheel gesture would bend the
    whole section), so the answer line reads clean over the sustained voicing. Pure."""
    placed: list[Note] = []
    t = start
    for ln in notes:
        if t >= end - 1e-9:
            break
        if ln.rest:
            t += ln.dur
            continue
        dur = min(ln.dur, end - t)
        placed.append(Note(swara=ln.swara, oct=base + ln.oct, start=round(t, 4),
                          dur=round(dur, 4), vel=ln.vel))
        t += ln.dur
    return placed


def _strings_sustained(intent: SectionOrchestra, voicing: list[tuple[str, int]],
                       bars: list[tuple[float, float]], base: int, vel: int) -> list[Note]:
    """The strings' SUSTAINED texture per its role (the counter-line is added separately)."""
    if intent.strings == "pad":
        return _held(voicing, bars, base, vel)
    if intent.strings == "tremolo":
        return _tremolo(voicing, bars, base, vel)
    if intent.strings == "ostinato":
        return _ostinato(voicing, bars, base, vel)
    return []   # "counter" (the counter-line carries it) or "silent"


def _strings_notes(intent: SectionOrchestra, span: SectionSpan, arr: Arrangement, base: int,
                   base_vel: int, avoid: frozenset[str] = frozenset()) -> list[Note]:
    raga = arr.raga
    r = RAGAS[raga]
    vel = _vel(base_vel, _STRINGS_VEL)
    bars = _bars(span, arr.beats_per_bar)
    voicing = _voicing(intent.string_swaras, raga, default=["S", r["vadi"]], avoid=avoid)
    sustained = _strings_sustained(intent, voicing, bars, base, vel)
    counter = (_place_countermelody(intent.countermelody, start=span.start, end=span.end, base=base)
               if intent.countermelody else [])
    # A "counter" section with no supplied line still wants strings — give it a thin pad.
    if intent.strings == "counter" and not counter:
        sustained = _held(voicing, bars, base, vel)
    return sustained + counter


def _brass_notes(intent: SectionOrchestra, span: SectionSpan, arr: Arrangement, base: int,
                 base_vel: int) -> list[Note]:
    if intent.brass == "silent":
        return []
    raga = arr.raga
    # brass wants weight — the root plus the fifth (Pa) where the raga has it, else the vadi.
    fifth = "P" if "P" in RAGAS[raga]["allowed"] else RAGAS[raga]["vadi"]
    voicing = _voicing(intent.brass_swaras, raga, default=["S", fifth])
    vel = _vel(base_vel, _BRASS_VEL)
    bars = _bars(span, arr.beats_per_bar)
    if intent.brass == "sustain":
        return _held(voicing, bars, base, vel, low_root=False)
    accent_beats = [a.beat for a in arr.accent_grid if a.kind in ("sam", "tali")]
    return _stabs(voicing, bars, accent_beats, base, vel)


def _choir_notes(intent: SectionOrchestra, span: SectionSpan, arr: Arrangement, base: int,
                 base_vel: int, avoid: frozenset[str] = frozenset()) -> list[Note]:
    if intent.choir == "silent":
        return []
    raga = arr.raga
    voicing = _voicing(intent.choir_swaras, raga, default=["S", RAGAS[raga]["vadi"]],
                       avoid=avoid)
    bars = _bars(span, arr.beats_per_bar)
    if intent.choir == "swell":
        return _choir_swell(voicing, bars, base, base_vel)
    return _held(voicing, bars, base, _vel(base_vel, _CHOIR_VEL), low_root=False)


def _timpani_notes(intent: SectionOrchestra, span: SectionSpan, arr: Arrangement, base: int,
                   base_vel: int) -> list[Note]:
    """A timpani reinforcement on each avartan's sam, plus a ROLL into the next section when
    the intent swells — the classic transition/climax lift. Timpani sounds the root (Sa),
    trivially legal, seated low but never subsonic."""
    if not (intent.timpani or intent.swell_into_next):
        return []
    low = max(base - 1, _TIMP_FLOOR)
    vel = _vel(base_vel, _TIMPANI_VEL)
    bars = _bars(span, arr.beats_per_bar)
    notes = [Note(swara="S", oct=low, start=round(start, 4), dur=_TIMP_HIT_DUR, vel=vel)
             for start, _ in bars]
    if intent.swell_into_next and bars:
        section_end = bars[-1][1]
        roll_start = max(bars[-1][0], section_end - _TIMP_ROLL_BEATS)
        step = (section_end - roll_start) / _TIMP_ROLL_STEPS
        for k in range(_TIMP_ROLL_STEPS):
            t = roll_start + k * step
            rvel = _vel(base_vel, _TIMPANI_VEL * (0.55 + 0.45 * (k + 1) / _TIMP_ROLL_STEPS))
            notes.append(Note(swara="S", oct=low, start=round(t, 4),
                              dur=round(step * 0.9, 4), vel=rvel))
    return notes


def orchestra_layers_from(arr: Arrangement, score: OrchestraScore, *,
                          guide: tuple[HarmonicWindow, ...] = ()) -> list[Layer]:
    """Expand a whole-chart OrchestraScore into the orchestral Layers — one per family that
    actually sounds. Each intent addresses a section by index; an intent for a section that
    does not list the `orchestra` layer is ignored. Returns [] when no family sounds (a chart
    with no orchestra, or an all-silent score), so the assembly simply appends nothing. Pure —
    no LLM, no I/O; every pitch is a raga swara, so `validate_composition` never flags it."""
    base = arr.registers.get(_SECTION_ROLE, arr.registers.get("lead", 0))
    spans = {span.index: span for span in section_spans(arr)}
    by_role: dict[str, list[Note]] = {role: [] for role in _ORCH_ROLES}
    for intent in score.sections:
        span = spans.get(intent.section_index)
        if span is None or _SECTION_ROLE not in span.section.layers:
            continue
        base_vel = _DYNAMIC_VEL[intent.dynamic]
        # Only the SUSTAINING families are filtered: a held string pad or choir tone is what
        # the ear stacks into a cluster, while brass stabs and timpani are over too quickly.
        avoid = avoided_at(guide, span.start)
        by_role[_STRINGS].extend(_strings_notes(intent, span, arr, base, base_vel, avoid))
        by_role[_BRASS].extend(_brass_notes(intent, span, arr, base, base_vel))
        by_role[_CHOIR].extend(_choir_notes(intent, span, arr, base, base_vel, avoid))
        by_role[_TIMPANI].extend(_timpani_notes(intent, span, arr, base, base_vel))
    layers: list[Layer] = []
    for role in _ORCH_ROLES:
        notes = by_role[role]
        if notes:
            voice = VOICES[role]
            layers.append(Layer(role=role, instrument=voice.instrument, program=voice.program,
                                channel=voice.channel, pan=voice.pan, notes=notes))
    return layers


# --------------------------------------------------------------------------- #
# The legality guardrail (the hard line) — every orchestral pitch stays in the #
# raga, and each countermelody enters a one-directional swara from its own side.#
# --------------------------------------------------------------------------- #

def _orchestra_swaras(score: OrchestraScore) -> list[str]:
    """Every swara the score commits to — each family's voicing swaras plus every
    countermelody note, its kan, and its meend target — flattened for the grammar."""
    swaras: list[str] = []
    for section in score.sections:
        swaras += section.string_swaras + section.brass_swaras + section.choir_swaras
        for note in section.countermelody:
            if note.rest:
                continue
            swaras.append(note.swara)
            swaras.extend(note.grace or [])
            if note.meend_swara is not None:
                swaras.append(note.meend_swara)
    return swaras


def _orchestra_grammar_error(score: OrchestraScore, raga: str) -> str | None:
    """The domain rule the guardrail enforces, as a precise retryable error (or None when
    clean): every orchestral swara legal in the raga, and each countermelody line entering a
    descent-only swara from above (never below), mirroring the lead guardrail."""
    illegal = motif_illegal_in_raga(_orchestra_swaras(score), raga)
    if illegal:
        return (f"swaras {sorted(set(illegal))} are illegal in raga {raga}. "
                f"Use only these swaras: {' '.join(RAGAS[raga]['allowed'])}. Fix and resend.")
    for section in score.sections:
        seq: list[tuple[str, int]] = []
        for note in section.countermelody:
            if note.rest:
                continue
            seq.append((note.swara, note.oct))
            if note.meend_swara is not None:
                seq.append((note.meend_swara, note.meend_oct if note.meend_oct is not None else note.oct))
        violations = direction_violations(seq, raga)
        if violations:
            return ("; ".join(dict.fromkeys(violations))
                    + " (in the orchestra countermelody). Fix the approach and resend.")
    return None


def _score_from_output(output: Any) -> OrchestraScore | None:
    """The OrchestraScore CrewAI parsed via output_pydantic (or None if parsing failed)."""
    parsed = getattr(output, "pydantic", None)
    if isinstance(parsed, OrchestraScore):
        return parsed
    raw = getattr(output, "raw", None)
    try:
        return OrchestraScore.model_validate_json(raw) if raw else None
    except ValidationError:
        return None


def _orchestra_guardrail(raga: str):
    """Build the Task guardrail: the raga-grammar rule over the whole score. `output_pydantic`
    guarantees the shape; this checks legality and, on a violation, returns the precise error
    for a bounded retry. Returns (True, OrchestraScore) or (False, error)."""
    def guard(output: Any):
        score = _score_from_output(output)
        if score is None:
            return (False, "Return a single valid OrchestraScore JSON object and nothing else.")
        error = _orchestra_grammar_error(score, raga)
        if error:
            return (False, error)
        return (True, score)

    guard.__annotations__["return"] = tuple[bool, Any]
    return guard


# --------------------------------------------------------------------------- #
# Facts -> prompt text. Pure.                                                  #
# --------------------------------------------------------------------------- #

@lru_cache(maxsize=1)
def _orchestra_role_briefs() -> dict[str, Any]:
    """The per-SUBGENRE orchestra role briefs (`crew/config/orchestra_roles.yaml`), read once.
    Exactly ONE is injected as `{role_brief}` — the same data-driven-per-subgenre pattern as
    the lead's per-role briefs: the subgenre reconfigures the SAME agent, no new agent."""
    path = Path(__file__).parent / "config" / "orchestra_roles.yaml"
    return yaml.safe_load(path.read_text())


def _render_role_brief(subgenre: str) -> str:
    briefs = _orchestra_role_briefs()
    return briefs.get(subgenre) or briefs["default"]


def _render_raga_facts(raga: str) -> str:
    """The raga facts the orchestra must stay inside (allowed swaras, ladders, vadi, pakad,
    the direction rule) — the single source of truth, compact for the whole-chart call."""
    r = RAGAS[raga]
    lines = [
        f"  {r['display']} ({r['western_mode']}) — allowed swaras: {' '.join(r['allowed'])}",
        f"  aroha: {' '.join(r['aroha'])}   avaroha: {' '.join(r['avaroha'])}",
        f"  vadi {r['vadi']}, samvadi {r['samvadi']}",
        f"  pakad: {' | '.join(' '.join(p) for p in r['pakad'])}",
    ]
    direction = directional_varjya(raga)
    if direction:
        down = [sw for sw, d in direction.items() if d == "avaroha"]
        up = [sw for sw, d in direction.items() if d == "aroha"]
        bits = []
        if down:
            bits.append(f"{' '.join(down)} only in DESCENT")
        if up:
            bits.append(f"{' '.join(up)} only in ASCENT")
        lines.append("  direction rule: " + "; ".join(bits))
    return "\n".join(lines)


def _line_tokens(layer: Layer | None, span: SectionSpan) -> str:
    """The sounding swaras of one voice inside a section window — compact, so the orchestra
    can hear what to ANSWER (not double)."""
    if layer is None or not layer.notes:
        return "(silent)"
    toks = [(n.swara if n.oct == 0 else f"{n.swara}({n.oct:+d})")
            for n in layer.notes if span.start - 1e-6 <= n.start < span.end - 1e-6]
    return " ".join(toks) or "(silent)"


def _lead_layer(lead_layers: list[Layer]) -> Layer | None:
    return next((la for la in lead_layers if la.role == "lead"), None)


def _render_sections(arr: Arrangement, lead_layers: list[Layer], rhythm: Layer | None) -> str:
    """The form the orchestra scores over — one line per section that uses the orchestra:
    its index, kind, gat role, length, and the lead + riff it must weave around."""
    lead = _lead_layer(lead_layers)
    lines: list[str] = []
    for span in section_spans(arr):
        section = span.section
        if _SECTION_ROLE not in section.layers:
            continue
        role = section.form_role or "free"
        lines.append(
            f"  [{span.index}] {section.kind.value} (gat role: {role}), {section.bars} bar(s), "
            f"foreground {section.foreground}\n"
            f"      intent: {section.intent or '(none)'}\n"
            f"      lead here: {_line_tokens(lead, span)}\n"
            f"      riff here: {_line_tokens(rhythm, span)}")
    return "\n".join(lines) or "  (no section uses the orchestra)"


_OUTPUT_SCHEMA: Final = """{
  "reasoning": "the whole-chart arc: where the choir/brass PEAK lands, how the texture develops, what stays silent",
  "sections": [
    {"section_index": 0, "strings": "pad", "string_swaras": ["S", "P"], "brass": "silent",
     "choir": "sustained", "choir_swaras": ["S", "g"], "timpani": false,
     "swell_into_next": true, "dynamic": "mp"},
    {"section_index": 2, "strings": "tremolo", "string_swaras": ["S", "g", "P"],
     "brass": "sustain", "brass_swaras": ["S", "P"], "choir": "swell", "choir_swaras": ["S", "P"],
     "timpani": true, "swell_into_next": false, "dynamic": "ff",
     "countermelody": [{"swara": "P", "oct": 0, "dur": 1.0}, {"swara": "d", "oct": 0, "dur": 1.0},
                       {"swara": "P", "oct": 0, "dur": 2.0}]}
  ]
}
Emit ONE entry per section listed below that USES the orchestra (skip the others). "strings"
is one of pad / tremolo / counter / ostinato / silent; "brass" is stabs / sustain / silent;
"choir" is sustained / swell / silent. The *_swaras lists are RAGA swaras (leave empty to let
the code pick a default voicing). "dynamic" is pp/p/mp/mf/f/ff. Set "swell_into_next" true to
crescendo (a timpani roll) INTO the next section. "countermelody" (optional, on the strings) is
a short ANSWER line — swara + oct (0 = home, +1 up, -1 down) + dur in beats — that WEAVES around
the lead, never doubles it; use ONLY the raga's swaras."""


class _OrchestraContext:
    """Assembles the whole-chart orchestra prompt inputs. Piece-level facts render once; the
    lead/riff summary is passed per call (it changes on a revise). Pure — no I/O."""

    def __init__(self, arr: Arrangement) -> None:
        from subgenres import SUBGENRES
        from talas import TALAS
        self._arr = arr
        self._static: dict[str, Any] = {
            "raga_block": _render_raga_facts(arr.raga),
            "subgenre": SUBGENRES[arr.subgenre]["display"],
            "subgenre_feel": SUBGENRES[arr.subgenre]["feel"],
            "role_brief": _render_role_brief(arr.subgenre),
            "motif": " ".join(arr.motif),
            "bpm": arr.bpm,
            "tala": TALAS[arr.tala]["display"],
            "output_schema": _OUTPUT_SCHEMA,
        }

    def inputs_for(self, lead_layers: list[Layer], rhythm: Layer | None, *,
                   feedback: str | None = None) -> dict[str, Any]:
        return {
            **self._static,
            "sections": _render_sections(self._arr, lead_layers, rhythm),
            "repair": _render_repair(feedback),
        }


def _render_repair(feedback: str | None) -> str:
    if not feedback:
        return "  (first attempt — compose freely within the rules above)"
    return ("  YOUR PREVIOUS ATTEMPT was out of the raga. Keep the arc, and FIX this:\n"
            f"    - {feedback}")


# --------------------------------------------------------------------------- #
# The LLM crew + the injected gen_fn (so the loop tests with no LLM).           #
# --------------------------------------------------------------------------- #

class _OrchestraCrew:
    """Runs the whole-chart orchestra generation as an isolated single-agent crew — config
    read once, `output_pydantic=OrchestraScore` for the shape, the raga-bound guardrail for
    legality (mirrors `_LeadCrew`)."""

    def __init__(self) -> None:
        config_dir = Path(__file__).parent / "config"
        self._agent_config = yaml.safe_load((config_dir / "agents.yaml").read_text())["orchestra"]
        self._task_config = yaml.safe_load((config_dir / "tasks.yaml").read_text())["compose_orchestra"]

    def run(self, raga: str, inputs: dict[str, Any]) -> OrchestraScore:
        agent = Agent(config=self._agent_config, llm=generator_llm(),
                      allow_delegation=False, max_iter=GENERATOR_MAX_ITER,
                      max_retry_limit=AGENT_RETRY_LIMIT, verbose=False)
        task = Task(config=self._task_config, agent=agent, output_pydantic=OrchestraScore,
                    guardrail=_orchestra_guardrail(raga), guardrail_max_retries=GENERATOR_RETRIES)
        crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)
        score = _score_from_output(crew.kickoff(inputs=inputs))
        if score is None:
            raise ValueError("orchestra generator returned no parseable OrchestraScore")
        return score


class OrchestraFn(Protocol):
    """A score provider: given the chart plus the realized lead + riff (so the orchestra
    ANSWERS them), return the whole-chart OrchestraScore. `feedback` carries the guardrail's
    grammar violation from a failed prior attempt, so a re-roll fixes exactly that."""

    def __call__(self, arr: Arrangement, lead_layers: list[Layer], rhythm: Layer | None, *,
                 feedback: str | None = None) -> OrchestraScore: ...


class _LLMOrchestra:
    """The real (LLM-backed) `gen_fn` — holds the crew and the precomputed context."""

    def __init__(self, arr: Arrangement) -> None:
        self._crew = _OrchestraCrew()
        self._context = _OrchestraContext(arr)

    def __call__(self, arr: Arrangement, lead_layers: list[Layer], rhythm: Layer | None, *,
                 feedback: str | None = None) -> OrchestraScore:
        return self._crew.run(arr.raga, self._context.inputs_for(lead_layers, rhythm, feedback=feedback))


# --------------------------------------------------------------------------- #
# The generator — pure control flow, LLM injected via `gen_fn`.                #
# --------------------------------------------------------------------------- #

def _orchestra_event(score: OrchestraScore, layers: list[Layer]) -> DebateEvent:
    families = ", ".join(la.role.replace("orch_", "") for la in layers) or "silent"
    return DebateEvent(
        type=EventType.PROPOSE, agent="Orchestra", role=_ROLE_GENERATOR,
        text=f"orchestral score over {len(score.sections)} section(s): {families}",
        data={"reasoning": score.reasoning,
              "families": [la.role.replace("orch_", "") for la in layers]})


def generate_orchestra(arr: Arrangement, *, gen_fn: OrchestraFn,
                       lead_layers: list[Layer] = (),
                       rhythm: Layer | None = None) -> tuple[list[Layer], list[DebateEvent]]:
    """Compose the whole-chart orchestral score (ONE call) and expand it into Layers.

    A VERIFIED cell like the lead's gat cells: generate -> check the raga grammar -> if the
    score reaches outside the raga, RE-ROLL fed the exact violation, bounded (`_ORCH_REPAIR_TRIES`),
    keeping the best-of-N. The guardrail already retries inside the crew; this is the outer
    safety so the expander only ever sees a legal (or best-available) score. `gen_fn` is
    injected, so this is fully tested with no LLM. Returns ([], event) when no family sounds."""
    events: list[DebateEvent] = []
    feedback: str | None = None
    best: OrchestraScore | None = None
    for _ in range(_ORCH_REPAIR_TRIES + 1):
        score = gen_fn(arr, list(lead_layers), rhythm, feedback=feedback)
        error = _orchestra_grammar_error(score, arr.raga)
        if error is None:
            best = score
            break
        feedback = error
        if best is None:
            best = score
    assert best is not None
    # The orchestra scored from the lead as PROSE; the guide reads the same lead as pitches,
    # so a sustained pad cannot sit on a swara that grinds under what the melody settles on.
    layers = orchestra_layers_from(arr, best,
                                   guide=harmonic_guide(list(lead_layers), arr))
    events.append(_orchestra_event(best, layers))
    return layers, events


def compose_orchestra(arr: Arrangement, *, lead_layers: list[Layer] = (),
                      rhythm: Layer | None = None) -> tuple[list[Layer], list[DebateEvent]]:
    """Run the real (LLM-backed) orchestra generation for a chart — one whole-chart call,
    expanded into raga-legal Layers. The Orchestra sees the realized lead + riff so it answers
    rather than doubles them."""
    return generate_orchestra(arr, gen_fn=_LLMOrchestra(arr), lead_layers=lead_layers, rhythm=rhythm)


# --------------------------------------------------------------------------- #
# The imperative edge — a deterministic sound check (NO LLM).                  #
# --------------------------------------------------------------------------- #

def _demo_arrangement() -> Arrangement:
    """A symphonic Kirwani chart: an orchestral intro (strings + choir swelling in), the band
    entering under pads + brass stabs, and a climax (tremolo strings, choir swell, brass
    sustain, timpani) whose final avartan drops the band so the orchestra carries the peak.
    Built through the real contract; hand-authored so the sound check spends NO LLM."""
    from crew.contracts import (
        ArrangementDraft, CompositionBrief, Section, SectionKind, build_arrangement,
    )
    draft = ArrangementDraft(
        raga="kirwani", subgenre="symphonic", tala="keherwa", bpm=120,
        motif=["S", "R", "g", "m", "P"],
        sections=[
            Section(kind=SectionKind.ALAAP, bars=2, layers=["orchestra", "drone"],
                    foreground="orchestra", form_role="intro",
                    intent="the orchestra opens — strings pad, choir swelling in"),
            Section(kind=SectionKind.RIFF, bars=2, layers=["rhythm", "drums", "orchestra", "drone"],
                    foreground="rhythm", form_role="mukhada",
                    intent="the band enters; strings pad, brass stabs on the sam"),
            Section(kind=SectionKind.TAAN, bars=2,
                    layers=["rhythm", "drums", "tabla", "orchestra", "drone"],
                    foreground="rhythm", form_role="taan_long",
                    intent="the climax — tremolo strings, choir swell, brass sustain, timpani"),
        ])
    return build_arrangement(draft, CompositionBrief(mood="epic"))


def _demo_score() -> OrchestraScore:
    """A hand-authored orchestral intent for `_demo_arrangement` — exercises every family and
    an in-raga countermelody (Kirwani: S R g m P d N)."""
    return OrchestraScore(
        reasoning="Open soft (strings + choir), build under the riff, peak at the taan.",
        sections=[
            SectionOrchestra(section_index=0, strings="pad", string_swaras=["S", "P"],
                             choir="sustained", choir_swaras=["S", "g"], dynamic="mp",
                             swell_into_next=True),
            SectionOrchestra(section_index=1, strings="pad", string_swaras=["S", "g", "P"],
                             brass="stabs", brass_swaras=["S", "P"], dynamic="mf"),
            SectionOrchestra(section_index=2, strings="tremolo", string_swaras=["S", "g", "P"],
                             brass="sustain", brass_swaras=["S", "P"], choir="swell",
                             choir_swaras=["S", "P"], timpani=True, dynamic="ff",
                             countermelody=[LeadNote(swara="P", oct=0, dur=1.0),
                                            LeadNote(swara="d", oct=0, dur=1.0),
                                            LeadNote(swara="N", oct=0, dur=1.0),
                                            LeadNote(swara="P", oct=0, dur=2.0)]),
        ])


def _demo_rhythm(arr: Arrangement) -> Layer | None:
    """A plain hand-authored chugging power-chord riff (Sa), so the sound check hears the
    orchestra IN a band without spending an LLM call on the real Riff generator."""
    register = arr.registers["rhythm"]
    voice = VOICES["rhythm"]
    cycle = arr.beats_per_bar
    notes: list[Note] = []
    for span in section_spans(arr):
        if "rhythm" not in span.section.layers:
            continue
        for bar in range(span.section.bars):
            t = span.start + bar * cycle
            while t < span.start + (bar + 1) * cycle - 1e-9:
                notes.append(Note(swara="S", oct=register, start=round(t, 4), dur=0.5,
                                  vel=104, chord=["S"], technique="palm_mute"))
                t += 0.5
    if not notes:
        return None
    return Layer(role="rhythm", instrument=voice.instrument, program=voice.program,
                 channel=voice.channel, pan=voice.pan, notes=notes)


def _run() -> None:
    from crew.band import band_layers

    arr = _demo_arrangement()
    score = _demo_score()
    orchestra_layers = orchestra_layers_from(arr, score)
    rhythm = _demo_rhythm(arr)
    layers = band_layers(arr, [], rhythm, orchestra_layers)
    comp = assemble_composition(arr, layers)

    from raga import validate_composition
    payload = comp.model_dump(exclude_none=True)
    violations = validate_composition(payload)
    roles = [la.role for la in comp.layers]
    print(f"symphonic band: {len(comp.layers)} layers {roles}; "
          f"{len(violations)} grammar violation(s)")

    if shutil.which("fluidsynth") and _SOUNDFONT.exists():
        wav = render_composition(comp, out_dir=_OUT_DIR, name="orchestra_demo", soundfont=_SOUNDFONT)
        print(f"-> rendered {wav.relative_to(_ROOT)}")
    else:
        print("-> render skipped (fluidsynth or soundfont not found)")


def main(argv: list[str]) -> int:
    _run()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
