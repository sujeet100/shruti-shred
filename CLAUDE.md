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
- **Live renders: ASK SUJIT FIRST, every time (IMPORTANT — his explicit rule, 2026-07-15).**
  A full-flow live render is the most expensive single action in the repo. Never kick one off
  on your own judgment, never re-render to "confirm" a code-level fix that pure tests already
  cover, and never chain render → find issue → fix → render again in one session — batch the
  fixes, then ask. (This rule exists because a session burned several full renders back to back.)
- **Live renders get a UNIQUE name** — `production_stages()` timestamps the render
  (`fusion_YYYYMMDD_HHMMSS.{wav,mid,json}`) so a new run never overwrites an earlier one;
  keep it that way, and never render to a name that already exists.
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

## Menu (expanded 2026-07-14 & 2026-07-15; all raga data source-verified ≥2 Hindustani sources)

- **Ragas (by metal-friendly mode):** Bhairavi (Phrygian), Bhimpalasi (Dorian),
  Darbari Kanada (Aeolian), Bhairav (double-harmonic), Malkauns (dark pentatonic),
  **Kirwani (harmonic minor)**, **Charukeshi (Mixolydian ♭6)**, **Bageshree (Dorian)**,
  **Puriya Dhanashree (double-harmonic ♯4)**, **Yaman (Lydian)**,
  **Chandrakauns (dark pentatonic + ♮7)**, **Jog (both-Ga pentatonic)**,
  **Marwa (♭2 ♯4, no Pa)**, **Todi / Miyan ki Todi (♭2 ♭3 ♯4 ♭6 ♮7)**.
  - **Yaman was re-added** despite the old "too bright for metal" note — it is the brightest
    (Lydian), so it leans prog/power, not doom/black. Keep the caveat in mind.
  - **Kirwani & Charukeshi are CARNATIC in origin** (melakarta ragas adopted into Hindustani) —
    encoded in their verified HINDUSTANI form; treat any Carnatic source as a red flag.
  - Bageshree shares Dorian with Bhimpalasi; its identity is the weak/omitted Pa + vakra + Ma-vadi,
    not the scale — don't let the two collapse in generation.
  - **2026-07-15 batch (Chandrakauns, Jog, Marwa, Todi):** Chandrakauns = Malkauns + shuddha Ni
    (a leading tone → tension); Jog uses BOTH gandhars (the komal-ga "Gmg" zigzag is its identity —
    don't let it collapse to a single third); Marwa OMITS Pa and its Sa is deliberately WEAK
    (hovers on komal-re/Dha, no dominant pull — a floating, tritone-tense colour); Todi is the most
    chromatic (Todi thaat, tivra Ma, Pa sparse, komal re/ga sung "ati-komal" — a shruti we can only
    approximate). FLAGGED discrepancies live in each entry's comment (esp. Jog's contested vadi).
- **Subgenres:** progressive, thrash, doom, death, **heavy** (Heavy Metal), **melodic_death**
  (Melodic Death), **black** (Black).

## Run

- **Dependency management: `uv`** (pyproject.toml + uv.lock). `uv add <pkg>`, `uv run <script>`.
  Lockfile → reproducible setup on the stage machine.
