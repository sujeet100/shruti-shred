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

- **Crew: Gemini (decided).** Flash for generators, Pro for critics/Conductor.
  Effort: `xhigh` for critics (Ustad/Rasik/Conductor), `high` for generators. GPT-5 = fallback only.
- Key via `.env` as **`GEMINI_API_KEY`** (what LiteLLM reads for the `gemini/` provider). Sujit
  provides it at Phase 2; Phase 1 data needs no key.
- Everything is model-agnostic via CrewAI/LiteLLM (model = one config value).

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
