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
 Interpreter ─────────────▶  CompositionBrief {only what the user STATED; rest = OPEN}
    │
    ▼
 Pandit  ⇄  Riffsmith  ───▶  Arrangement (the shared "chart")
 (tradition) (metal)         bounded dialogue; Conductor breaks ties
    │
    ▼
 Lead ∥ Riff  (PARALLEL LLM generators, read the same chart)
        + Drone (from the chart)  + Bass + Drums (deterministic, from the riff + tala grid)
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
| **Interpreter** | Extract & validate ONLY what the user stated (raga/subgenre kept if supported, key→Sa, mood passthrough). Invents nothing; **nothing is required** (mood-only OK); unstated dimensions stay OPEN for the composers | text → `CompositionBrief` | Flash |
| **Pandit** (composer, tradition-leaning) | Argue for raga depth: space, ornament, alaap/development, idiom | dialogue turns → `Arrangement` | Flash |
| **Riffsmith** (composer, metal-leaning) | Argue for metal impact: heaviness, riff hooks, aggression, tightness | dialogue turns → `Arrangement` | Flash |
| **Lead** (RagaGrammar) | Melodic lines per section (alaap/taan/lead/solo), seeded by pakad/chalan, kan/meend; voiced as **sitar and/or lead guitar** — solo, unison, octave, or a raga-diatonic third (harmony derived in code) | (section, chart) → lead layer(s) | Flash |
| **Riff** (MetalRiff) | Rhythm-guitar riff, in-raga, subgenre feel/register | (section, chart) → rhythm layer | Flash |
| **Groove / Drums** (Tala) | Kit from the tala×subgenre accent skeleton, **locked to the riff** (kick/crash follow it), feel per section-kind + fills at transitions — **deterministic, no agent** | riff + chart → drums layer | — |
| *Drone (tanpura)* | Sa + companion pad (Pa, or Ma for a Pa-less raga like Malkauns) — **deterministic, no agent** | chart → drone layer | — |
| *Bass* | Doubles the riff's roots in the low register — **deterministic, no agent, locked to the riff** | riff layer → bass layer | — |
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

The two creative generators (Lead and Riff) run **in parallel** (better on stage, and the
audience will ask); the derivable voices — Drone from the chart, Bass and Drums from the
riff — fall out deterministically around them. Lead and Riff still lock together without a
sequential handoff because coherence comes from three places:

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

## Who leads a section: the composers decide (`foreground`)

Real composition has no fixed order — sometimes the bassline comes first, sometimes
the riff, sometimes the melody — and the voice that leads shapes the rest. We model
this WITHOUT a new mechanism: each `Section` already carries a `foreground` (the
voice in the spotlight), and that IS the section's leader. The composers choose it
per section (a creative call, so it lives with them), and different sections can lead
with different voices — a lead-led alaap, a riff-led groove, a drum-led breakdown —
giving any combination.

Orchestration (step 6) gives `foreground` teeth: the leader generates FIRST from the
shared motif, and the supporting voices are seeded with the leader's REALIZED line
("answer this", "lock to this"), not just the abstract motif — so a riff-led section
is genuinely built around that riff, a lead-led section around that melody. This is a
per-section leader→follower dependency layered on top of the parallel default, and
the bass is its standing example (bass always follows the rhythm guitar's roots). It
also dramatizes the composers' opposition: Pandit argues for lead-led sections,
Riffsmith for riff/bass-led ones.

(A genuinely melodic, INDEPENDENT bass lead — bass-first in the strong sense — would
need an LLM bass generator; the deterministic bass gives the locked low-end
foundation now, and a "lead bass" can be added later if a section calls for it.)

---

## The derivable voices: Drone, Bass, and Drums (deterministic)

Three voices are pure FACT or derivation, not creative decisions, so they are CODE
— no agent, no LLM call. This is "agents map to decisions, not instruments" applied
to the whole rhythm section and the drone, and it is why the roster stays lean: only
the two genuinely CREATIVE voices (the Lead melody and the Riff) are LLM generators.

- **Drone (tanpura)** — Sa plus one companion tone, derived from the raga's own
  allowed swaras (`raga.drone_swaras`): Pa where the raga has it, Ma for a Pa-less
  raga like Malkauns (tuned Sa–ma), so the drone is legal in the grammar BY
  CONSTRUCTION and the guardrail can never flag it. Reads the chart; spans the whole
  piece at the lowest register.
- **Bass** — the metal low-end anchor, and the fix for a mix that otherwise sounds
  flat (a distorted guitar is harmonically rich but thin on fundamentals; the bass
  supplies the body and locks the riff to the kick). It is NOT a separate agent: in
  metal the bass follows the rhythm guitar's roots, so it is DERIVED from the riff
  layer — doubling the riff's root notes (or holding them on the accent-grid
  downbeats) in the *rhythm register* (same octave as the downtuned guitar, so it
  never goes subsonic), on a bass patch. It runs right after the Riff generator as a
  deterministic shadow of it, and needs no composer decision and no new contract:
  bass is present wherever the rhythm guitar is, and its notes are already
  raga-legal because they are the riff's. (A melodic/independent "lead bass" for prog
  could become an LLM generator later; the default foundation bass stays code.)
