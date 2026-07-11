# Raga × Metal — Agentic Composer: Build Plan

*A conference-talk demo that teaches agentic-AI **patterns** through a live, multi-agent
Hindustani-classical × metal fusion composer.*

Last updated: 2026-07-08

---

## 1. Locked decisions

| Decision | Choice |
|---|---|
| **Talk goal** | Live demo that wows; the wow is *visual* — the audience watches agents debate. Thesis: **constraints make agents creative**, and the meta-lesson **hard guardrails (code) + soft taste (LLM)**. |
| **Learning goal** | Agentic **patterns**, not a framework. Code will be pattern-explicit + a `PATTERNS.md` walkthrough. |
| **Framework** | **CrewAI** — using **Flows** (explicit propose→critique→revise loop) so the patterns stay visible, not a fully-autonomous Crew. |
| **Crew models** | **Gemini Flash** for generators, **Gemini Pro** for critics (Ustad/Rasik). Fast + cheap for live; lines up with Google's Lyria/Veo for V2. |
| **Agents** | Generators: RagaGrammar, MetalRiff, Tala. Critics: **Ustad** (legality + theory; uses the deterministic validator tool) and **Rasik** (aesthetic taste; rubric). |
| **Sound** | Agents emit **swara JSON** → deterministic Python → MIDI → **FluidSynth + MuseScore_General.sf3** (Distortion Guitar = GM prog 30). *(Pipeline already proven.)* |
| **Build mode** | Claude implements each **logical step**, then explains what was built + teaches the underlying agentic pattern + asks Sujit to review **before** proceeding. No building ahead of the plan or of an explicit "start". |
| **Deliverable** | Full stage demo. |
| **Demo risk** | Fully live on stage (+ a quiet one-key pre-rendered fallback as insurance). |
| **Range** | Audience picks live — **raga AND metal subgenre both selectable**. |
| **Latency budget** | 60–90s per live generation; the streamed debate fills the wait. |
| **Timeline** | One weekend (~2–3 focused days). |

---

## 2. The scope-vs-time reality (read this first)

The choices above are the *most ambitious on every axis*. In a weekend, we cannot ship
"any raga × any subgenre, richly debated, fully live, polished UI." So we split:

### Weekend Core (must land — this is the demo)
- **5 ragas (by mode) × 4 subgenres, selectable live** — 20 combos the crew can attempt. Ragas: **Bhairavi** (Phrygian), **Bhimpalasi** (Dorian), **Darbari** (Aeolian), **Bhairav** (double-harmonic, built), **Malkauns** (dark pentatonic — no Re, no Pa). Subgenres: **progressive, thrash, doom, death**. Natural pairings: Phrygian→death/thrash, Dorian→progressive, Aeolian & pentatonic→doom, exotic→death. Subgenre = tempo+rhythm+register; raga = legal notes (orthogonal). Pre-render ~5 hero combos as tuned fallbacks. *(Yaman/Lydian dropped — too bright.)*
- Presenter-operated **dropdown pick** (raga + subgenre) — reads as "audience chose it."
- CrewAI **Flow**: generators → Ustad (legality, deterministic) → Rasik (taste) → 1 revise round.
- **Mission-control UI**: 5 agent panels, debate streaming live, swara grid turning green/red, rubric scorecard, big **PLAY**, naive-vs-crew A/B.
- **Fully live**, with pre-warm + retries + a one-key fallback clip.

### Stretch (only if Core is solid)
- +2 ragas (Bhairavi, Bhupali), +1–2 subgenres (thrash, black-metal).
- **Multimodal Rasik** — renders the candidate and *listens* to it (Gemini audio) before judging.
- Real audience input (QR page / phone vote) instead of presenter dropdown.
- More debate rounds; per-section regeneration.

If a weekend proves tight, Core still gives a complete, jaw-dropping talk. Stretch is gravy.

---

## 3. Architecture

