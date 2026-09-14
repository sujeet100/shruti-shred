"""
The composers (agent #2) — Pandit <-> Riffsmith, a BOUNDED dialogue that produces
the Arrangement (the shared chart).

The pattern on show: TWO AGENTS COLLABORATE TO CREATE, with OPPOSED priors. Pandit
argues for the raga's depth, Riffsmith for metal impact; they share one goal. The
tension is deliberate — two neutral agents collapse into agreement-theater with
nothing to watch. Crucially, WE own the loop: the transcript and the evolving
draft live in explicit state and we step turn-by-turn (Pandit proposes ->
Riffsmith responds -> ...), capped by `COMPOSER_TURNS`. That cap — not organic
consensus — is the guaranteed terminator (the Conductor makes the tie-break smart
in step 6; until then, the last draft stands).

Legality stays code's job: each turn's draft is validated at the boundary (the
motif must be legal in the raga) and an illegal draft is bounced back to the
composer with the precise error for ONE bounded retry. The LLM is the composer;
code only holds the hard line (legality) and derives verified facts (the tala's
accent grid), never the music.

Layering follows the repo's pure-core / imperative-shell split:
  * pure           — the `_render_*` functions and `_PromptContext` turn facts into
                     prompt text; `run_dialogue` is pure control flow over an
                     injected `turn_fn` (so the whole loop is tested with no LLM).
  * imperative     — `_ComposerCrew` / `_LLMTurns` make the actual Gemini calls.

Entry point:  uv run python -m crew.composers "a crushing dark metal fusion"
"""

from __future__ import annotations

import itertools
import sys
from collections.abc import Callable
from enum import Enum
from pathlib import Path
from typing import Any, Final, get_args

import yaml
from crewai import Agent, Crew, Process, Task
from pydantic import ValidationError

from crew.config import (
    AGENT_RETRY_LIMIT,
    COMPOSER_MAX_ITER,
    COMPOSER_RETRIES,
    COMPOSER_TURNS,
    composer_llm,
    load_env,
)
from crew.contracts import (
    ROLES,
    Arrangement,
    ArrangementDraft,
    CompositionBrief,
    ComposerTurn,
    DebateEvent,
    EventStream,
    EventType,
    FormRole,
    SectionKind,
    _LAYAS,
    build_arrangement,
    motif_illegal_in_raga,
)
from crew.interpreter import interpret
from crew.lead import render_direction_rule
from raga import RAGAS, directional_varjya
from subgenres import SUBGENRES
from talas import TALAS


class Composer(Enum):
    """One of the two composers. The value is the display name; `config_key`
    indexes the agent's entry in agents.yaml."""
    PANDIT = "Pandit"
    RIFFSMITH = "Riffsmith"

    @property
    def config_key(self) -> str:
        return self.name.lower()


# Pandit opens; then they alternate. This tuple IS the turn order.
_TURN_ORDER: Final[tuple[Composer, ...]] = (Composer.PANDIT, Composer.RIFFSMITH)

# DebateEvent role for a composer turn (the others: "system", "critic", ...).
_ROLE_COMPOSER: Final = "composer"
_ROLE_SYSTEM: Final = "system"

# One-line meaning per section kind — the composer's vocabulary. Keyed by enum
# value so a new SectionKind without a description fails loud here (KeyError in
# `_render_section_kinds`) rather than silently shipping an undocumented kind.
_SECTION_DESC: Final[dict[str, str]] = {
    "alaap": "slow, unmetered raga exposition; lead-led, usually no drums",
    "riff": "the main metal riff statement; rhythm-led",
    "melody": "the motif sung as a theme over the groove",
    "taan": "fast, virtuosic melodic run — the climax",
    "solo": "lead improvisation over the riff",
    "breakdown": "heavy, sparse rhythm + drums crush",
    "outro": "cadential resolution",
}

# A section that rests the lead may run at most this many avartans — riff-only interludes
# are a short contrast; the gat must never vanish for long (enforced by the guardrail).
_MAX_LEADLESS_BARS: Final = 2
# ...and the whole form gets at most this many of them: one instrumental interlude is a
# contrast, a second is a hole in the gat (Sujit cut the second bridge/breakdown outright).
_MAX_LEADLESS_SECTIONS: Final = 1
# The mukhada RETURN right after a manjha must run at least this many avartans, so the head
# re-establishes itself before a riff interlude or anything else takes over.
_MIN_RETURN_BARS: Final = 2
# The intro/alap needs room to establish Sa and the raga (the aochar unfolds in phrases with
# real silence between them) — a 2-avartan intro was heard as rushed (Sujit, 2026-07-15).
_MIN_INTRO_BARS: Final = 3

