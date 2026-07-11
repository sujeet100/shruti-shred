# Agentic flow design (Phase 2)

*The detailed agent architecture, decided in the 2026-07-11 design brainstorm. `PLAN.md`
is the roadmap; `CLAUDE.md` holds the always-on rules; `TALK.md` is talk prep. This file
is the reference for **how the crew is wired** — read it before building any agent.*

---

## Guiding principle: agents map to DECISIONS, not instruments

The naive instinct is one agent per track — sitar agent, drums agent, tabla agent, solo
agent, harmonizer agent — which balloons to ~15 agents and, worse, organizes by *type*
(the same mistake as a `utils.py`). Instruments are **data** (`layers` in the composition
JSON), rendered deterministically; "taan", "solo", and "harmony" are **sections/modes** a
generator emits, not agents. So agents are drawn along **responsibilities/decisions**:
understand intent, arrange the form, generate content (by musical function), judge
legality, judge taste, arbitrate. ~7 agents, not 15. On stage this also matters: every
agent is an LLM call, so the wrong axis means far more latency, failure surface, and a
debate too noisy to follow.

---

## The flow

```
"metal fusion in Malkauns, key of D"
    │
    ▼
 Interpreter ─────────────▶  CompositionBrief {raga, sa, subgenre, bpm, instruments}
    │
    ▼
 Pandit  ⇄  Riffsmith  ───▶  Arrangement (the shared "chart")
 (tradition) (metal)         bounded dialogue; Conductor breaks ties
    │
    ▼
 Lead ∥ Riff ∥ Groove  (PARALLEL, read the same chart)  +  Drone (deterministic)
    │
    ▼
 assemble Composition JSON
    │
    ▼
 Ustad (legality)  +  Rasik (taste + coherence)
    │
    ▼
 conflict? ──▶ Conductor: bounded debate ──▶ accept | revise (surgical)
    │                                              │
    │◀─────────── regenerate only the flagged layer ┘   (≤ MAX_ROUNDS)
    ▼
 render WAV
```

Two genuinely different multi-agent patterns are on show: the composers **collaborate to
create** (opposed emphases, shared goal), and the critics **adversarially judge** the
result (arbitrated with a clock). That contrast is a core teaching beat.

---

## Roster

| Agent | One responsibility | In → Out | Tier |
|---|---|---|---|
| **Interpreter** | Free-text query → validated brief; map mood→subgenre, key→Sa; fill grounded defaults; never block | text → `CompositionBrief` | Flash |
| **Pandit** (composer, tradition-leaning) | Argue for raga depth: space, ornament, alaap/development, idiom | dialogue turns → `Arrangement` | Flash |
| **Riffsmith** (composer, metal-leaning) | Argue for metal impact: heaviness, riff hooks, aggression, tightness | dialogue turns → `Arrangement` | Flash |
| **Lead** (RagaGrammar) | Melodic lines per section (alaap/taan/lead/solo), seeded by pakad/chalan, kan/meend | (section, chart) → lead layer | Flash |
| **Riff** (MetalRiff) | Rhythm-guitar riff, in-raga, subgenre feel/register | (section, chart) → rhythm layer | Flash |
| **Groove** (Tala) | Drums (± tabla) from the tala×subgenre accent skeleton | (section, chart) → drums layer | Flash |
| *Drone (tanpura)* | Sa+Pa pad — **deterministic, no agent** | — | — |
| **Ustad** | Legality/theory — calls `validate_composition` (the hard guardrail) | composition → verdict + violations | Flash→Pro |
| **Rasik** | Aesthetic/rasa: pakad present, idiom, mood-fit, **ensemble coherence** | composition → scores + notes | Flash→Pro |
| **Conductor** | Arbiter: composer tiebreak; on Ustad↔Rasik conflict run the bounded debate, rule accept/revise, cap rounds | verdicts → decision | Pro |

---

## The composers: opposed, collaborating (the "conversation" showcase)

**Pandit and Riffsmith hold opposite emphases but share one goal** — a great fusion. Opposed
priors are deliberate: two *neutral* agents collapse into sycophantic agreement-theater with
no tension to watch and no exploration of the design space. Opposition dramatizes the
project's whole thesis (tradition ⇄ transgression) as a live negotiation and forces real
exploration of "how traditional vs. how aggressive."

They argue about **creative direction** (what to make), which is distinct from Ustad/Rasik
who judge **the finished result** — different pipeline stage, different question, no overlap.

**Mechanism (important):** the dialogue is orchestrated **explicitly in the Flow**, NOT via
CrewAI's autonomous `allow_delegation`/hierarchical delegation. We hold the **transcript**
and the **evolving draft** in shared Flow state and loop turn-by-turn (Pandit speaks →
Riffsmith responds → …) for a **bounded** number of exchanges (~2–3), ending on agreement or
the **Conductor breaking the tie**. The transcript *is* them talking — but we own the loop,
so it's bounded, streamable, and legible ("visible patterns, not autonomous magic"). This is
also what fills the live wait: the streamed conversation is the show.

