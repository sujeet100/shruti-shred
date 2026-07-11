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
  - **Local tracing + portal + eval harness** — done (on by default).
- **NEXT → step 4: the generators** (Lead / Riff / Groove). See "The next task" below.

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
  - `config.py` — every model/temperature/loop knob (env-overridable). Prompts live in
    `config/agents.yaml` + `config/tasks.yaml`, never inline.
  - `tracing.py` / `trace_portal.py` — local observability. `evals.py` — eval harness.
- **`tests/`** — pure tests only (no API): knowledge, arrangement, composers, interpreter.

## The rules that bite (read `CLAUDE.md` for the full set)

- **Build ONE step at a time**, explain + teach the pattern, then get review before proceeding.
- **Hindustani, NOT Carnatic.** Verify raga/tala facts against ≥2 reliable sources; never guess.
- **Cost discipline** — Gemini billing is live. Prefer pure tests; batch live calls; run
  **one** eval case, not the whole suite (ask before the full suite).
- **Trace every LLM run** and read the trace (prompt + reasoning + output) *before* changing
  anything — tracing is on by default.
- **Own the loop** (bounded, streamable), don't use CrewAI's autonomous delegation.
  Validate at boundaries; schema checks shape, guardrails check domain, normalize junk.

## The next task — step 4: the generators

Turn the agreed `Arrangement` into playable audio. Three parallel generators read the
same chart and each emit one `Layer` of the `Composition` JSON (already defined in
`crew/contracts.py`; the Phase-0 renderer consumes it):

- **Lead** (RagaGrammar) — melodic lines per section (alaap/taan/lead/solo), seeded by the
  raga's pakad/chalan, using kan/meend; must pass `validate_composition`.
- **Riff** (MetalRiff) — rhythm-guitar riff, in-raga, locked to the tala accent grid.
- **Groove** (Tala) — drums (± tabla) from the tala × subgenre accent skeleton.
- **Drone** (tanpura) — Sa+Pa pad, **deterministic, no agent**.

Coherence comes from the shared chart (`Arrangement.accent_grid`, `registers`, `motif`,
`sections` with `intent`/`transition`). Run them in parallel, assemble the `Composition`,
render to WAV. Then step 5 (Ustad/Rasik critics) and step 6 (Conductor + the Flow). Full
detail in `DESIGN.md`.