- **Drums** — the kit is GENERATED at the tala×subgenre intersection: the tala's
  accent grid is the rhythmic skeleton (kick on the sam and strong matras, snare on
  the subgenre's backbeat, hats/ride filling the subdivision), the subgenre profile
  supplies the technique (density, double-kick, blast beats), and — like the bass —
  the kit READS the riff so the kick and crashes LOCK to it rather than to a canned
  pattern. Feel changes per section kind (a breakdown crushes half-time, a taan
  doubles up, an alaap drops the kit for tabla), and a rule drops a fill into each
  transition. If those rule-based fills ever sound canned, a small LLM pass over just
  the transition bars (reading the composers' `transition` text) is the one place an
  agent might later earn its keep — added only if listening proves the rule short.

**Audience Q&A answer (why is there no bass or drum agent?):** "The bass and the drum
groove both FOLLOW the riff — they're derivable, not creative decisions — so they're
deterministic code, not LLM calls. That's the rule that keeps the roster lean: an
agent is a DECISION (intent, arrangement, legality, taste), never an instrument. The
drone, the bass, and the groove are all facts or derivations the code can supply, so
they cost nothing and can't hallucinate — leaving the model budget for the two voices
that are genuinely creative, the raga lead and the metal riff." (Reinforces "code
does the derivable, the LLM does the creative" at the level of the roster itself.)

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
| **`CompositionBrief`** | Interpreter | ALL fields optional — only what the user stated (raga/subgenre validated against the libraries and kept only if supported; key→Sa; mood passthrough). Unstated = None = "OPEN, composers decide." |
| **`Arrangement`** (the "chart") | Composers | ordered sections (type, bars, active layers), **tala accent grid**, **register per voice**, **shared motif** (from pakad), dynamics/foreground — rich enough that parallel generators reading it interlock |
| **`Composition`** | Generators (assembled) | the swara-JSON the renderer consumes (already defined) |
| **`DebateEvent` stream** | every step | `{type, agent, role, text, verdict?, scores?}` — same shape live or replay |

---

## Operating rules (settled)

- Prompts live as **CrewAI classic YAML** (`crew/config/agents.yaml` + `tasks.yaml`, `@CrewBase`).
- **Interpreter extracts only, never invents** — captures just what the user stated, leaves
  the rest OPEN; the composers make the creative calls (including the raga, from the mood).
  It never blocks. Prompt rules + examples carry the "leave it null" faithfulness — do NOT
  raise reasoning effort to paper over a weak prompt (prompt first).
- Composers converge in **~2–3 turns** or the Conductor decides; `MAX_ROUNDS = 2` for revise.
- Revise is **surgical** — only the flagged layer regenerates; the Arrangement stays fixed.
- Generators **parallel**; the composer dialogue and the critic debate are the two bounded
  loops. See `CLAUDE.md` for the CrewAI + code-organization rules that all of this obeys.

---

## Model tiering (tune after a working baseline)

Tier by cognitive load, but only *after* the loop works end-to-end on uniform **Flash-low**
— you can't judge a "cheaper here costs quality" tradeoff before you can hear the output.
Per-role model/effort are env-overridable in `crew/config.py`, so tiering is a cheap change.

| Load | Agents | Plan |
|---|---|---|
| low | **Interpreter**, **Ustad** (narrates a *deterministic* result), *Groove* (rule-driven) | → flash-lite / minimal effort later |
| medium | **Lead**, **Riff** | keep Flash |
| high | **Pandit**, **Riffsmith**, **Rasik**, **Conductor** | keep Flash now, → **Pro** later |

The story: spend model budget where *judgment and creativity* live; go cheap where the work
is *extraction* or *deterministic narration* — the "code does the checkable, LLM does the rest"
thesis applied to model choice. (`gemini-3.1-flash-lite` id is unverified — confirm before use.)

## Build order (one agent at a time, with review between)

1. ✅ Contracts — `CompositionBrief` + `Arrangement` (the chart).
2. ✅ **Interpreter** — agent #1 (structured extraction + validation-at-the-boundary).
3. ✅ **Pandit ⇄ Riffsmith** — the bounded composer dialogue producing the Arrangement.
4. **Generators** — the two creative LLM voices (**Lead**, **Riff**) plus the derivable
   voices (**Drone** from the chart; **Bass** and **Drums** from the riff). *DONE: Drone,
   Lead (+ sitar/guitar voicing), Riff, Bass, Groove/Drums, Tabla theka, and the full-band
   assembly (`crew/band.py`, chart -> every voice -> Composition -> WAV). Remaining: the
   foreground leader/follower LLM-seeding (lead ⇄ riff), which lands with the Flow (step 6).*
5. **Ustad / Rasik** — the critics. *(not started)*
6. **Conductor + the Flow** — arbitration, the bounded loops, the foreground leader/follower
   ordering, end-to-end render. *(not started)*

*Not in the original list but added along the way:* **local tracing + trace portal**
(`crew/tracing.py`, `crew/trace_portal.py`) and an **interpreter eval harness**
(`crew/evals.py`) — on by default so every LLM run is inspectable (see CLAUDE.md
"Observability").
