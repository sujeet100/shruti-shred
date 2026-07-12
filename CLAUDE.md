# Shruti Shred — a Raga × Metal agentic composer

A conference-talk demo: a multi-agent system that composes **Hindustani-classical × metal**
fusion, used to **teach agentic-AI patterns**. Audience picks a raga + metal subgenre; the
agents compose, critique, and revise live; the result renders to audio.

**Full build plan: `PLAN.md`.** This file is the always-on rules; PLAN.md is the roadmap.

---

## Working agreement (IMPORTANT — overrides default behavior)

- **Build ONE logical step at a time:** implement → explain what was built → **teach the
  underlying agentic pattern** → ask Sujit to review → only then proceed.
- **Do NOT build ahead of an explicit "start"/"go"** — even a low-risk, no-API-key step.
  Sujit is learning agentic patterns by reviewing; racing ahead defeats that. (This happened
  once and was reverted.)
- The goal is learning **agentic patterns, not a framework.** Keep patterns explicit — use
  CrewAI **Flows** (visible propose→critique→revise loop), visible tools, named patterns —
  not autonomous "magic."

## Musical accuracy (IMPORTANT — non-negotiable)

- **Hindustani, NOT Carnatic.** Names overlap but the ragas and the tala system differ.
  Treat any Carnatic source as a red flag.
- **Verify every raga AND tala against ≥2 reliable Hindustani sources** before encoding:
  ITC Sangeet Research Academy, Rajan Parrikar (parrikar.org), Tanarang, *The Raga Guide*
  (Nimbus/Joep Bor). Online raga data is often wrong/contradictory — **flag discrepancies,
  never guess.** Record which sources were used per raga/tala.
- **Knowledge = data; reasoning = LLM.** Raga/tala facts live in code as the single source of
  truth for BOTH the deterministic validator and the agents. LLM agents reason and map — they
  never supply the facts.
- Per **raga**, capture: allowed swaras, aroha/avaroha, vadi/samvadi, **pakad** (signature
  phrase), **chalan** (characteristic movement), thaat, samay. Pakad/chalan are used as
  generation seeds (idiomatic, not just in-scale) and as Rasik critique criteria.
- Per **tala**, capture: matras, vibhag grouping, sam/tali/khali positions, theka (bols).

## Architecture

- **Generators:** RagaGrammar, MetalRiff, Tala.
- **Critics — three ORTHOGONAL dimensions, one each** (the three questions about a piece of
  music): **Ustad** = *is it legal?* (uses the deterministic `validate_composition` as a tool —
  the hard guardrail); **Rasik** = *does it sound like the raga?* (raga authenticity — pakad,
  idiom, rasa); **Producer** = *does it work as a song?* (composition quality — structure,
  dynamics, climax, motif, hook, balance, independence, mood_fit; raga-agnostic).
- **Conductor (arbiter):** Ustad's legality drives a pure triage (illegal ⇒ forced revise, no
  debate). On a legal-but-flagged piece it runs a **bounded** debate between the two AESTHETIC
  critics — **Rasik (soul) ↔ Producer (works-as-music)** — Ustad EXITS the debate (its legality
  job ended at triage; a legal piece gives it no aesthetic stake), and makes the final call
  (accept, or the revise directive). **Always terminates** — debate needs a referee and a clock.
  This disagreement→debate→verdict is the money moment.
- **Orchestration:** CrewAI **Flow** — propose → critique → (debate + arbitrate on conflict)
  → revise, capped by `max_rounds`. Every debate/revise loop is bounded with a guaranteed
  terminator; never rely on agents converging on their own (live-safety).
- **Deterministic core (no LLM):** `src/raga.py` (grammar + validator), `src/talas.py`,
  `src/subgenres.py`, `src/render.py` (swara → MIDI → WAV).
- **Two contracts:** (1) composition JSON (generators emit / renderer consumes),
  (2) the debate event stream the UI renders.

## Conventions

- **Sargam** (semitones from Sa): `S0 r1 R2 g3 G4 m5 M6 P7 d8 D9 n10 N11`.
  lowercase = komal (flat), uppercase = shuddha (natural), `M` = tivra Ma (sharp).
- Compositions are **data** (swaras + timing); see the schema in `src/render.py`.
  Pitch = `sa + semitone(swara) + 12*oct`. Times are in quarter-note beats.