```
                 ┌──────────────────────────────────────────────┐
                 │  MISSION-CONTROL UI  (FastAPI + SSE + vanilla) │
                 │  pick raga+subgenre │ live debate │ PLAY │ A/B │
                 └───────────────┬───────────────▲──────────────┘
                     pick request│               │ SSE: debate events,
                                 ▼               │ validation, audio URL
                 ┌──────────────────────────────────────────────┐
                 │  ORCHESTRATOR  — CrewAI Flow                   │
                 │  propose → critique → revise (explicit loop)   │
                 └───┬───────────────┬───────────────┬───────────┘
       generators    │               │ critics       │  deterministic core
   ┌─────────────────▼──┐   ┌────────▼─────────┐   ┌─▼───────────────────────┐
   │ RagaGrammar (Flash)│   │ Ustad  (Pro)     │   │ raga library (data)      │
   │ MetalRiff  (Flash) │   │  legality+theory │──▶│ validate_composition()   │  ← hard guardrail
   │ Tala       (Flash) │   │  [validator tool]│   │ swara→MIDI→WAV (FluidSynth)│  ← proven
   └────────────────────┘   │ Rasik  (Pro)     │   └──────────────────────────┘
                            │  aesthetic taste │
                            └──────────────────┘
   Contracts: (a) composition JSON schema  (b) debate event stream (agent, text, verdict)
```

**Conductor (arbiter)** sits over the two critics (not drawn above): on an Ustad↔Rasik conflict it runs a *bounded* debate between them and issues the verdict (accept, or the revise directive). Every debate/revise loop is capped by `max_rounds` with the Conductor as the guaranteed terminator — *debate needs a referee and a clock.*

**Two contracts hold it together** (both framework-agnostic, so they double as teaching artifacts):
1. **Composition JSON** — what generators emit and the renderer consumes (already defined in `render.py`).
2. **Debate event stream** — `{agent, role, text, verdict?, scores?}` events the UI renders. The UI
   doesn't care whether events come from the live crew or a replay script — same shape.

---

## 4. Agentic patterns catalog (the learning spine → `PATTERNS.md`)

| # | Pattern | Where it lives | Talk beat |
|---|---|---|---|
| 1 | Structured output as a contract | swara JSON schema | "agents don't return prose, they return data you can check" |
| 2 | Deterministic tool as a hard guardrail | `validate_composition` | "the one thing you never trust the LLM to do" |
| 3 | Separation of concerns / roles | generators vs critics | "small specialists beat one god-prompt" |
| 4 | Reflection loop | propose→critique→revise Flow | the live debate itself |
| 5 | LLM-as-judge | Ustad + Rasik scoring | "how do you grade taste?" |
| 6 | Multi-judge disagreement | Ustad (legal) vs Rasik (lifeless) | sets up the argument |
| 7 | Multi-agent debate | critics argue conflicting verdicts to converge | the on-stage argument |
| 8 | Arbitration + bounded termination | Conductor caps rounds and decides | "debate needs a referee and a clock" |
| 9 | Hard guardrail vs soft judgment | code validator vs LLM critics | the thesis, one slide |
| 10 | (stretch) Multimodal judge | Rasik listens to the render | "the AI grew ears" |

---

## 5. Build phases & order

| Phase | Work | Output | Learning-review checkpoint |
|---|---|---|---|
| **0 ✅** | Render pipeline + validator + data-driven demo | `raga.py`, `render.py`, `demo.py`, proven WAV | (done) |
| **1 ✅** | **Raga library** — 5 ragas: allowed swaras, aroha/avaroha, vadi/samvadi, **pakad**, **chalan**, thaat, samay — **cross-checked ≥2 reliable Hindustani sources** (NOT Carnatic). + kan/meend ornaments (schema+renderer+validator). + **Tala library** — Rupak/Jhaptaal/Teentaal/Keherwa/Dadra/Ektaal: matras, vibhag grouping, sam/tali/khali, theka bols (also verified, Hindustani). + **subgenre profiles** (tempo/rhythm/register + drum vocabulary). + `tests/test_knowledge.py`. | `raga.py`, `talas.py`, `subgenres.py` | (done) |
| **2** | **CrewAI Flow + agents + prompts(md)** — generators emit JSON; Ustad validates via tool; Rasik scores; on Ustad↔Rasik conflict the **Conductor** runs a bounded debate and arbitrates; then revise (capped by `max_rounds`). Headless (prints debate + renders WAV). | `crew/`, `prompts/*.md` | review: patterns #1–#9 in real code |
| **3** | **Mission-control UI** — FastAPI + SSE streaming the debate, swara grid, scorecard, PLAY, A/B, pick menu | `ui/` | review: the event-stream contract |
| **4** | **Live-harden** — pre-warm models, retries/backoff, latency budget, one-key fallback, rehearse the 60–90s flow | resilience layer | review: what "fully live" really costs |
| **S** | Stretch: more ragas/subgenres, multimodal Rasik, audience input | — | — |