# One-line meaning per gat FORM role. Keyed by the FormRole value so a new role without a
# description fails loud in `_render_form_roles` (KeyError) rather than shipping undocumented.
_FORM_DESC: Final[dict[str, str]] = {
    "intro": "opening — reveal the raga over the drone before the gat (an aochar/alap); give "
             "it at least 3 avartans so it can breathe",
    "mukhada": "the GAT HOOK — the recurring melodic+rhythmic head that resolves to the sam; "
               "STATE it early, then RETURN to it (mark the return 'mukhada' too)",
    "manjha": "the LOWER-register bridge (majh/manjha, part of the sthayi) — a SHORT, calm line "
              "that takes the melody DOWN into the mandra octave (the antara owns the taar); the "
              "mukhada must re-enter IMMEDIATELY after it (head -> manjha -> head, one cohesive cycle)",
    "antara": "the second theme — lifts into the higher (taar) octave",
    "taan_short": "a short cadential taan filler (half/one cycle) that resolves into the next mukhada",
    "taan_long": "the developed taan — the SITAR's peak; place it after the antara or before the final mukhada. The climax belongs to the sitar: build it with a LONG taan, or with back-to-back taan sections that accelerate into each other, rather than handing the melody to another instrument. By DEFAULT the band DRIVES it (sustained rhythm chords + climax drums under the taan, the lead guitar joining in unison only for the final avartan); set climax_style 'exposed' only when you want a short exposed breath (a few matras) before the re-entry sam — code thins the band there; it is a held breath, not a cycle without the band",
    "breakdown": "a heavy, sparse rhythmic climax",
    "tihai": "a phrase stated thrice, landing on the sam — a cadence",
    "outro": "settle back down to a held Sa",
}

# One-line meaning per LAYER role (the voices). Keyed by role so a new ROLE without
# a description fails loud in `_render_layers`. Note tabla + drums may coexist.
_LAYER_DESC: Final[dict[str, str]] = {
    "lead": "the melodic voice (sitar-like lead / lead guitar) — the raga line, taans, solos",
    "rhythm": "the metal rhythm guitar — downtuned riffs and power chords",
    "drums": "the metal drum kit (kick/snare/cymbals) — the metal groove",
    "tabla": "Hindustani tabla — lays the tala's theka; may play ALONGSIDE the metal drums. Currently MUTED at render (it does not yet respond to the section it is under), so do not build a section around it",
    "drone": "the tanpura drone — a sustained Sa+Pa pad anchoring the tonality",
    "clean": "the CLEAN electric guitar — arpeggiates the section's harmony plan (a shimmer "
             "under the band): intros, under a melody, a breakdown afterglow; it holds ringing "
             "pads under the long taan (driving the climax; it sits out only an 'exposed' taan's "
             "band-drop)",
    "orchestra": "the ORCHESTRA (strings, brass, choir, timpani) — a CINEMATIC layer a separate "
                 "agent scores. ACTIVATE it throughout a SYMPHONIC chart (there it is a full, "
                 "equal member of the band), and only SPARINGLY as colour on other subgenres (a "
                 "string pad under a chorus, a brass stab, a choir at the climax). You just list "
                 "the layer where you want cinematic depth; the orchestra agent decides what each "
                 "family plays and reserves the big tutti for the peak",
}