- **Orthogonal axes:** raga = which notes are legal; subgenre = tempo/rhythm/register;
  tala = the rhythmic cycle. Keep them independent.
- Grammar/tala facts must be **testable** — assert scales match their declared mode, etc.

## Models

- **Crew: Gemini (decided).** Flash for generators, Pro for critics/Conductor. GPT-5 = fallback only.
- Gemini has **no "reasoning effort" knob** — steer with **temperature** instead: generators
  ~0.8–0.9 (variety), critics/Conductor ~0.2 (consistency). See the CrewAI section below.
- Key via `.env` as **`GEMINI_API_KEY`** (what LiteLLM reads for the `gemini/` provider). Sujit
  provides it at Phase 2; Phase 1 data needs no key.
- Everything is model-agnostic via CrewAI/LiteLLM (model = one config value).

## Cost discipline — Gemini billing is LIVE (IMPORTANT)

Every LLM/crew call costs real money now. Keep spend minimal and deliberate:
- **Prefer PURE tests** (no API) — resolver, knowledge, `check_*_consistency`, structural
  contract checks. These are free; run them freely and rely on them as the first line.
- **Run LIVE calls sparingly** — only to verify something a pure test genuinely can't, and
  **batch** several checks into ONE run rather than many one-offs. Never re-run a live check
  just to re-confirm a result already in hand; reuse the last output.
- **No live calls in tight dev loops.** Iterate on prompts/logic against pure tests and
  reasoning first; do a single live confirmation at the end.
- **Evals: run ONE case, not the whole suite (IMPORTANT).** To test a change, run a SINGLE
  eval case — `uv run python -m crew.evals <index>` or `uv run python -m crew.evals "<ad-hoc
  query>"` — never the full golden set on a whim. Run ALL cases only for a deliberate
  regression pass, and **ask Sujit before running the entire eval suite.**
- **Levers:** cached input (repeated data/prompts ~10% cost), bounded dialogue turns
  (`MAX_ROUNDS`), flash-lite for the cheap agents, small structured outputs. Watch
  `flow.usage_metrics`.

## Observability — trace every LLM run (IMPORTANT)

**Tracing is ON by default for any LLM test, smoke, or eval** — never guess what an
agent did; read its trace. `crew/tracing.py` subscribes to CrewAI's event bus and
captures each crew/agent/LLM/guardrail step (full prompt, response, token usage,
timing, and guardrail retries). `crew/evals.py` and `crew/composers.py` enable it
automatically via `tracing_enabled()`; **opt out only with `RMA_TRACE=0`**. Each run
writes `traces/<name>.jsonl` (+ a standalone HTML) and streams a readable tree to the
console. Browse all runs in the local portal:
`uv run python -m crew.trace_portal` → http://127.0.0.1:8420 (dependency-free stdlib
server; `traces/` is gitignored). When diagnosing a misbehaving agent, open its trace
and read the actual prompt + reasoning + output *before* changing anything — pair this
with the reasoning-first extraction rule. (CrewAI event paths verified for 1.15.2;
re-check on upgrade.)

## CrewAI & agentic implementation rules (Phase 2)

*Researched 2026-07-11 against **CrewAI 1.15.2** (released 2026-07-08; supports Python 3.10–3.13,
so our 3.13 pin is correct). Sources: docs.crewai.com; Anthropic "Building Effective Agents" &
"Multi-agent research system"; Du et al. (multi-agent debate); Zheng et al. (MT-Bench / LLM-as-judge).*

**Flows (we use Flows, not autonomous Crews — the loop must stay visible):**
- Import from `crewai.flow.flow`: `Flow, start, listen, router, or_, and_`.
- `@start()` = entry (multiple run in parallel). `@listen(trigger)` fires on the trigger and
  receives its return value — **prefer writing to `self.state` over passing args**. `@router(trigger)`
  returns a **string label** matched by `@listen("label")` — the branching primitive. `or_/and_` = any/all join.
- **Structured state:** `class S(BaseModel): ...` then `class ComposeFlow(Flow[S])` → typed
  `self.state` (an `id` field is auto-added). `@persist` = SQLite save/restore.
- **The bounded loop IS our terminator.** Flows have **no built-in loop cap** (infinite-loop is a
  documented footgun). The Conductor is a `@router` that reads `state.round` and **always returns
  `"done"` once `round >= max_rounds`** — the referee and the clock, in code. Never wait on organic consensus.