Dependency: 1 → 2 → 3 → 4. UI (3) can start against a replay script in parallel once the event contract (end of 2) is fixed.

---

## 6. Weekend timeline

- **Day 1** — Phase 1 (raga library + subgenres) + Phase 2 (Flow + agents + prompts) to a **headless end-to-end**: pick → agents compose → validated → WAV plays. *This is the real milestone; everything after is presentation.*
- **Day 2** — Phase 3 (mission-control UI) wired to the live crew; the debate streams, validation lights up, PLAY works.
- **Day 3** — Phase 4 (live-harden + rehearse), record the teaser clip, polish the two extra raga/subgenre combos.

---

## 7. Risks & mitigations

| Risk | Mitigation |
|---|---|
| **Live latency (60–90s) feels dead** | Stream the debate token-by-token — the wait *is* the show; pre-warm models before the segment. |
| **Debate doesn't converge / hangs live** | Bounded `max_rounds` + the Conductor always issues a final verdict — never wait on organic consensus. |
| **Wrong grammar on a raga** | Grammar is hand-encoded **data**, cross-checked against **≥2 reliable Hindustani sources** (ITC-SRA, Rajan Parrikar / parrikar.org, Tanarang, *The Raga Guide*), **Hindustani not Carnatic** (same names, different ragas), and validated deterministically — never LLM-generated live. |
| **Non-idiomatic "in-scale but soulless" output** | Capture **pakad + chalan** per raga; feed them to generators as seeds and let Rasik check the pakad is present. |
| **Model rate limits / network on stage** | Retries + backoff; one-key pre-rendered fallback per menu combo; run the crew on the fastest tier (Flash). |
| **Audio quality varies by subgenre** | Tune soundfont patch + gain per subgenre offline; only ship combos that pass your ear. |
| **Scope creep eats the weekend** | Core vs Stretch is enforced — Core ships first, Stretch only if Core is solid. |
| **You can't explain it in Q&A** (you're reviewing, not writing) | Pattern-explicit code + `PATTERNS.md` + a review checkpoint each phase. |

---

## 8. Prerequisites / to confirm

- [x] **Model decided: Gemini.** Sujit adds `GEMINI_API_KEY` to `.env` (gitignored) at Phase 2; Phase 1 data needs no key.
- [x] **Menu locked:** ragas Bhairavi / Bhimpalasi / Darbari / Bhairav / Malkauns; subgenres progressive / thrash / doom / death.
- [x] **Raga data (Phase 1):** 5 ragas in `raga.py` — allowed swaras, aroha/avaroha, vadi/samvadi, **pakad, chalan**, andolan, thaat, samay, verified against 2 Hindustani sources each (Tanarang + Wikipedia corroboration), sources recorded in code. **Hindustani, NOT Carnatic.** Ektaal *Kat Ta*/*Kat Tin* discrepancy flagged, not guessed. Plus kan/meend ornament support (schema + renderer + validator).
- [x] **Tala data (Phase 1):** 6 talas in `talas.py` (Rupak 7, Jhaptaal 10, Teentaal 16, Keherwa 8, Dadra 6, Ektaal 12) — matras, vibhags, sam/tali/khali, theka bols, 2 sources each. Data = structure; the Tala agent maps subgenre-meter ↔ tala. Drum grooves **generated** at tala×subgenre (no catalogue); subgenre profiles in `subgenres.py` carry the drum vocabulary.
- [ ] The **machine that runs on stage** (this laptop?) — so we rehearse on the real hardware.
- [ ] **Deps via `uv`** — `uv add crewai python-dotenv` at Phase 2; pin Python (`uv python pin 3.13`) if crewai lacks 3.14 wheels. Add `.gitignore` (`.venv/`, `__pycache__/`, `.env`) + `.env.example` at kickoff.

---

## 9. Your review touchpoints (Claude drives, you review)

**After each logical step** (not just each phase), I stop and: (1) explain what was built, (2) teach the underlying agentic pattern, (3) ask you to review — then we proceed. I do **not** run ahead of your review or start building before you say "go."
Goal: by the talk you can explain **every** design choice from the podium.