# The exact JSON shape we want back, injected as an input so CrewAI's {placeholder}
# interpolation never has to parse these literal braces.
_OUTPUT_SCHEMA: Final = """{
  "reasoning": "your private monologue: one thing you respect in your counterpart's last turn, one you push back on",
  "draft": {
    "raga": "malkauns",
    "subgenre": "doom",
    "tala": "teentaal",
    "bpm": 72,
    "anchor": "gat_first",
    "motif": ["d", "n", "S", "m"],
    "sections": [
      {"kind": "alaap", "form_role": "intro", "bars": 2, "layers": ["lead", "clean", "drone"], "foreground": "lead", "harmony": {"mode": "drone"}, "intent": "unfold the raga slowly; clean guitar breaks the drone dyad gently", "transition": "tabla settles into the theka"},
      {"kind": "melody", "form_role": "mukhada", "bars": 4, "layers": ["lead", "rhythm", "drums", "tabla", "drone"], "foreground": "lead", "riff_slot": "main", "harmony": {"mode": "modal_pedal"}, "intent": "state the gat hook on the sitar; the riff answers it as a rhythmic reduction", "transition": "a shared tihai lands on the sam into the breakdown"},
      {"kind": "breakdown", "form_role": "breakdown", "bars": 2, "layers": ["rhythm", "drums", "drone"], "foreground": "rhythm", "riff_slot": "breakdown", "intent": "half-time crush on the komal notes", "transition": "feedback swells; the mukhada returns"},
      {"kind": "riff", "form_role": "mukhada", "bars": 4, "layers": ["lead", "rhythm", "drums", "clean", "drone"], "foreground": "rhythm", "riff_slot": "main", "harmony": {"mode": "progression", "roots": ["S", "m", "d", "S"]}, "intent": "bring the mukhada hook back, full band, the clean arpeggio cycling home", "transition": "ring out"}
    ],
    "registers": {"lead": 0, "rhythm": -3, "drone": -3}
  },
  "note": "one or two sentences arguing your change, in character",
  "agree": false
}
"reasoning" comes FIRST. "registers" is OPTIONAL — omit it to use sensible defaults. "intent" and "transition" are short free-text hints and may be empty.
"harmony" (OPTIONAL per section) is how the section MOVES under the melody: {"mode": "drone"} (no motion — the tanpura dyad; alaap and climax territory), {"mode": "modal_pedal", "roots": [...]} (the DEFAULT — a Sa pedal under changing colour tones; roots = the colours, empty = the raga's vadi/samvadi), or {"mode": "progression", "roots": [...]} (a short per-avartan chord-root cycle for a CHORUS-like section: 2-4 raga swaras, the LAST one "S" so the cycle comes home). Activate the "clean" layer wherever this harmony should be HEARD as arpeggios.
"climax_style" (OPTIONAL, only meaningful on the "taan_long" peak): "driven" (the DEFAULT — the metal-solo climax: sustained rhythm chords + climax drums DRIVE the peak while the sitar/guitar taan trades over them) or "exposed" (the alap-style reveal — the band drops out of the taan's final avartan, sitar + tabla carrying it alone). Prefer "driven" for a metal-leaning peak; reserve "exposed" for a deliberately spacious, classical reveal.
"anchor" is the ONE idea the whole piece derives from: "gat_first" (the sitar mukhada is the source; the riff is a rhythmic reduction of it) or "riff_first" (the riff is the source; the mukhada quotes its accented notes).
Set "form_role" on EVERY section — its place in the gat form (intro/mukhada/manjha/antara/taan_short/taan_long/breakdown/tihai/outro). The MUKHADA is the hook: STATE it and RETURN to it — mark at least TWO sections "mukhada" (above, the last section is the mukhada coming back). The CLIMAX IS THE SITAR'S: build it with a long "taan_long", or with back-to-back taan sections (a "taan_short" running straight into the "taan_long", or two consecutive taans) that accelerate into the peak — do NOT give another instrument a solo section to share the spotlight. At most TWO "taan_long" sections, and only back-to-back if you use two. A MANJHA must sit between mukhada statements — place a "mukhada" section IMMEDIATELY after every "manjha" (head -> manjha -> head, one cohesive cycle), and give that returning mukhada at least 2 bars so the head re-establishes itself. The whole form gets AT MOST ONE section that RESTS the lead (riff-only/breakdown), no longer than 2 bars — the gat is the star and must never vanish for long.
Every rhythm section needs a "riff_slot" naming which riff it plays — "main"/"chorus"/"breakdown". Sections that SHARE a slot replay the SAME riff, so REUSE "main" wherever the mukhada/main riff returns, and give the chorus/breakdown their OWN slots to contrast. Lead-only sections need no slot."""


# --------------------------------------------------------------------------- #
# Pure renderers: FACTS (raga/tala/subgenre data) -> prompt text. Never inline #
# prose — the single source of truth stays in raga.py / talas.py / subgenres.py.#
# --------------------------------------------------------------------------- #

def _render_brief(brief: CompositionBrief) -> str:
    """Spell out what the user FIXED (honor exactly) vs. what is OPEN (compose)."""
    lines = [
        f"  raga: FIXED = {brief.raga} (use this raga)" if brief.raga
        else "  raga: OPEN — you choose (let the mood guide you)",
        f"  subgenre: FIXED = {brief.subgenre}" if brief.subgenre
        else "  subgenre: OPEN — you choose",
        f"  key/Sa: FIXED = {brief.key} (Sa={brief.sa})" if brief.key
        else "  key/Sa: OPEN — a sensible default is applied",
        f"  bpm: FIXED = {brief.bpm}" if brief.bpm else "  bpm: OPEN — you choose",
        f"  tala: FIXED = {brief.tala} (use this rhythmic cycle)" if brief.tala
        else "  tala: OPEN — you choose the rhythmic cycle",
    ]
    if brief.laya:
        lines.append(f"  laya: FIXED = {brief.laya} ({_LAYAS[brief.laya]})")
    if brief.mood:
        lines.append(f"  mood to honor: {brief.mood}")
    if brief.instruments:
        lines.append(f"  instruments the user mentioned: {', '.join(brief.instruments)}")
    return "\n".join(lines)


def _render_raga_line(key: str) -> str:
    r = RAGAS[key]
    return (f"  - {key}: {r['display']} — {r['western_mode']}; "
            f"allowed swaras: {' '.join(r['allowed'])}; vadi {r['vadi']}, samvadi {r['samvadi']}; "
            f"{r['samay']}")


