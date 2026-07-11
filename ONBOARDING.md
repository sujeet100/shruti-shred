# Onboarding — Shruti Shred

*Start here. This is the handoff map; the authoritative rules live in `CLAUDE.md`,
the roadmap in `PLAN.md`, the agent architecture in `DESIGN.md`, and the talk
narrative in `TALK.md`.*

## What this is

A conference-talk demo that **teaches agentic-AI patterns** by composing
**Hindustani-classical × metal** fusion live. The audience picks a raga + metal
subgenre; a small crew of LLM agents interprets the request, argues out an
arrangement, (eventually) generates and critiques the parts, and renders to audio.
The two theses: **constraints make agents creative**, and **hard guardrails (code) +
soft taste (LLM)** — knowing which is which is the skill.

The name: **shruti** (the microtones *between* the notes — the finest thing in
Hindustani music) × **shred** (metal's loudest gesture). It's also technically apt —
the renderer bends pitch to voice *meend* (glides).

## Where things stand (2026-07-11)

- **Phase 0** (render pipeline) and **Phase 1** (knowledge core: 5 ragas, 6 talas, 4
  subgenres, all source-verified and tested) — **done**.
- **Phase 2** (agents) — in progress:
  - **Agent #1 Interpreter** — done. Query → validated `CompositionBrief`.
  - **Agent #2 Pandit ⇄ Riffsmith composers** — done. Brief → `Arrangement` chart via a
    bounded turn-by-turn debate.
  - **Agent #3 generators + full-band assembly** — done. Chart → every voice → `Composition`
    → WAV (`out/full_band.wav`). Only **Lead** (sitar/lead-guitar voicing) and **Riff** are
    LLM; **Drone, Bass, Drums, Tabla** are deterministic. `crew/band.py` assembles.
  - **Agent #4 Ustad (legality critic)** — done. `Composition` → `UstadVerdict` (legal/illegal
    + violations). Code owns the verdict via `validate_composition`; the LLM only narrates it
    (`crew/ustad.py`). Same validator is the generator guardrail AND Ustad's explain-tool.
  - **Agent #5 Rasik (taste critic)** — done. `Composition` → `RasikVerdict` (a fixed 1-5
    rubric: pakad/idiom/mood/coherence + notes). The OPPOSITE of Ustad — taste is not
    checkable, so the LLM owns the verdict; it's disciplined by the rubric + encoded-fact
    grounding + a code-computed pakad hint (`crew/rasik.py`).
  - **Local tracing + portal + eval harness** — done (on by default).
- **NEXT → step 6 (Conductor + the Flow)**: on an Ustad↔Rasik conflict, run the bounded debate
  and rule accept / surgical-revise; also wires the deferred foreground leader/follower
  seeding. See "The next task" below.

## Quickstart

```bash
uv run python tests/test_knowledge.py      # pure tests — free, run freely
uv run python tests/test_arrangement.py    # (also test_composers.py, test_interpreter.py)

# LLM runs (need GEMINI_API_KEY in .env; billing is LIVE — be sparing):
uv run python -m crew.connectivity                              # one-call key/model check
uv run python -m crew.composers "doom fusion in Darbari, key of D"   # traced by default
uv run python -m crew.evals 0                                  # ONE interpreter eval case
uv run python -m crew.trace_portal                             # browse traces → :8420
```

`GEMINI_API_KEY` goes in `.env` (gitignored; copy `.env.example`). Render needs
FluidSynth (`brew install fluid-synth`) + the soundfont (see `soundfonts/README.md`).

## The code map

- **`src/`** — the deterministic core (NO LLM, NO network): `raga.py` (grammar +
  `validate_composition`), `talas.py`, `subgenres.py`, `render.py` (swara → MIDI → WAV).
  This is the single source of truth for raga/tala facts, used by both the validator
  and the agents.
- **`crew/`** — the agent shell (depends on `src/`, never the reverse):
  - `contracts.py` — the Pydantic contracts + pure builders: `CompositionBrief`,
    `Arrangement`/`ArrangementDraft`/`ComposerTurn`, `Composition`, the `DebateEvent`
    stream, `resolve_brief`, `build_arrangement`.
  - `interpreter.py` — agent #1. `composers.py` — agent #2 (the bounded dialogue).
  - `generators.py` — the deterministic backbone (section timeline, `VOICES`, Drone, Bass,
    assembly, render shell). `lead.py` / `riff.py` — the two LLM generators. `groove.py` —
    the deterministic Drums + Tabla. `band.py` — full-band assembly (`compose_band`,
    `compose_from_query`).
  - `config.py` — every model/temperature/loop knob (env-overridable). Prompts live in
    `config/agents.yaml` + `config/tasks.yaml`, never inline.
  - `tracing.py` / `trace_portal.py` — local observability. `evals.py` — eval harness.
- **`tests/`** — pure tests only (no API): knowledge, arrangement, composers, interpreter,
  generators, lead, riff, groove, band, ustad, rasik (142 tests, all free).

## The rules that bite (read `CLAUDE.md` for the full set)

- **Build ONE step at a time**, explain + teach the pattern, then get review before proceeding.
- **Hindustani, NOT Carnatic.** Verify raga/tala facts against ≥2 reliable sources; never guess.
- **Cost discipline** — Gemini billing is live. Prefer pure tests; batch live calls; run
  **one** eval case, not the whole suite (ask before the full suite).
- **Trace every LLM run** and read the trace (prompt + reasoning + output) *before* changing
  anything — tracing is on by default.
- **Own the loop** (bounded, streamable), don't use CrewAI's autonomous delegation.
  Validate at boundaries; schema checks shape, guardrails check domain, normalize junk.

## The next task — step 6: Conductor + the Flow (the money moment)

The generators AND both critics are done. Ustad (`critique_legality(comp)`) and Rasik
(`critique_taste(comp)`) each judge a `Composition`; what remains is to WIRE them into the
bounded debate — the talk's money moment:

- **Ustad** — legality — **done** (`crew/ustad.py`). Code owns the verdict; the LLM narrates.
- **Rasik** — taste — **done** (`crew/rasik.py`). LLM owns the verdict; a fixed rubric +
  encoded-fact grounding + a code-computed pakad hint keep it honest.
- **Conductor + the Flow** (next) — a CrewAI **Flow** running propose → critique → (debate +
  arbitrate on conflict) → revise, capped by `MAX_ROUNDS`. On an Ustad↔Rasik conflict (legal
  but lifeless, or loved but illegal) the Conductor is a `@router` that runs the **bounded
  debate** and rules accept / surgical-revise (regenerate only the flagged layer). It ALWAYS
  terminates on the round cap — never organic consensus. This is also where the deferred
  **foreground leader/follower LLM-seeding** (lead ⇄ riff) lands.

Everything the Conductor arbitrates already exists: `compose_band(arr)` yields the
`Composition`, `compose_from_query(query)` runs the whole pipeline, and the two critics return
`(verdict, events)`. Read `DESIGN.md` (roster, the critics + Conductor section, "who leads a
section") and the `CLAUDE.md` CrewAI/Flow rules before building.
