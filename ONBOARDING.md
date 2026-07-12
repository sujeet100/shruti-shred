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
  - **Agent #6 Conductor** — done (the arbitration half of step 6, the money moment).
    `conduct(ustad, rasik, comp)` → `ConductorRuling` (accept | surgical revise). Pure CODE
    triage (illegal ⇒ forced revise; legal+satisfied ⇒ accept; legal+weak ⇒ debate), a
    bounded Ustad↔Rasik debate capped by `MAX_ROUNDS`, always ruling at the cap (`crew/conductor.py`).
  - **The Flow** — done (step 6's orchestration half). `compose_flow(query)` runs the WHOLE
    pipeline as one bounded CrewAI `Flow`: interpret → composers → generate → critics →
    Conductor → (surgical revise)* → render, with the `@router` on `state.round` as the
    terminator (`crew/flow.py`). Live-confirmed end-to-end → `out/flow_demo.wav`.
  - **Local tracing + portal + eval harness** — done (on by default).
- **Phase 2 is COMPLETE end-to-end** (`compose_flow(query)` → WAV). NEXT is really Phase 3 (the
  live UI / SSE over the `DebateEvent` stream the Flow already emits); optional deferred
  refinements are the foreground leader/follower seeding + the composer tie-break. See below.

## Quickstart

```bash
uv run python tests/test_knowledge.py      # pure tests — free, run freely
uv run python tests/test_arrangement.py    # (also test_composers.py, test_interpreter.py)

# LLM runs (need GEMINI_API_KEY in .env; billing is LIVE — be sparing):
uv run python -m crew.connectivity                              # one-call key/model check
uv run python -m crew.composers "doom fusion in Darbari, key of D"   # traced by default
uv run python -m crew.conductor                                # money-moment debate (planted conflict)
uv run python -m crew.flow                                     # WHOLE pipeline → WAV (bounded demo chart)
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
  - `ustad.py` / `rasik.py` — the two critics (legality / taste). `conductor.py` — the
    arbiter (triage + bounded debate + ruling). `flow.py` — the whole pipeline as ONE
    bounded CrewAI `Flow` (`compose_flow(query)` → `ComposeState`), the orchestration root.
  - `config.py` — every model/temperature/loop knob (env-overridable). Prompts live in
    `config/agents.yaml` + `config/tasks.yaml`, never inline.
  - `tracing.py` / `trace_portal.py` — local observability. `evals.py` — eval harness.
- **`tests/`** — pure tests only (no API): knowledge, arrangement, composers, interpreter,
  generators, lead, riff, groove, band, ustad, rasik, conductor, flow (159 tests, all free).

## The rules that bite (read `CLAUDE.md` for the full set)

- **Build ONE step at a time**, explain + teach the pattern, then get review before proceeding.
- **Hindustani, NOT Carnatic.** Verify raga/tala facts against ≥2 reliable sources; never guess.
- **Cost discipline** — Gemini billing is live. Prefer pure tests; batch live calls; run
  **one** eval case, not the whole suite (ask before the full suite).
- **Trace every LLM run** and read the trace (prompt + reasoning + output) *before* changing
  anything — tracing is on by default.
- **Own the loop** (bounded, streamable), don't use CrewAI's autonomous delegation.
  Validate at boundaries; schema checks shape, guardrails check domain, normalize junk.

## The next task — audio production polish (then Phase 3)

Phase 2 is complete: `compose_flow("a dark doom fusion in Malkauns")` runs the whole crew end
to end and returns a `ComposeState` with the `Composition`, the full `DebateEvent` stream, the
Conductor's ruling, and the rendered WAV path. Everything downstream already exists.

**Immediate work (2026-07-12 — Sujit: "do all together"; full plan + RESUME-HERE note in
DESIGN.md "Audio production & riff voicing" + roadmap):** audio + review-informed polish, in
tested chunks. Root insight: the loop is symbolic — no agent hears audio — so mix/timbre fixes
are deterministic code. **Mix pass is DONE** (commit `40048f6`: bass an octave below the
guitar, per-channel pan, sitar/lead panned opposite, rhythm double-tracked hard L/R). **Resume
at step 2:** riff extended-chords + techniques (legal-only, stacked from the raga's own
swaras — concrete design in DESIGN.md), then the debate reframe (**Ustad exits; a Producer
critic debates Rasik**), composition memory, computed metrics + consistency, robustness, prompt
hygiene, live-hardening. **Run NO LLM until all changes are done** — then one batched live render.
The external reviews (GPT + Gemini on `REVIEW.md`) are triaged in DESIGN.md.

Then Phase 3:

- **Phase 3 — the live show (the real next step).** A UI that streams the `DebateEvent` stream
  the Flow already emits (over SSE): the audience picks a raga + subgenre, and the propose →
  critique → debate → revise loop plays out live, ending in audio. The event contract
  (`crew/contracts.py`, `EventStream`) and the replay harness (`crew/replay.py`) were built for
  exactly this — the events look identical live or replayed. See `PLAN.md` for Phase 3.
- **Optional deferred refinements** (nice-to-have, not blocking):
  - **Foreground leader/follower LLM-seeding** (lead ⇄ riff): a section's `foreground` voice
    generates FIRST and its realized line seeds the followers ("answer this"), so a riff-led
    section is genuinely built around that riff. Today the two creative voices generate in
    parallel against the shared chart.
  - **Composer tie-break**: have the Conductor arbitrate an un-agreed composer dialogue instead
    of letting the last draft stand (`run_dialogue` already leaves the hook).

Read `PLAN.md` (Phase 3), `DESIGN.md` (the flow diagram + "who leads a section"), and the
`CLAUDE.md` CrewAI/Flow rules before building.