def _render_raga_block(key: str) -> str:
    """Full facts for a FIXED raga — enough to compose idiomatically."""
    r = RAGAS[key]
    lines = [
        _render_raga_line(key),
        f"    aroha: {' '.join(r['aroha'])}   avaroha: {' '.join(r['avaroha'])}",
        f"    pakad: {' | '.join(' '.join(p) for p in r['pakad'])}",
        f"    chalan: {' | '.join(' '.join(p) for p in r['chalan'])}",
    ]
    if r.get("andolan"):
        lines.append(f"    andolan (swaras that oscillate — idiomatic): {' '.join(r['andolan'])}")
    direction = directional_varjya(key)
    if direction:
        lines.append(f"    direction rule — {render_direction_rule(direction)}")
    return "\n".join(lines)


def _render_ragas(brief: CompositionBrief) -> str:
    """The fixed raga's full facts, or a compact line for each supported raga."""
    if brief.raga:
        return _render_raga_block(brief.raga)
    return "\n".join(_render_raga_line(key) for key in RAGAS)


def _render_talas() -> str:
    lines = []
    for key, t in TALAS.items():
        vibhags = "+".join(str(v) for v in t["vibhags"])
        lines.append(f"  - {key}: {t['display']} — {t['matras']} matras in {vibhags}; "
                     f"sam {t['sam']}, tali {t['tali']}, khali {t['khali']}")
    return "\n".join(lines)


def _render_subgenre_line(key: str) -> str:
    s = SUBGENRES[key]
    lo, hi = s["bpm"]
    reg_lo, reg_hi = s["register"]
    return (f"  - {key}: {s['display']} — {lo}-{hi} bpm; {s['feel']}; "
            f"register octaves [{reg_lo}, {reg_hi}] (lower = heavier)\n"
            f"      how it grooves: {s['groove_brief']}")


def _render_subgenres(brief: CompositionBrief) -> str:
    if brief.subgenre:
        return _render_subgenre_line(brief.subgenre)
    return "\n".join(_render_subgenre_line(key) for key in SUBGENRES)


def _render_section_kinds() -> str:
    return "\n".join(f"  - {kind.value}: {_SECTION_DESC[kind.value]}" for kind in SectionKind)


def _render_form_roles() -> str:
    # Iterate the FormRole Literal itself so a role added there without a description
    # fails loud here (KeyError), never ships undocumented.
    return "\n".join(f"  - {role}: {_FORM_DESC[role]}" for role in get_args(FormRole))


def _render_layers() -> str:
    return "\n".join(f"  - {role}: {_LAYER_DESC[role]}" for role in sorted(ROLES))


def _render_pakad_seeds(brief: CompositionBrief) -> str:
    keys = [brief.raga] if brief.raga else list(RAGAS)
    return "\n".join(f"  - {key}: {' '.join(phrase)}"
                     for key in keys for phrase in RAGAS[key]["pakad"])


def _render_transcript(transcript: list[tuple[str, str]]) -> str:
    if not transcript:
        return "  (nothing yet — you are speaking first)"
    return "\n".join(f"  {who}: {note}" for who, note in transcript)


def _section_line(s) -> str:
    """One section in the draft summary — its form role, kind, length, voices, foreground, and
    (for a rhythm section) its riff slot, so the counterpart can align on the same gat + riffs."""
    role = f"{s.form_role}:" if s.form_role else ""
    slot = f", riff={s.riff_slot}" if s.riff_slot else ""
    harm = f", harm={s.harmony.mode}" if s.harmony else ""
    return f"{role}{s.kind.value}[{s.bars}b, {'+'.join(s.layers)}, fg={s.foreground}{slot}{harm}]"


def _render_draft(draft: ArrangementDraft | None) -> str:
    if draft is None:
        return "  (no draft yet — propose one)"
    sections = "; ".join(_section_line(s) for s in draft.sections)
    registers = f"\n  registers: {draft.registers}" if draft.registers else ""
    return (f"  raga={draft.raga}, subgenre={draft.subgenre}, tala={draft.tala}, "
            f"bpm={draft.bpm}, anchor={draft.anchor}\n"
            f"  motif: {' '.join(draft.motif)}\n"
            f"  sections: {sections}{registers}")


def _render_arrangement(arr: Arrangement) -> str:
    # Show the gat form (form_role where set, else the render kind) so the arc reads at a glance.
    form = " -> ".join(s.form_role or s.kind.value for s in arr.sections)
    return (f"{arr.raga} x {arr.subgenre} in {arr.tala} @ {arr.bpm}bpm (Sa={arr.sa}); "
            f"anchor {arr.anchor}; motif {' '.join(arr.motif)}; form: {form}")


def _draft_summary(draft: ArrangementDraft) -> dict[str, Any]:
    """A compact draft snapshot for the DebateEvent payload the UI renders."""
    return {"raga": draft.raga, "subgenre": draft.subgenre, "tala": draft.tala,
            "bpm": draft.bpm, "anchor": draft.anchor, "motif": draft.motif,
            "sections": [s.kind.value for s in draft.sections],
            "form": [s.form_role for s in draft.sections]}