- `kickoff(inputs=...)` / `kickoff_async`. Stream steps to the UI via the event bus: `BaseEventListener`
  from `crewai.events`, and the event classes from **`crewai.events.event_types`** (verified in 1.15.2:
  `MethodExecutionStartedEvent`, `MethodExecutionFinishedEvent`, `FlowStartedEvent`, `FlowFinishedEvent`).
  These paths move between releases — re-smoke-test on upgrade. `flow.plot()` renders the graph (a talk visual).

**Agents / Tasks / Tools:**
- Tools import from **`crewai.tools`** (NOT `crewai_tools`, the separate toolkit). Subclass `BaseTool`
  with a Pydantic `args_schema` for the deterministic validator tool; deterministic tools = no cache, return dict/Pydantic.
- **Use `validate_composition` two ways (do both):** (1) as a Task **`guardrail`** — runs *after* the
  agent's output, returns `(ok, value_or_error)`, feeds errors back for a bounded retry
  (`guardrail_max_retries`, default 3); the mandatory hard stop the agent can't skip. (2) as a **Tool**
  Ustad calls mid-reasoning so it can *explain* the violation. (`TaskGuardrail` is now `LLMGuardrail`.)
- **Structured output** via Task `output_pydantic=Model` is good but **not guaranteed** — always back
  it with a guardrail. Agents return DATA, never prose.
- Agent hygiene: tight role/goal/backstory, explicit `llm=` per tier, `tools=[...]`,
  **`allow_delegation=False`** (scripted Flow, not delegation), modest `max_iter` for live safety.
  Prompts live as external markdown/yaml config, never inline strings.

**Model IDs (VERIFIED 2026-07-11):** `from crewai import LLM; LLM(model="gemini/...", temperature=..., reasoning_effort=...)`.
`gemini/gemini-3.5-flash` is confirmed working on CrewAI 1.15.2 with `reasoning_effort="low"`. **Requires the
`crewai[google-genai]` extra** (native Google provider) — `uv add "crewai[google-genai]"`, else you get
`ImportError: Google Gen AI native provider not available`. **Starting simple:** Flash 3.5 at low effort for the
WHOLE crew (critics included); promote critics/Conductor to a Pro tier later via `RMA_PRO_MODEL`. All model IDs,
effort, and temperatures are env-overridable in `crew/config.py`.