- **Python version:** pin to a crewai-supported version (`uv python pin 3.13` — 3.14 wheels may
  lag for crewai's dep tree). Re-verify the render there (render side is version-agnostic).
- Render/sound check: `uv run python src/demo.py` → writes `out/*.wav`.
- Render engine: **FluidSynth** + `soundfonts/GeneralUser-GS.sf2` (GeneralUser GS 2.0.3,
  License v2.0; Distortion Guitar = GM program 30, Sitar = GM #105). Swapped from
  `MuseScore_General.sf3` (MIT) on 2026-07-13 — an all-round upgrade for guitars/bass/drums
  with a proper GM sitar; our GM program numbers map transparently (drop-in). Soundfont path
  is set per module (`_SOUNDFONT`); fetched by `setup.sh` (gitignored). FluidSynth is a system
  binary (brew), NOT a Python dep.
- **Stacked (split) soundfonts** (`src/soundfont.py`): the renderer can layer specialized
  banks over the GM base (FluidSynth `-b` bank-offset + MIDI Bank Select per channel, `mma`
  mode) so a voice pulls from a dedicated soundfont; a missing extra degrades to the base.
  Live: the guitars route to **SGM V2.01** when present (bank offset 300 — Sujit picked its
  tone by ear 2026-07-15; it is what Songsterr's FluidSynth player uses; GM-compatible, so the
  two-tone L/R double-track survives; palm-muted chugs bank-select its bank-1 **"Muted
  Dis.Gt"** articulation via the renderer's companion channel), degrading to **Dethmetal**
  (dedicated distorted guitar, bank 126; license UNVERIFIED — demo-only) then the GM base;
  the **sitar + tabla** route to the **Indian Ensemble**
  (bank offset 50; E-mu, attribution license, MANUAL fetch — polyphone gates it, see `setup.sh`).
  That soundfont is pitched an OCTAVE LOW, so the sitar (preset 2) is transposed +1 octave; the
  tabla (preset 0, melodic channel) is **tuned to the piece's Sa** via RPN coarse-tuning. The
  **drone stays on GM strings** (better than the tamboura). Routing is data in `soundfont.py`
  (`route_guitars`/`route_indian`/`route_layers`, `present_extras`); each degrades to the GM
  base when its file is absent.
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
  - **(step 4) Composition memory — ✅ DONE**: each Lead/Riff section is generated seeing the
    REALIZED prior sections (`LeadMemo`/`RiffMemo` threaded through the generator loop, rendered
    as a `{previous}` prompt block), so the music DEVELOPS (restate/vary the motif, answer the
    prior section, bring the main riff back as a hook, reserve the peak for the climax) instead of
    collaging. Within-voice; cross-voice seeding (lead sees riff) still deferred. Pure tests in
    `test_lead.py`/`test_riff.py`. (214 pure tests green.)
  - **(step 6, structured-output) — ✅ DONE**: on the NATIVE `GeminiCompletion` provider (native
    controlled generation), the "parse JSON ourselves" reviewer concern targets the LiteLLM path we
    DON'T use → **manual parser dropped**; complex `meend` Union flattened → `meend_swara`+`meend_oct`
    (`e5e5d53`); and **fuzzy `pakad_presence`** shipped (`5c3cfa3`) — literal / fuzzy / absent tiers
    (the fuzzy tier a bounded-gap subsequence) so a stray grace note no longer breaks the match.
  - **(step 7, prompt hygiene) — ✅ DONE** (`c3c5346`): positive-over-negative (interpreter + the
    `Do NOT` lines), per-criterion **1/3/5 judge anchors + anti-length** lines, **rubric AFTER the
    composition data** for the critics, dialed-back **ALL-CAPS**; one worked few-shot example in generate_lead.
  - **(step 9, lead `phrase_plan`) — ✅ DONE** (`1a0fefb` code + `c3c5346` prompt): the lead produced
    a straight SCALE run, not a raga taan — Rasik CAUGHT it ("scalar run dilutes the raga; use vakra
    phrasing + andolan on komal g/d"), proving the critic works but the GENERATOR couldn't act on the
    directive. Fix: a REQUIRED `phrase_plan` (seed/contour/transformations/climax) ordered BEFORE
    `notes` in the schema (reasoning-first made STRUCTURAL) + a prompt that builds taans from
    chalan/vakra fragments (~80% from pakad/chalan). Live-confirmed the taan became pakad-derived +
    rhythmically varied. Lesson (talk-gold): a critique loop is only as good as the GENERATOR's
    ability to act on the directive.
  - **(step 10, meend realism) — ✅ DONE** (`1a0fefb` density guard + `6b6f897` render): the meend was
    pitch-CORRECT (lands on the swara; bend range honored) yet sounded out of tune on EVERY patch → it
    was the GESTURE, not the sitar sample or the renderer. The old glide crawled LINEARLY over 60% of
    the note, dwelling on the out-of-scale micro-pitches. Fix: (a) a **density guard** strips meend from
    sub-beat notes (fast taan articulates clean; direction free — kan/khatka/murki all bend either way);
    (b) the render is a **quick, capped, cubic-ease-out pull ANCHORED ON THE TARGET** (sounds at the
    target's home sample, wheel pre-bends to the source and eases to 0, ends at 0 — no bleed). MIDI
    portamento (CC5/CC65) researched + rejected; no new renderer/soundfont. Research notes in DESIGN.md.
  - **`PROMPTING.md` — ✅ ADDED** (`af96bb9`): a cited Gemini-focused prompt-engineering reference
    (from a research pass). It drove step 7 (done) and still flags an **OPEN TENSION** for step 8's
    live pass: Google recommends **temp 1.0 for Gemini-3.x** and warns <1.0 degrades reasoning,
    but our critics run 0.2 / extractor 0.0; and the "no reasoning knob" / "temperature is the
    main knob" premises here are STALE (code already passes `reasoning_effort`, Gemini 3 has
    `thinking_level`). Resolve EMPIRICALLY via traces — do NOT silently flip. See DESIGN.md.
  - **NEXT — ★ HEADLINE (build in a NEW session, decided 2026-07-12):** **bounded cooperative
    collaboration** — the talk's SECOND named pattern beside the critique loop (collaboration is rarely
    showcased; most demos are plain workflows). A "studio session" on a shared `SectionCanvas`: the two
    creative agents (Lead ⇄ Riff) propose→respond→refine over bounded passes; Drone/Bass/Drums/Tabla stay
    deterministic and follow. CODE decides the order (bandleader + clock) — the LEADER rotates by section
    kind (riff leads a groove, lead leads an alaap, climax = unison); NOT autonomous L4. Locked: 3 passes
    / fast-mode 1, rotating leader, bass/drums deterministic. Stream the canvas so the audience watches
    the band build it → two money moments (cooperate → debate). Full design + the sequencing answer +
    open items in DESIGN.md ("Next headline feature — bounded cooperative collaboration").
  - **Also queued:** step 8 live-hardening (fast mode, failsafe chart, concurrent Lead∥Riff) + the
    **temperature A/B** (OPEN TENSION — resolve empirically); **one full-band live render** (taan + clean
    meend in context); deferred **meend polish** (CC74 roll-off + chorus; a first-class **andolan**
    ornament — Rasik's standing ask); **triage bite** (a weak idiom score should FORCE a revise).
    (225 pure tests green; steps 6/7/9/10 committed: `5c3cfa3`, `1a0fefb`, `6b6f897`, `c3c5346`.)
- **`REVIEW.md`** is the external design/prompt review request; GPT + Gemini feedback is triaged
  in DESIGN.md ("External review triage").
- **External reviews are IN** (GPT + Gemini, on `REVIEW.md`) — triaged in DESIGN.md
  ("External review triage"). Both independently flag the **Ustad↔Rasik debate as the
  weakest link** (by triage the piece is already legal, so Ustad has no aesthetic stake):
  top finding is to **reframe the debate as Rasik (soul) vs a Producer/impact voice**, and
  to stop relying on provider-native strict JSON (parse+retry ourselves). Full roadmap +
  adopt/adapt/reject verdicts live in DESIGN.md.
- **GAT DEVELOPMENT — ✅ BUILT (2026-07-15;** full record: DESIGN.md "GAT DEVELOPMENT — BUILT"**):**
  the A→D campaign from Sujit's live feedback + the Gemini review. (A) `verify_intro` — the alap
  ends on a HELD Sa, Sa ≥30% by duration (chikari counts — the prompt teaches Sa re-emphasis via
  chikari between phrases), ≥2 true rests + a nyas rest after Sa; the pre-mukhada pause is CODE
  (`_intro_gen_span` shortens the gen window). (C) manjha composed KNOWING the cached head
  (`{mukhada_head}` block) + `verify_manjha` (fills to the sam; last note ≤2 ladder steps from the
  head's first swara; not flat); composer guardrail: manjha only after the first mukhada and
  IMMEDIATELY followed by one, and lead-less sections ≤2 bars. (D) ONE sixteenth-note taan fill
  (`verify_fill`) spliced by code into the middle statement of every ≥3-bar mukhada section. All
  verified cells share `_generate_verified_cell` (bounded feedback re-roll, best-of-N).
  **The riff finding (talk-gold):** the MIDI DISPROVED the tritone-stack hypothesis (110 octaves +
  8 fifths, zero dissonant stacks) — the real mud was (1) riff roots at D1 (local `oct:-1` sank
  below the register floor; now clamped per-note at `RHYTHM_FLOOR` in `_sequence_cycle`), which
  also put the bass IN the riff's octave, (2) CLIPPING at gain 1.2 (now `_GAIN=0.5`, calibrated),
  (3) bone-dry samples (now per-role CC91 reverb sends + a FluidSynth room), (4) both rhythm
  sides on one Dethmetal patch (now `detune_cents=8` on the right take). Chords now seat
  CONSONANT-under-distortion (`_seat_chord_tone`: octave/fifth/inverted-fourth/add9/tenth;
  semitone/tritone/sixth/seventh degrade to octave weight) and `harmonize_riff_to_lead` thins any
  riff note grinding (ic 1/6/11) under a sustained lead note to a soft chug — the riff yields, the
  raga line is never re-pitched. Every render now saves the **Composition JSON** beside the WAV.
- **DRUM MACHINE V2 — ✅ BUILT (2026-07-15;** design + research record: DESIGN.md "DRUM MACHINE
  V2"**):** the kit is a real metal drummer, still deterministic (no agent). New
  `crew/drum_patterns.py` (pure, research-grounded 16th-grid vocabulary: skank/D-beat, three
  blasts, gallop cell, double-kick carpet, half-time, prog kick-drift) + `crew/groove.py`
  orchestration: section ENERGY from kind+form_role (**ANTARA rides half-time on the RIDE**,
  taan_long = climax crash wash, breakdown = china quarters), patterns tiled PER VIBHAG with the
  tala in the kit's dynamics (sam crash+kick each phrase, tali leans in/bell, khali sits back),
  A-A-A-B turnarounds, mini/seam/into-climax crescendo fills (kick carpet plays through),
  band-entrance pickup roll + riff-matched STOP HITS, ghost notes + 4-level velocities +
  deterministic jitter (black stays icy-flat; doom drags the backbeat). New GM `bell` voice;
  death gained ride+bell. `groove_layer(arr, rhythm)` signature unchanged (band.py untouched).
  test_groove 15→30; suite 490 green; no-LLM sound check `out/drum_machine_v2_demo.wav`.
- **RIFF CAMPAIGN chunk 1 — ✅ BUILT (2026-07-15;** evidence + design: DESIGN.md "RIFF
  CAMPAIGN chunk 1"**):** Sujit's "riffs sound light/happy, hollow, no chugs" diagnosed from
  `out/fusion.json` EVIDENCE (79% pitch-change = melody-not-riff; bright add9/tenth stacks
  outnumbering power weight; techniques emitted but inaudible in render; nothing sustained;
  and the piece was YAMAN — brightest raga). New `crew/riff_texture.py`: **RiffMode**
  (DRIVE/PADS/STABS, code-decided from form_role — the ANTARA/taans PAD: long ringing power
  chords under the sitar) + **`verify_riff`** texture budgets (chug-ground share, pitch-change
  cap, weighted sam, real silence, ring share, bright-colour ration) + **`verified_riff`**
  bounded feedback re-roll wrapping BOTH composition roots (`_LLMRiff`, `studio_riff_fn`) at
  the LLM boundary — pure loops/fakes untouched. Prompt reframed as rhythm-guitar ARRANGER
  (chug ground default, power-weight default, strip-the-pitches test, {mode_brief}/{repair}).
  New techniques **long_slide + pick_scrape** (schema→renderer wheel gestures→prompt→ration).
  test_riff_texture (19) + placeholder-contract test.
- **RIFF CAMPAIGN chunk 2 — ✅ BUILT (2026-07-15;** DESIGN.md "RIFF CAMPAIGN chunk 2"**):**
  the techniques became AUDIBLE (render-internal, contract unchanged): palm-mute chugs route
  to a GM muted-guitar companion channel (+ soft distorted body under; inherits pan/detune,
  never the specialized bank), hammer_on/pull_off are real legato (a capped wheel pull from
  the PREVIOUS note's pitch on connected unchorded notes), slides start from the previous
  pitch (direction follows the line). test_render 25→28; suite 516 green; no-LLM sound check
  `out/riff_texture_demo.wav` (muted companion + 162 wheel gestures verified in the MIDI).
  **Next: ONE live render (ask Sujit first), then tune by ear (batched).**
- **SONGSTERR INVESTIGATION + SGM — ✅ BUILT (2026-07-15;** full findings: DESIGN.md
  "SONGSTERR INVESTIGATION"**):** Songsterr = pre-rendered Opus stems (offline Vir2/Kontakt
  render — the "great sound") + an in-browser fallback that IS our stack (FluidSynth-WASM +
  SGM, palm mute = bank-1 preset switch). Adopted: **SGM V2.01 stacked** (offset 300;
  setup.sh, ~236MB) — **guitars prefer SGM** (Sujit's ear), chug companions bank-select
  `Muted Dis.Gt` (301:28, no body layering), palm-mute gate now FIXED ~70ms wall-clock.
  A/B piece (ORIGINAL riff, style-level — the song's tab NOT transcribed, copyright):
  `out/slide_chug_ab.wav` vs Songsterr's Redneck Stomp playback. Suite 520 green.
  **Tuning menu queued (by ear, next):** tail-loaded slides landing on the target's beat,
  multi-fret slides as chromatic retriggered steps, per-string channels for chord slides,
  RPN bend range 24.
- **SOUND CONFIG LOCKED BY EAR (2026-07-15, Sujit's A/B):** `SGM_Plus_HQ.sf3` is the
  **preferred BASE** for the whole band when present (`base_soundfont()`; setup.sh fetches
  it, ~95MB, license UNVERIFIED demo-only) — guitars keep their own GM programs (no bank
  routing), chugs bank-select its 1:28 "Muted Dis.Gt", **drums route to the POWER kit
  (GS 16)**, bass plays its GM bass; Indian Ensemble still stacks for sitar/tabla; the
  stacked SGM V2.01 is skipped when HQ is base (fallback chain otherwise unchanged).
  Loudness = **peak-normalize post-render to `NORMALIZE_PEAK_DB` (−2.0 dBFS ≈ Songsterr
  gain 1.0, Sujit's dial-back)** via ffmpeg in `render()`; synth gain stays at the
  calibrated 0.5 (never re-raise it — gain 1.2 pins peaks/clips). Chug parity rules:
  no PM velocity cut, companion CC7=127, distorted body under chugs at FULL vel.
  Songsterr facts (DESIGN.md "SONGSTERR"): their client has NO mastering; premium sound
  = offline Vir2/Kontakt stems; synth fallback = FluidSynth-WASM + this exact font.
- **Deferred (optional):** foreground leader/follower LLM-seeding (lead ⇄ riff) + the
  Conductor's composer tie-break. **Then Phase 3** — the live UI/SSE over the `DebateEvent` stream.