class _PromptContext:
    """Assembles a composer turn's prompt inputs from the facts.

    The brief-derived context (what's fixed vs. open, the raga/subgenre/seed facts)
    is CONSTANT across a dialogue, so it is rendered ONCE at construction; only the
    turn number, transcript and evolving draft change per turn. Pure — no I/O.
    """

    def __init__(self, brief: CompositionBrief, *, max_turns: int) -> None:
        self._static: dict[str, Any] = {
            "max_turns": max_turns,
            "brief_context": _render_brief(brief),
            "raga_context": _render_ragas(brief),
            "tala_context": _render_talas(),
            "subgenre_context": _render_subgenres(brief),
            "section_kinds": _render_section_kinds(),
            "form_roles": _render_form_roles(),
            "layer_roles": _render_layers(),
            "seed_context": _render_pakad_seeds(brief),
            "output_schema": _OUTPUT_SCHEMA,
        }

    def inputs_for(self, speaker: Composer, turn_no: int, draft: ArrangementDraft | None,
                   transcript: list[tuple[str, str]]) -> dict[str, Any]:
        return {
            **self._static,
            "composer": speaker.value,
            "turn_no": turn_no,
            "transcript": _render_transcript(transcript),
            "current_draft": _render_draft(draft),
        }


# --------------------------------------------------------------------------- #
# Boundary parsing + the guardrail (the hard legality line). Imperative-ish.   #
# --------------------------------------------------------------------------- #

def _turn_from_output(output: Any) -> ComposerTurn | None:
    """The ComposerTurn CrewAI parsed via output_pydantic (or None if parsing failed)."""
    parsed = getattr(output, "pydantic", None)
    if isinstance(parsed, ComposerTurn):
        return parsed
    raw = getattr(output, "raw", None)
    try:
        return ComposerTurn.model_validate_json(raw) if raw else None
    except ValidationError:
        return None


# A progression is a CHORUS device: on the melodic-gravity sections (the alap, the
# taan's climax, the settling outro) harmony must stay a drone or pedal — a root cycle
# there would fight Sa's pull, the musical-accuracy red line of the harmony design.
# The climax is the SITAR's, and it is allowed to be BIG: a long taan, or two taans running
# into each other (Sujit, 2026-09-14 — "long sitar taans or back-to-back taans to build the
# climax", replacing the guitar solo that used to interrupt the arc). Two is the cap: a third
# stops being a climb and becomes the piece.
_MAX_TAAN_LONG: Final = 2

_NO_PROGRESSION_ROLES: Final = frozenset({"intro", "taan_long", "outro"})
_PROGRESSION_MIN_ROOTS: Final = 2
_PROGRESSION_MAX_ROOTS: Final = 4


def _harmony_error(draft) -> str | None:
    """The harmony rules the schema can't hold (the raga is only known here): every root
    a legal raga swara; a PROGRESSION is 2-4 roots resolving to Sa, on a chorus-like
    section only, with no descent-only swara as a harmonic centre (a tone the raga only
    brushes on the way down cannot carry a chord)."""
    from raga import directional_varjya
    restricted = directional_varjya(draft.raga)
    allowed = " ".join(RAGAS[draft.raga]["allowed"])
    for i, s in enumerate(draft.sections):
        plan = s.harmony
        if plan is None:
            continue
        where = f"section #{i + 1} ({s.kind.value})"
        illegal = motif_illegal_in_raga(plan.roots, draft.raga)
        if illegal:
            return (f"harmony roots {illegal} in {where} are illegal in raga "
                    f"{draft.raga}. Use only these swaras: {allowed}. Fix and resend.")
        if plan.mode == "progression":
            if s.form_role in _NO_PROGRESSION_ROLES:
                return (f"{where} is a {s.form_role} — a progression there fights Sa's "
                        f"melodic gravity. Use 'drone' or 'modal_pedal' on intro/"
                        f"taan_long/outro sections; save progressions for chorus-like "
                        f"sections. Fix and resend.")
            if not (_PROGRESSION_MIN_ROOTS <= len(plan.roots) <= _PROGRESSION_MAX_ROOTS):
                return (f"a progression needs {_PROGRESSION_MIN_ROOTS}-"
                        f"{_PROGRESSION_MAX_ROOTS} roots ({where} has {len(plan.roots)}). "
                        f"Fix and resend.")
            if plan.roots[-1] != "S":
                return (f"the progression in {where} must RESOLVE: its last root is "
                        f"'{plan.roots[-1]}', not 'S' — the cycle comes home to Sa. "
                        f"Fix and resend.")
            bad_roots = sorted({r for r in plan.roots if restricted.get(r) == "avaroha"})
            if bad_roots:
                return (f"root(s) {bad_roots} in {where} are DESCENT-only swaras in "
                        f"{draft.raga} — a tone the raga only brushes on the way down "
                        f"cannot carry a chord. Pick roots the raga dwells on. Fix and "
                        f"resend.")
    return None