---

## The generators: PARALLEL, coordinated by the chart

The three generators run **in parallel** (better on stage, and the audience will ask). They
still lock together without a sequential handoff because coherence comes from three places:

1. **Free shared constraints** — same raga (legal notes), key/Sa, tala grid, bpm, sections.
   This alone prevents the train-wreck failures.
2. **The Arrangement as a shared "chart"** — it pins the **tala accent grid** (so riff and
   kick interlock by design), a **register per voice** (lead high / riff low / drone lowest,
   so they can't collide), and a **shared motif** drawn from the pakad (common melodic DNA).
   Parallel generators reading the same chart are like session players reading a chart —
   independent but locked, not improvising blind.
3. **The critique loop as the safety net** — after assembly, Rasik checks ensemble coherence
   (interlock / register clash / too busy); if a layer doesn't fit, the Conductor's
   **surgical revise** regenerates only that layer. No separate generator loop.

**Trade-off (accepted):** parallel-against-a-chart clashes a little more on the first pass
than a sequential handoff would, so the coherence-revise fires more often — which on stage is
a *good* moment (watch the critic catch a clash and fix it). **Fallback** only if it proves
too clash-prone in rehearsal: let Groove commit its accent grid just before Riff/Lead.

**Audience Q&A answer (parallelism):** "The three generators run concurrently and still lock
together because the two composers already agreed on a shared chart — the tala's accent grid,
a register for each voice, and a common motif from the raga's pakad. They read the same chart
like session players, not blind. And if two parts still clash, that's what the critics are
for: Rasik flags it and we regenerate just that layer. Parallel speed, coherence from the
shared plan plus the review loop." (Showcases three patterns at once: parallel fan-out,
plan-as-contract, guardrail/critique loop.)

---

## The critics + Conductor (the "judgment" showcase)

- **Ustad** — legality/theory, backed by the deterministic `validate_composition` **tool**
  (used both as the mandatory guardrail and as a tool Ustad calls to *explain* a violation).
- **Rasik** — aesthetic/rasa on an explicit rubric grounded in the encoded pakad/chalan
  (criteria, not vibes): is the pakad present, is it idiomatic, does it serve the raga's mood,
  and do the parts cohere as an ensemble.
- **Conductor** — the referee with a clock. On an Ustad↔Rasik conflict it runs the bounded
  debate and issues **accept** or a **surgical revise** directive (which layer, why), capped
  at `MAX_ROUNDS`. Also breaks composer ties. Debate never relies on organic consensus.

---

## Contracts (Pydantic, in `crew/contracts.py`)

| Contract | Producer | Carries |
|---|---|---|
| **`CompositionBrief`** | Interpreter | raga, Sa/key, subgenre, bpm, instruments, length target — validated against the data libraries (unknown raga fails at the boundary) |
| **`Arrangement`** (the "chart") | Composers | ordered sections (type, bars, active layers), **tala accent grid**, **register per voice**, **shared motif** (from pakad), dynamics/foreground — rich enough that parallel generators reading it interlock |
| **`Composition`** | Generators (assembled) | the swara-JSON the renderer consumes (already defined) |
| **`DebateEvent` stream** | every step | `{type, agent, role, text, verdict?, scores?}` — same shape live or replay |

---

## Operating rules (settled)

- Prompts live as **CrewAI classic YAML** (`crew/config/agents.yaml` + `tasks.yaml`, `@CrewBase`).
- **Interpreter never blocks** — fills grounded defaults (subgenre from `raga_affinity`, bpm
  from the subgenre range, Sa from key or default D) and emits the assumption as an event.
- Composers converge in **~2–3 turns** or the Conductor decides; `MAX_ROUNDS = 2` for revise.
- Revise is **surgical** — only the flagged layer regenerates; the Arrangement stays fixed.
- Generators **parallel**; the composer dialogue and the critic debate are the two bounded
  loops. See `CLAUDE.md` for the CrewAI + code-organization rules that all of this obeys.

---

## Build order (one agent at a time, with review between)

1. Contracts — `CompositionBrief` + `Arrangement` (the chart).
2. **Interpreter** — agent #1 (structured extraction + validation-at-the-boundary).
3. **Pandit ⇄ Riffsmith** — the bounded composer dialogue producing the Arrangement.
4. **Lead / Riff / Groove** — parallel generators reading the chart (+ deterministic Drone).
5. **Ustad / Rasik** — the critics.
6. **Conductor + the Flow** — arbitration, the bounded loops, end-to-end render.
