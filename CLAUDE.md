# Raga × Metal — Agentic Composer

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
- **Critics:** **Ustad** (legality + theory; uses the deterministic `validate_composition`
  as a tool — the hard guardrail) and **Rasik** (aesthetic taste; rubric; checks the pakad is
  present).
- **Conductor (arbiter):** on an Ustad↔Rasik conflict, runs a **bounded** debate between them
  and makes the final call (accept, or issue the revise directive). **Always terminates** —
  debate needs a referee and a clock. This disagreement→debate→verdict is the money moment.
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
- **Levers:** cached input (repeated data/prompts ~10% cost), bounded dialogue turns
  (`MAX_ROUNDS`), flash-lite for the cheap agents, small structured outputs. Watch
  `flow.usage_metrics`.

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

## Status

Phase 0 (render pipeline) built and proven (`out/fusion_legal.wav`).
Phase 1 (knowledge core) **done**: `raga.py` (5 ragas, source-verified, + kan/meend
ornament support in the schema/renderer/validator), `talas.py` (6 talas), `subgenres.py`
(4, with drum vocabulary). All covered by `tests/test_knowledge.py` (`uv run python
tests/test_knowledge.py`). Drum grooves are **generated** at the tala×subgenre
intersection (no groove catalogue). Talk prep lives in `TALK.md`.
Phase 2 (CrewAI Flow + agents) is next and needs `GEMINI_API_KEY`. See `PLAN.md`.