def _validate_turn(output: Any):
    """Task guardrail — the domain rules kept out of the schema: (1) the composer's motif
    must be legal in its raga, (2) every rhythm section must NAME a riff_slot (so the reuse
    that makes the main riff a hook is deliberate), and (3) the GAT FORM must hold — every
    section carries a form_role, a MUKHADA is stated AND returns, and at most one section is
    a long taan. Code guards only this checkable STRUCTURE; the melodic realisation (what the
    mukhada IS, how the riff reduces from it) stays the composers' creative call.
    `output_pydantic` already guarantees the SHAPE; this checks the raga grammar and the
    song-form rules and, on a violation, returns the precise error so CrewAI re-runs the
    turn (a bounded retry).

    Contract: returns (True, ComposerTurn) or (False, error-message). CrewAI inspects
    this guardrail's RETURN ANNOTATION and requires the literal object tuple[bool, Any];
    this module's `from __future__ import annotations` would stringify a normal hint
    and CrewAI rejects the string — so it is attached as a real object below the def.
    """
    turn = _turn_from_output(output)
    if turn is None:
        return (False, "Return a single valid ComposerTurn JSON object and nothing else.")
    illegal = motif_illegal_in_raga(turn.draft.motif, turn.draft.raga)
    if illegal:
        allowed = " ".join(RAGAS[turn.draft.raga]["allowed"])
        return (False, f"motif swaras {illegal} are illegal in raga {turn.draft.raga}. "
                       f"Use only these swaras: {allowed}. Fix the motif and resend.")
    # Song form: every rhythm section must NAME its riff (a slot), so the reuse that makes
    # the main riff a recurring hook is a deliberate choice, not an accident of the kind.
    unslotted = [f"#{i + 1} {s.kind.value}" for i, s in enumerate(turn.draft.sections)
                 if "rhythm" in s.layers and not s.riff_slot]
    if unslotted:
        return (False, "Every rhythm section needs a riff_slot naming which riff it plays "
                       "('main'/'chorus'/'breakdown'); sections that share a slot replay the "
                       "same riff, so reuse 'main' wherever the main riff returns. Add a "
                       f"riff_slot to section(s): {', '.join(unslotted)}. Fix and resend.")
    # Gat form: every section declares its place in the form, and the MUKHADA (the gat hook)
    # is stated AND returns — a recurring hook is what turns a loop into a song.
    roleless = [f"#{i + 1} {s.kind.value}" for i, s in enumerate(turn.draft.sections)
                if not s.form_role]
    if roleless:
        return (False, "Every section needs a form_role naming its place in the gat form "
                       "(intro/mukhada/manjha/antara/taan_short/taan_long/breakdown/tihai/outro). "
                       f"Add one to section(s): {', '.join(roleless)}. Fix and resend.")
    if sum(s.form_role == "mukhada" for s in turn.draft.sections) < 2:
        return (False, "The gat needs a MUKHADA that RETURNS: mark the recurring hook 'mukhada' "
                       "where it is first stated AND again where it comes back (at least two "
                       "sections). Add the mukhada return and resend.")
    if sum(s.form_role == "taan_long" for s in turn.draft.sections) > _MAX_TAAN_LONG:
        return (False, f"The climax is the sitar's, but it is a CLIMB, not the piece: at most "
                       f"{_MAX_TAAN_LONG} sections may be 'taan_long' (back-to-back is fine — "
                       f"that is how you build a peak without handing the melody to another "
                       f"instrument). Use 'taan_short' for cadential fillers. Fix and resend.")
    # The intro/alap needs room to breathe — the aochar establishes Sa and the raga in phrases
    # separated by real silence, and code reserves a further pause at its end.
    short_intro = [f"#{i + 1}" for i, s in enumerate(turn.draft.sections)
                   if s.form_role == "intro" and s.bars < _MIN_INTRO_BARS]
    if short_intro:
        return (False, f"The intro/alap needs at least {_MIN_INTRO_BARS} avartans to establish "
                       f"Sa and the raga before the gat enters — lengthen section(s) "
                       f"{', '.join(short_intro)} and resend.")
    # The manjha is the head's COMPLEMENT, not a detour: it may only appear once the mukhada
    # has been stated, and the mukhada must re-enter IMMEDIATELY after it — head x3-4, manjha
    # carries the line to the sam, head again: one cohesive cycle.
    roles = [s.form_role for s in turn.draft.sections]
    first_mukhada = roles.index("mukhada")
    bad_manjha = [f"#{i + 1}" for i, role in enumerate(roles) if role == "manjha"
                  and (i < first_mukhada or i + 1 >= len(roles) or roles[i + 1] != "mukhada")]
    if bad_manjha:
        return (False, "A manjha DEVELOPS the mukhada and must RETURN to it: place every manjha "
                       "AFTER the mukhada is first stated, with a mukhada section IMMEDIATELY "
                       "after it (mukhada -> manjha -> mukhada, one cohesive cycle). Fix "
                       f"section(s) {', '.join(bad_manjha)} and resend.")
    # The RETURN after a manjha must establish itself: at least two avartans of the head
    # before anything else takes over (Sujit: "after manjha, 2 loops of mukhada again
    # before only-riff kicks in").
    short_return = [f"#{i + 2}" for i, role in enumerate(roles) if role == "manjha"
                    and i + 1 < len(roles) and turn.draft.sections[i + 1].bars < _MIN_RETURN_BARS]
    if short_return:
        return (False, f"The mukhada RETURN after a manjha needs at least {_MIN_RETURN_BARS} "
                       f"avartans — the head must re-establish itself before anything else "
                       f"takes over. Lengthen section(s) {', '.join(short_return)} and resend.")
    # Riff-only interludes are a CONTRAST, not a second act: without the lead the gat vanishes,
    # so any section that rests the lead stays short (the first live render left the sitar
    # silent for 8 avartans mid-piece — the form lost its thread), and the piece gets at most
    # ONE such interlude (a second bridge/breakdown gap kills the gat's momentum — Sujit).
    long_leadless = [f"#{i + 1} {s.kind.value}" for i, s in enumerate(turn.draft.sections)
                     if "lead" not in s.layers and s.bars > _MAX_LEADLESS_BARS]
    if long_leadless:
        return (False, f"Keep lead-less (riff-only) sections SHORT — at most {_MAX_LEADLESS_BARS} "
                       f"avartans each; the gat is the star and must never vanish for long. "
                       f"Shorten or add the lead to section(s): {', '.join(long_leadless)} "
                       f"and resend.")
    leadless = [f"#{i + 1} {s.kind.value}" for i, s in enumerate(turn.draft.sections)
                if "lead" not in s.layers]
    if len(leadless) > _MAX_LEADLESS_SECTIONS:
        return (False, f"At most {_MAX_LEADLESS_SECTIONS} lead-less (riff-only) section in the "
                       f"whole form — one instrumental interlude is a contrast, a second is a "
                       f"hole in the gat. Add the lead to (or merge/cut) some of: "
                       f"{', '.join(leadless)} and resend.")
    harmony_error = _harmony_error(turn.draft)
    if harmony_error:
        return (False, harmony_error)
    return (True, turn)