**Agentic design (the talk's patterns, as engineering rules):**
- **Validate at every boundary; one bounded retry, not a loop.** If a step routinely needs 2+ retries,
  fix the prompt/schema — not the retry count.
- **Code decides the checkable; the LLM decides the rest.** Legality is code; taste is LLM. The
  guardrail runs before we accept generator output and gates the final render.
- **LLM-as-judge is biased** (position, verbosity, self-preference). Counter with explicit rubrics on a
  fixed scale, ground Rasik in the encoded pakad/chalan facts (criteria, not vibes), and swap option order when comparing.
- **Debate: 2–3 rounds max.** Gains plateau fast (Du et al.; Self-Refine) — most benefit is rounds 1–2.
- **Live cost/latency:** tier models, prewarm the crew + preload raga/tala data before the pick,
  retries with exponential backoff + jitter + a fallback path. Multi-agent burns ~15× single-agent
  tokens — stream the debate so the wait is the show.

**Python:**
- Full type hints. **Pydantic v2** for the two cross-boundary contracts (composition JSON, debate event
  stream); plain **dataclasses** for internal already-validated data on the render hot path (validate at
  the edge, pass dataclasses inside).
- `src/` stays importable with **no LLM/network** (the deterministic core). uv lockfile; ruff for
  lint/format. Raga/tala data remains the single immutable source of truth for both validator and
  agents; pass Flow state explicitly, no hidden globals.

## Code organization & maintainability (IMPORTANT)

*Researched 2026-07-11 (CrewAI 1.15.2). Sources: docs.crewai.com; Cosmic Python (*Architecture
Patterns with Python*); Refactoring Guru; PEP 544; Pydantic / ruff docs.*

**Hard rules (non-negotiable):**
- **Type hints on everything** — params, returns, attributes. Put `from __future__ import annotations`
  at the top of every module.
- **No god classes, no god methods.** **Single responsibility:** one unit, one job.
- Optimize for **long-run maintainability** over cleverness.

**Structure — by responsibility, pure core vs. shell:**
- Organize by **domain/responsibility, NOT by type**. No `utils.py` / `helpers.py` / `models.py` grab-bags.
- **Functional core, imperative shell.** The deterministic core (`src/`: raga, talas, subgenres, render,
  validator) imports **no crewai/LLM/network** and never depends on the agent layer. The `crew/` shell
  depends on the core, never the reverse. (Already true — keep it true.)
- Split a module the moment it grows a **second reason to change**.

**SRP heuristics — how to know a unit is too big:**
- You can't name it without "and"; it has >1 reason to change; a method runs past **~10 lines**; or you
  feel the urge to add an explanatory comment mid-method → **extract that block into a named method**.
  A god class is Refactoring Guru's "Large Class" smell → **Extract Class**.

**CrewAI layout (adopt as agents land):**
- Keep flow **orchestration** (`@start`/`@listen`/`@router`, state, the bounded loop) in its own module,
  **separate** from agent/task definitions.
- Prompts live as **external config** (CrewAI's classic `config/agents.yaml` + `config/tasks.yaml`, or our
  `prompts/*.md`) — never inline prose. **One task = one objective = one output.**
- Tools are **thin adapters** over the pure core: the validator tool is a ~3-line wrapper; the real logic
  and its tests live in `src/raga.py`.
- Flow state is a **Pydantic model**, not a dict. One agent = **one narrow role** (no god-agent).

**Types & data:**
- `Protocol` for interfaces (e.g. an injectable LLM client) — structural, no ABC. `Literal`/`Enum` for
  closed sets (swara, subgenre, role); `TypedDict` only for raw JSON dict shapes.
- **Pydantic v2 at boundaries** (LLM/tool output, config, JSON contracts), validate **once at ingress**;
  plain **dataclasses** for internal data; `frozen=True` for value objects that must not mutate.
- Enforce with **ruff** (lint+format) and **mypy/pyright** (cross-file types); start mypy loose, tighten.

**Dependencies & side effects:**
- Pass deps **explicitly** (LLM client, config, clock) — no global singletons. Small **factory functions**
  wire real adapters at the entry point (composition root).
- **No import-time side effects:** no network, no client construction, no `load_dotenv()` at module top —
  do those inside the functions the shell calls.
- Functions **return data, not prints**; side effects (audio write, API calls, logging) stay at the shell
  edge. Docstrings state the **contract** (inputs/outputs/invariants), not a paraphrase of the code.

**YAGNI:** don't add layers/registries/interfaces this small project doesn't need; introduce an
abstraction only when a second implementation or a real test seam demands it. SRP serves clarity, not a
checklist.

## Menu (locked)

- **Ragas (by metal-friendly mode):** Bhairavi (Phrygian), Bhimpalasi (Dorian),
  Darbari Kanada (Aeolian), Bhairav (double-harmonic), Malkauns (dark pentatonic).
  *Yaman dropped — Lydian, too bright for metal.*
- **Subgenres:** progressive, thrash, doom, death.

## Run

- **Dependency management: `uv`** (pyproject.toml + uv.lock). `uv add <pkg>`, `uv run <script>`.
  Lockfile → reproducible setup on the stage machine.
- **Python version:** pin to a crewai-supported version (`uv python pin 3.13` — 3.14 wheels may
  lag for crewai's dep tree). Re-verify the render there (render side is version-agnostic).
- Render/sound check: `uv run python src/demo.py` → writes `out/*.wav`.
- Render engine: **FluidSynth** + `soundfonts/MuseScore_General.sf3`
  (Distortion Guitar = GM program 30 — the same patch Songsterr uses). FluidSynth is a system
  binary (brew), NOT a Python dep.
- Deps: `MIDIUtil` (installed). **`crewai` added in Phase 2** (`uv add crewai python-dotenv`).
- **Secrets:** API keys in `.env` (**gitignored**; commit a `.env.example` template), loaded via
  `python-dotenv`. Never commit `.env`.
- **Entry points (Phase 2):**
  - Pure tests (no API — run freely): `uv run python tests/test_knowledge.py` (also
    `test_arrangement.py`, `test_composers.py`, `test_interpreter.py`).
  - Composer run (LLM, **traced by default**): `uv run python -m crew.composers "doom fusion in Darbari, key of D"`.
  - Interpreter eval (**ONE case** — see Cost discipline): `uv run python -m crew.evals 0` or `uv run python -m crew.evals "<ad-hoc query>"`.
  - Trace portal (browse runs by id): `uv run python -m crew.trace_portal` → http://127.0.0.1:8420.
  - Connectivity check: `uv run python -m crew.connectivity`.

## Status

Phase 0 (render pipeline) built and proven (`out/fusion_legal.wav`).
Phase 1 (knowledge core) **done**: `raga.py` (5 ragas, source-verified, + kan/meend
ornament support in the schema/renderer/validator), `talas.py` (6 talas), `subgenres.py`
(4, with drum vocabulary). All covered by `tests/test_knowledge.py` (`uv run python
tests/test_knowledge.py`). Drum grooves are **generated** at the tala×subgenre
intersection (no groove catalogue). Talk prep lives in `TALK.md`.
Phase 2 (CrewAI Flow + agents) **in progress** — see `DESIGN.md` for the full agent flow
and build order.
- Scaffolding done: `crew/` package, config (`crew/config.py`), contracts
  (`crew/contracts.py`), replay harness, connectivity check.
- **Agent #1 — Interpreter** (`crew/interpreter.py`) **done**: free-text query → validated
  `CompositionBrief` (invents nothing; unstated dims left OPEN). Reasoning-first extraction
  (chain-of-thought in the schema) at Flash/low-effort — faithfulness is the model's job,
  no string-grounding. Resolver tested in `tests/test_interpreter.py`.
- **Agent #2 — Pandit ⇄ Riffsmith composers** (`crew/composers.py`) **done**: a bounded,
  we-own-it turn-by-turn dialogue → the `Arrangement` chart (contracts + `build_arrangement`
  in `crew/contracts.py`; the LLM composes the music, code derives the tala accent grid and
  guards legality). `output_pydantic=ComposerTurn` for shape + a guardrail for the one
  domain rule (motif legal in the raga). Pure loop tests: `tests/test_arrangement.py`,
  `tests/test_composers.py`.
- **Agent #3 — the generators + full-band assembly** **done** — chart → every voice →
  `Composition` → WAV (`out/full_band.wav`). Only TWO voices are LLM; the rest is code:
  - **Lead** (`crew/lead.py`, LLM) — melodic line per section (kan/meend, cross-octave
    incl. cross-octave meend), voiced as **sitar and/or lead guitar** per section kind:
    solo / unison / octave / raga-diatonic **third** (harmony via `raga.scale_step_up`,
    legal by construction). Distinct lead-guitar tone from the rhythm guitar.
  - **Riff** (`crew/riff.py`, LLM) — one tala-cycle riff, looped seamlessly (code fills the
    cycle) and matra-locked; accents punched on the sam/tali.
  - **Deterministic voices (no agent):** **Drone** (raga-aware Sa+companion, `raga.drone_swaras`),
    **Bass** (`generators.bass_layer` — follows the riff's on-beat roots, need not play every
    note), **Drums/Groove** (`crew/groove.py` — locked to the riff, feel per section kind,
    rule fills at transitions), **Tabla** (`groove.tabla_layer` — the tala theka on conga
    stand-ins, may play under the kit).
  - **Assembly:** `crew/band.py` (`band_layers` pure; `compose_band` / `compose_from_query`).
    Backbone in `crew/generators.py` (section timeline, VOICES, drone, bass, assemble, render).
  - Pure tests (free): `test_generators`, `test_lead`, `test_riff`, `test_groove`, `test_band`.
- **Agent #4 — Ustad, the legality critic** (`crew/ustad.py`) **done**: judges whether a
  finished `Composition` stays inside its raga's grammar. The pattern — **code decides the
  checkable, the LLM narrates it** — is made STRUCTURAL: the deterministic
  `validate_composition` owns the `verdict`/`violations`, and Ustad's LLM output
  (`UstadNarration`) has no verdict field it could fill; the shell assembles the
  `UstadVerdict`. `validate_composition` is used the two prescribed ways — the hard
  guardrail on generator output, and a **tool Ustad calls mid-reasoning** (a visible ReAct
  step in the trace) so it can *explain* a violation. Tool caching is OFF (zero-arg call ⇒ a
  cache would return a prior piece's stale result). Pure tests: `tests/test_ustad.py`.
- **Agent #5 — Rasik, the RAGA-AUTHENTICITY critic** (`crew/rasik.py`) **done**: the deliberate
  OPPOSITE of Ustad — legality is a fact (code owns it), but **authenticity is not checkable, so
  the LLM genuinely judges** (LLM-as-judge). The bias (verbosity/gestalt/self-preference) is
  countered by DISCIPLINE, not by taking the pen: a fixed **1-5 rubric** over three named
  authenticity criteria (`RasikScores`: **pakad, idiom, rasa** — narrowed 2026-07-12 from the
  old four; songwriting moved to the Producer), scores **grounded in the encoded
  pakad/chalan/rasa facts** plus a **code-computed pakad hint** (`pakad_presence`), and a
  per-criterion justification required (reasoning first). No tool. Pure tests: `tests/test_rasik.py`.
- **Agent #7 — the Producer, the COMPOSITION-QUALITY critic** (`crew/producer.py`) **done**
  (2026-07-12): the THIRD critic dimension (Sujit's insight — Rasik was doing two jobs). Raga-
  AGNOSTIC songwriting/arrangement judgment on a fixed **1-5 rubric** over NINE criteria
  (`ProducerScores`: structure, dynamics, climax, motif, hook, balance, independence, mood_fit,
  repetition), grounded in the whole symbolic SCORE (section timeline, motif, riff line with
  chords/techniques, lead, ensemble — it reads the Arrangement, not just the Composition) AND in
  code-computed metrics (`crew/metrics.py`, pure): the per-section dynamics/energy curve +
  ornament rate, peak/resolution/flat arc, `motif_share` + `motif_recurrence` + `section_variety`
  (motif/repetition), `lead_riff_overlap`/`bass_riff_overlap`/`drums_tabla_overlap`
  (independence), register overlaps + everyone-playing fraction (balance) — "code measures, LLM
  evaluates". LLM-as-judge like Rasik. Pure tests: `tests/test_producer.py`, `tests/test_metrics.py`.
- **Agent #6 — the Conductor** (`crew/conductor.py`) **done** (the arbitration half of step 6,
  the talk's money moment): DISAGREEMENT → BOUNDED DEBATE → a REFEREE's verdict. `detect_conflict`
  is pure CODE triage — **illegal ⇒ forced revise, no debate** (legality is non-negotiable);
  **legal + both aesthetic critics satisfied ⇒ accept, no debate**; else the **aesthetic conflict**
  worth an LLM debate. Triage is now **HYBRID over BOTH** aesthetic critics: a CRITICAL criterion
  below `RASIK_PASS_SCORE` (Rasik: pakad/idiom; Producer: structure/motif) OR that critic's mean
  below `RASIK_OVERALL_FLOOR` — so a lone weak non-critical criterion doesn't burn a debate. The
  debate is **Rasik ↔ Producer** (Ustad EXITS — its legality is a quoted FACT, not a chair), a
  we-own-it bounded loop (Rasik opens, alternate) capped by `MAX_ROUNDS`; the Conductor **always
  rules at the cap** with a **surgical** `ConductorRuling` (one `layer`, one `reason`). Both
  aesthetic critics share ONE `debate_turn` task (bias in the backstories). Pure tests:
  `tests/test_conductor.py`.
- **The Flow** (`crew/flow.py`) **done** — step 6's orchestration half: the WHOLE pipeline as
  ONE bounded CrewAI `Flow` (`ComposeFlow`/`compose_flow(query)`): interpret → composers →
  generate → critics → Conductor → (surgical revise)* → render. The propose→critique→revise
  loop is VISIBLE (not autonomous). Two properties: (1) the `@router` reads `state.round` and
  ALWAYS returns "done" at the cap — the terminator is in code, never organic consensus; (2)
  the revise is **surgical** — regenerate ONLY the flagged voice (the Conductor's directive is
  threaded through that section's `intent` via `revise_arrangement`), then re-derive + re-assemble.
  The pipeline steps arrive as an injected `Stages` bundle (the composition root), so the Flow
  is fully tested with no LLM (`tests/test_flow.py`). CrewAI-Flow gotcha learned: the loop-back
  must be a **router label** (`revise_layer` is a `@router` re-emitting "recritique"), because a
  plain method-completion `or_()` fires once — only router-label `or_()` listeners get re-armed
  for a cycle. Live-confirmed end-to-end: fixed chart → 6 LLM calls → `out/flow_demo.wav`.
- **Observability** (`crew/tracing.py` + `crew/trace_portal.py`): every LLM run is traced by
  default (one trace = one run id, Langfuse-style); browse by id in the local portal.
  `crew/evals.py` is the interpreter eval harness. See the "Observability" section.
- Gemini billing is **LIVE** (`gemini/gemini-3.5-flash`, low effort) — see "Cost discipline".
- **Phase 2's agentic pipeline is COMPLETE end-to-end** (`compose_flow(query)` → WAV).
- **IN PROGRESS (2026-07-12) — audio production + review-informed polish** (Sujit: "do all
  together", tested chunks; full roadmap + design in DESIGN.md "Audio production & riff voicing"
  + "External review triage"). Root insight: the loop is symbolic — **no agent hears audio** —
  so the critics can't catch mix/timbre/technique gaps; those fixes are deterministic code.
  - **(1) Mix pass — ✅ DONE** (commit `40048f6`): bass an octave below the guitar, guitar out
    of sub-bass, per-channel pan (CC10), sitar/lead panned opposite, rhythm double-tracked hard
    L/R (Overdriven left / Distortion right + Haas offset). Not yet heard (batched — see below).
  - **(2) Riff extended-chords + techniques — ✅ DONE**: `chord`/`technique` on `RiffNote`+`Note`;
    the renderer stacks chord tones upward from the root (`_stack_above`) so `["S"]`=power chord,
    `["P"]`=fifth, `["g","n"]`=extended voicing, all legal-only (chord tones hit BOTH
    `validate_composition` kind `"chord"` and the riff guardrail); palm_mute chug + legato +
    slide/bend pitch-wheel gestures in `src/render.py`; prompt teaches it. New `tests/test_render.py`
    + riff/knowledge tests (179 pure tests green). Not yet heard (batched).
  - **(3) Producer as the 3rd critic + reframe the debate — ✅ DONE (chunk A)**: Sujit's notes
    split Rasik's two jobs — **Rasik → raga authenticity** (narrowed to pakad/idiom/rasa),
    **new Producer → composition quality** (8-criterion rubric over the whole symbolic score).
    Ustad EXITS the debate; the debate is now **Rasik ↔ Producer**, hybrid triage over both.
    Flow runs THREE critiques. See DESIGN.md "The Producer — a THIRD critic dimension".
  - **(chunk B / step 5) Producer's computed metrics — ✅ DONE**: `crew/metrics.py` (pure)
    computes the dynamics/energy curve, arc peak/resolution/flatness, `motif_share`,
    `lead_riff_overlap`, register overlaps + everyone-playing fraction; `render_metrics` grounds
    the Producer prompt ("code measures, LLM evaluates"). Pure tests: `tests/test_metrics.py`.
  - **(chunk C) Deepen Producer metrics + `repetition` criterion — ✅ DONE**: closed the deltas
    vs ChatGPT's full 10-point list — added `motif_recurrence`, `section_variety`,
    `bass_riff_overlap`, `drums_tabla_overlap`, per-section `ornament_rate`, and a 9th scored
    criterion `repetition`. (208 pure tests green.)
  - **NEXT (steps 4, 6–8):** composition memory (generators see realized previous sections);
    structured-output robustness (parse+retry) + fuzzy pakad; prompt hygiene; live-hardening
    (fast mode, failsafe chart, concurrent Lead∥Riff). A computed consistency check can fold
    into `metrics.py`.
  - **RUN NO LLM/live calls until ALL changes are done** (Sujit's instruction) — pure tests
    only, then ONE batched live render + one live Flow run at the very end.
- **`REVIEW.md`** is the external design/prompt review request; GPT + Gemini feedback is triaged
  in DESIGN.md ("External review triage").
- **External reviews are IN** (GPT + Gemini, on `REVIEW.md`) — triaged in DESIGN.md
  ("External review triage"). Both independently flag the **Ustad↔Rasik debate as the
  weakest link** (by triage the piece is already legal, so Ustad has no aesthetic stake):
  top finding is to **reframe the debate as Rasik (soul) vs a Producer/impact voice**, and
  to stop relying on provider-native strict JSON (parse+retry ourselves). Full roadmap +
  adopt/adapt/reject verdicts live in DESIGN.md.
- **Deferred (optional):** foreground leader/follower LLM-seeding (lead ⇄ riff) + the
  Conductor's composer tie-break. **Then Phase 3** — the live UI/SSE over the `DebateEvent` stream.