_validate_turn.__annotations__["return"] = tuple[bool, Any]


class _ComposerCrew:
    """Runs ONE composer turn as an isolated, single-agent crew.

    We own the loop, so each turn is an explicit call with the shared state injected
    as inputs — not CrewAI's autonomous delegation. Structured output is CrewAI's job
    (`output_pydantic=ComposerTurn`), so there is no hand-rolled JSON parsing; the
    guardrail adds only the domain (legality) check. Config is read once at construction.
    """

    def __init__(self) -> None:
        config_dir = Path(__file__).parent / "config"
        self._agent_configs = yaml.safe_load((config_dir / "agents.yaml").read_text())
        self._task_config = yaml.safe_load((config_dir / "tasks.yaml").read_text())["compose_turn"]

    def run(self, speaker: Composer, inputs: dict[str, Any]) -> ComposerTurn:
        task = self._build_task(speaker)
        crew = Crew(agents=[task.agent], tasks=[task], process=Process.sequential, verbose=False)
        result = crew.kickoff(inputs=inputs)
        turn = _turn_from_output(result)
        if turn is None:
            raise ValueError(f"composer {speaker.value} returned no parseable ComposerTurn")
        return turn

    def _build_task(self, speaker: Composer) -> Task:
        # allow_delegation=False: WE drive the turn order, not autonomous delegation.
        # max_iter: a modest per-turn circuit-breaker beneath our across-turn cap.
        # output_pydantic: CrewAI parses+validates the SHAPE into a ComposerTurn;
        # the guardrail adds the raga-legality domain check with a bounded retry.
        agent = Agent(config=self._agent_configs[speaker.config_key], llm=composer_llm(),
                      allow_delegation=False, max_iter=COMPOSER_MAX_ITER,
                      max_retry_limit=AGENT_RETRY_LIMIT, verbose=False)
        return Task(config=self._task_config, agent=agent, output_pydantic=ComposerTurn,
                    guardrail=_validate_turn, guardrail_max_retries=COMPOSER_RETRIES)


# A turn provider: given the speaker and the shared state, return their turn.
type TurnFn = Callable[[Composer, ArrangementDraft | None, list[tuple[str, str]]], ComposerTurn]


class _LLMTurns:
    """The real (LLM-backed) `turn_fn`. Holds the crew and the precomputed prompt
    context across the dialogue's turns."""

    def __init__(self, brief: CompositionBrief, *, max_turns: int) -> None:
        self._crew = _ComposerCrew()
        self._context = _PromptContext(brief, max_turns=max_turns)

    def __call__(self, speaker: Composer, draft: ArrangementDraft | None,
                 transcript: list[tuple[str, str]]) -> ComposerTurn:
        turn_no = len(transcript) + 1
        return self._crew.run(speaker, self._context.inputs_for(speaker, turn_no, draft, transcript))


# --------------------------------------------------------------------------- #
# The bounded dialogue loop — pure control flow, LLM injected via `turn_fn`.    #
# The DebateEvent builders below keep the loop body about CONTROL, not wording. #
# --------------------------------------------------------------------------- #

_OPENING_ROUND: Final = 1  # round 1 is a proposal; there is nothing yet to argue with


def _system_event(text: str, *, round_no: int | None = None) -> DebateEvent:
    return DebateEvent(type=EventType.INFO, agent="System", role=_ROLE_SYSTEM,
                       text=text, round=round_no)


def _turn_event(speaker: Composer, turn: ComposerTurn, round_no: int) -> DebateEvent:
    kind = EventType.PROPOSE if round_no == _OPENING_ROUND else EventType.DEBATE
    return DebateEvent(type=kind, agent=speaker.value, role=_ROLE_COMPOSER,
                       text=turn.note, round=round_no,
                       data={"draft": _draft_summary(turn.draft), "reasoning": turn.reasoning})


def _agreement_event(speaker: Composer, round_no: int) -> DebateEvent:
    return DebateEvent(type=EventType.INFO, agent=speaker.value, role=_ROLE_COMPOSER,
                       text="agrees — the chart serves both sides.", round=round_no)


def run_dialogue(brief: CompositionBrief, *, turn_fn: TurnFn,
                 max_turns: int = COMPOSER_TURNS) -> tuple[Arrangement, list[DebateEvent]]:
    """Step Pandit and Riffsmith turn-by-turn to a shared Arrangement.

    Bounded and always-terminating: it stops when a RESPONDING composer AGREES, or
    when the turn cap is hit (the guaranteed terminator — the Conductor makes the
    un-agreed tie-break smart in step 6; here the last draft stands). Emits a
    DebateEvent per turn (the streamed transcript) plus setup/verdict INFO events.
    `turn_fn` is injected so the loop is tested with no LLM.
    """
    if max_turns < 1:
        raise ValueError("max_turns must be at least 1")

    events = [_system_event(f"Composers open on brief: {_render_brief(brief).strip()}")]
    transcript: list[tuple[str, str]] = []
    draft: ArrangementDraft | None = None
    speakers = itertools.cycle(_TURN_ORDER)  # Pandit opens, then they alternate
    agreed = False

    for round_no in range(_OPENING_ROUND, max_turns + 1):
        speaker = next(speakers)
        turn = turn_fn(speaker, draft, list(transcript))
        draft = turn.draft
        transcript.append((speaker.value, turn.note))
        events.append(_turn_event(speaker, turn, round_no))

        if turn.agree and round_no > _OPENING_ROUND:  # an opener has nothing to agree with
            agreed = True
            events.append(_agreement_event(speaker, round_no))
            break

    if not agreed:
        events.append(_system_event(
            f"Turn cap ({max_turns}) reached — last draft stands "
            f"(the Conductor will arbitrate in step 6).", round_no=len(transcript)))

    arrangement = build_arrangement(draft, brief)  # draft is set: max_turns >= 1
    events.append(_system_event(f"Arrangement: {_render_arrangement(arrangement)}"))
    return arrangement, events


def compose(brief: CompositionBrief, *,
            max_turns: int = COMPOSER_TURNS) -> tuple[Arrangement, list[DebateEvent]]:
    """Run the real (LLM-backed) composer dialogue for a brief."""
    return run_dialogue(brief, turn_fn=_LLMTurns(brief, max_turns=max_turns), max_turns=max_turns)


def _run(query: str) -> None:
    """Interpret the query, run the composer dialogue, stream both event sets."""
    stream = EventStream()
    brief, intake_events = interpret(query)
    for event in intake_events:
        stream.emit(event)
    _, dialogue_events = compose(brief)
    for event in dialogue_events:
        stream.emit(event)


def main(argv: list[str]) -> int:
    load_env()  # entry point loads .env
    query = " ".join(argv) or "a crushing, dark metal fusion"
    # Trace by default — every live run is captured for the portal (RMA_TRACE=0 opts out).
    from contextlib import nullcontext

    from crew.tracing import traced, tracing_enabled
    ctx = traced(query) if tracing_enabled() else nullcontext()
    with ctx:
        _run(query)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
