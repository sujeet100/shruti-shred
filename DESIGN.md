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
5. ✅ **Ustad / Rasik** — the critics, the two OPPOSITE judgment patterns.
   - **Ustad** (`crew/ustad.py`) — the legality critic. Code owns the verdict (deterministic
     `validate_composition`), the LLM only narrates: the type split (`UstadNarration` has no
     verdict field → code assembles `UstadVerdict`) makes "code decides the checkable"
     structural. The validator is BOTH the generator guardrail and a tool Ustad calls to
     explain a violation.
   - **Rasik** (`crew/rasik.py`) — the taste critic, LLM-as-judge. Taste is not checkable, so
     the LLM owns the verdict; the bias is countered by a fixed 1-5 rubric (`RasikScores`:
     pakad/idiom/mood/coherence), scores grounded in encoded pakad/chalan/rasa facts + a
     code-computed pakad hint (`pakad_presence`), and a per-criterion justification.
6. ✅ **Conductor + the Flow** — arbitration + the bounded loops + end-to-end render.
   - **Conductor** (`crew/conductor.py`) — the arbitration half (the money moment).
     `detect_conflict` is pure CODE triage (illegal ⇒ forced revise no debate; legal+satisfied
     ⇒ accept; legal+weak ⇒ the aesthetic conflict); the Ustad↔Rasik debate is a we-own-it
     bounded loop capped by `MAX_ROUNDS`; the Conductor always rules at the cap with a surgical
     `ConductorRuling` (one layer, one reason).
   - **The Flow** (`crew/flow.py`) — the whole pipeline as one bounded CrewAI `Flow`
     (`compose_flow(query)`): interpret → composers → generate → critics → Conductor →
     (surgical revise)* → render. The `@router` on `state.round` is the terminator; the revise
     regenerates ONLY the flagged voice (directive threaded via `revise_arrangement`) and
     re-derives the rest. Steps injected as a `Stages` bundle → fully tested with no LLM.
     *CrewAI gotcha: the loop-back must be a router LABEL (`revise_layer` is a `@router`
     re-emitting "recritique") — a plain method-completion `or_()` fires once; only router-label
     `or_()` listeners re-arm for a cycle.*
   - **Deferred (optional refinements):** the **foreground leader/follower LLM-seeding** (lead ⇄
     riff) and the Conductor's **composer tie-break** (today the last composer draft stands).

*Not in the original list but added along the way:* **local tracing + trace portal**
(`crew/tracing.py`, `crew/trace_portal.py`) and an **interpreter eval harness**
(`crew/evals.py`) — on by default so every LLM run is inspectable (see CLAUDE.md
"Observability").

---

## Next: audio production & riff voicing (decided 2026-07-12, not yet built)

Phase 2's pipeline is complete end-to-end, but a listen (`out/flow_demo.wav`) exposed
**mix/production** gaps that the agents cannot catch — because the whole loop is
symbolic and **no agent ever hears audio**. This is a genuine design insight worth its
own talk beat: *a critic can only critique what it can perceive, and ours perceive
symbols, not sound.* Concretely, nothing complained about a bass-like rhythm guitar or
a sitar indistinguishable from the lead guitar because (1) timbre/register/pan live only
in the rendered WAV, which no agent sees; (2) the `RiffNote` contract can't even express
a power chord / palm-mute / bend, so the absence is unrepresentable; and (3) the critics
aren't shown the riff — Ustad checks only note-legality (the riff *was* legal), and Rasik
judges the **lead** line plus an abstract ensemble summary, never the riff's notes. So
mix/timbre fixes belong in **deterministic code**; making a critic *able* to complain
would mean feeding Rasik the riff + a "metal idiom" lens.

**✅ Mix pass — DONE (commit `40048f6`).** `Layer.pan`/`Voice.pan` + MIDI CC10 in
`src/render.py`; bass an octave below the guitar (`_BASS_FLOOR`); guitar floored at oct −2
(`_RHYTHM_FLOOR`); sitar (left) / lead-guitar (right) pan opposite; rhythm double-tracked
hard L/R via `generators.double_track` (left = Overdriven GM30 pan 20, right = Distortion
GM31 pan 108, ~10 ms Haas offset + slight vel drop); bass/groove/tabla still derive from the
ORIGINAL riff. Covered by `tests/test_generators.py`. (Not yet heard — batched for the final
live render per "no LLM runs until all changes done".)

**✅ Riff voicing + technique — DONE (2026-07-12, step 2).** `chord`/`technique` on
`RiffNote` + `Note` (contracts), rendered in `src/render.py` (`_stack_above` seats each
chord tone at the lowest octave over the root; `_apply_technique` does the palm-mute chug
+ legato attack; `_render_slide`/`_render_bend` are pitch-wheel gestures, armed via
`_bends`). Chord tones face the grammar in BOTH `validate_composition` (kind `"chord"`) and
the riff guardrail, so a power chord is legal-by-construction. Plumbed through
`_sequence_cycle`/`place_riff` (model_copy) and taught in the `generate_riff` prompt +
`_OUTPUT_SCHEMA`. Pure tests: `tests/test_render.py` (new), `tests/test_riff.py`,
`tests/test_knowledge.py`. NOT yet heard — batched for the final live render (slide/bend
audio quality needs Sujit's ear then). Design as-built (kept for the record):
- **Extended chords, legal-BY-CONSTRUCTION.** Add `chord: Optional[list[str]]` to `RiffNote`
  (and to the render-time `Note`): extra swaras sounded WITH the root, each a legal raga
  swara (same guardrail check as the root — extend `raga.validate_composition` to check chord
  tones too). The renderer sounds them **stacked UPWARD from the root** (each chord tone at
  the lowest octave whose pitch is > the root's). That single rule yields everything Sujit
  asked for and stays in-raga: a fifth = `["P"]`; a root+octave power chord = `["S"]` (the
  repeated root lands an octave up); a prog extended voicing = e.g. `["g","n"]` (stack raga
  color tones). NO fixed +7 fifths — the palette IS `RAGAS[raga]["allowed"]`.
- **Techniques.** Add `technique: Optional[Literal["palm_mute","slide","bend","hammer_on",
  "pull_off"]]` to `RiffNote`/`Note`. Render mappings: **palm_mute** → dur ×~0.5 + vel ×~0.9
  (the chug — solid, pure-testable); **slide** → brief pitch-bend ramp −2 st → 0 into the
  onset; **bend** → pitch-bend 0 → +2 st over the first half; **hammer_on/pull_off** → softer
  attack velocity (legato approximation). Reuse `_arm_bend_range`/`_render_meend` machinery;
  arm the rhythm channel's bend range if any note slides/bends. **Caveat:** the rhythm channel
  is now polyphonic (chords), and pitch-bend is channel-wide — so a *slid power chord* bends
  the whole chord together (correct!), but a bend on one note of a sustained chord bends the
  chord (acceptable). Riff notes are laid end-to-end, so reset the wheel to 0 at each note end.
  Slide/bend audio quality needs Sujit's ear at the final render.
- **Plumbing:** `RiffNote` → `Note` copy of `chord`/`technique` in `riff.py` `_sequence_cycle`;
  extend the riff guardrail (`_riff_guardrail`) + `validate_composition` to check chord tones;
  update the `generate_riff` prompt (extended raga voicings + the technique vocabulary +
  legal-only). Pure tests: chord placement + legality (guardrail catches an illegal chord
  tone) + technique passthrough + a chord-stacking pitch-math helper + palm_mute dur/vel.

---

## External review triage (GPT **and** Gemini on `REVIEW.md`, 2026-07-12)

Two independent expert reviews. Both rate the ARCHITECTURE stronger than the prompts,
both bless the core theses (decisions-not-instruments; code-owns-facts/LLM-owns-judgment;
bounded loops), and — the strongest signal — **both independently name the Ustad↔Rasik
debate as the weakest link.** Where they converge = highest confidence.

**BOTH FLAGGED (act on these first):**
- **The critic debate is theater — and the real fix is to CHANGE THE COUNTERPART.** By the
  time the debate triggers the piece is already legal, so Ustad has NO aesthetic stake —
  "it lacks soul" vs "but it passes the rules" is a non-contest. Fix (Gemini's, sharper
  than GPT's cross-examination): Ustad EXITS the debate (its job ends at triage); reframe
  it as a genuine AESTHETIC argument — **Rasik (soul/tradition → revise) vs a Producer /
  impact voice (momentum/energy → ship, a revise risks the drive)** — refereed by the
  Conductor, kept to one sharp exchange. This mirrors the Pandit⇄Riffsmith tension at the
  JUDGE stage. *Decision for Sujit: add a "Producer" critic or repurpose Riffsmith.*
- **`compose_turn` is overloaded** (read state + argue + draft + design seams + negotiate a
  tihai, all in one turn). Decompose: move the structural asks (seams/unison) into HARD
  RULES or subgenre-driven sub-tasks; compress; move INVARIANT text (sargam legend,
  ornament tutorial, octave map) to the agent backstory / system side.
- **Structured-output robustness — stop relying on provider-native strict JSON.** It
  hard-fails on `{}`/`null`/`"null"` BEFORE our guardrail can retry (the `_clean_meend`
  bug). Gemini's fix: request a text/markdown JSON block, `json.loads` it in our shell,
  and on failure feed the error back as a bounded retry. Also minimize optional+nullable
  fields (LLMs love emitting nullish). *(Investigate whether CrewAI lets us opt out of
  native structured output and parse manually.)*
- **`pakad_presence` literal match is too brittle** — one valid grace note inside the
  phrase breaks it. Make it a FUZZY subsequence match (pakad notes in order within a
  window, ignoring intervening grace/duration).
- **Live latency is the top stage risk.** Our answer: the **streamed debate IS the filler**
  (the wait is the show). Harden with (a) a **fast mode** (skip both dialogues unless the
  audience asks to see the agents argue), (b) a **failsafe pre-rendered chart** per
  raga×subgenre if the renderer throws (audience hears music, never silence), and (c) run
  **Lead ∥ Riff truly concurrently** (today `compose_band` runs them sequentially).

**DIVERGENCE (resolved by our judgment):**
- **Reasoning-first:** GPT says drop it from Lead/Riff (weak ROI); Gemini says keep it
  EVERYWHERE (best defense against schema hallucination). Given we JUST hit schema
  fragility, **keep it** — but allow a SHORT reasoning in the generators. Gemini's
  robustness argument outweighs GPT's token cost here.

**ADOPT (GPT, thesis-aligned):**
- **Precompute measurable facts for Rasik to JUDGE, not measure** — vadi-emphasis
  (weighted duration on the vadi), pakad-coverage %, phrase-ending / resting-note
  distribution, register overlap. Hand Rasik numbers; it judges. *(Best single idea.)*
- **A computed CONSISTENCY analysis** over the whole piece (motif similarity, density
  curve, repetition ratio, register overlap, rhythmic entropy), LLM explains — a
  cross-section dimension distinct from legality and taste. Biggest MISSING check.
- **Composition MEMORY** — generators see the realized previous sections (motifs,
  cadences, call/response), not just the abstract chart, so the music DEVELOPS. Biggest
  architectural gap; subsumes the deferred foreground-seeding.
- **Hybrid conflict triage** — weighted overall OR a critical criterion (pakad/idiom) low;
  don't let a lone mediocre `mood` trigger the debate.

**ADOPT (both, easy hygiene):**
- **Anti-sycophancy pacing** — the composers' "concede gracefully" risks folding on turn 1;
  add "do NOT concede your core priorities on turn 1; defend fiercely; compromise only
  later." (GPT's asymmetric-emphasis is a deeper fix for the same convergence problem.)
- **Split HARD CONSTRAINTS (enforced) from SOFT STYLE (guidance);** reframe negative rules
  as positive ("Only extract a raga if explicitly written" > "Do NOT invent a raga").
- **Flag agreed-upon points in `{current_draft}`** so a late composer turn can't regress a
  prior concession.

**KEEP AS-IS (pushed back):**
- **Do NOT merge Lead & Riff** (GPT) — same abstract shape, different musical DECISIONS and
  diverging contracts (riff gains chords/techniques; lead has ornaments/cross-octave).
- **Keep the Interpreter as an agent** (Gemini would demote it to a zero-shot call) — it's
  already cheap, and "agent #1 = the front door / validate-at-boundary" is a teaching beat.
- **Keep Ustad's name** — but it now EXITS the debate (its legality job ends at triage).

### The Producer — a THIRD critic dimension (Sujit's notes, 2026-07-12; reshapes steps 3+5)

Sujit's review sharpened the Producer well past DESIGN.md's original "impact/momentum
debater": today **Rasik does two different jobs** — classical connoisseurship AND
songwriting critique — and they pull apart. There are three distinct questions about a
piece of music: (1) is it LEGAL? (Ustad), (2) does it sound like the RAGA? (Rasik), (3)
does it WORK AS A PIECE OF MUSIC? (Producer). Rasik was answering (2) and (3) at once.
So we split them, one dimension per critic:

- **Ustad → legality** (code decides, LLM narrates). Unchanged. EXITS the debate.
- **Rasik → raga authenticity** — NARROWS to the uniquely Hindustani questions: pakad
  present, chalan movement, idiomatic ornaments, rasa, an expressive-not-scalar lead.
  `RasikScores` drops `coherence` and renames `mood`→`rasa` → **{pakad, idiom, rasa}**.
- **Producer → composition quality** (NEW critic, raga-AGNOSTIC — doesn't care if it's
  Malkauns or Yaman, only whether the song works). Owns the things nobody checks today, as a
  **9-criterion** 1-5 rubric (Sujit chose the finer split): **structure** (sections lead
  onward), **dynamics** (energy actually builds), **climax** (earned peak + resolution),
  **motif** (introduced→repeated→varied→resolved — "the biggest omission today"), **hook**
  (riff memorable/loopable/strong downbeat), **balance** (arrangement space — not everyone
  playing always), **independence** (lead≠riff, bass≠riff, drums≠tabla), **mood_fit**
  (holds the requested SUBGENRE mood — no bright power-metal solo in a doom piece), and
  **repetition** (added chunk C — enough return/reinforcement without monotony; "AI under-repeats").
- **Conductor → arbitration.** Unchanged role; now refereeing **Rasik (soul) vs Producer
  (works-as-music)** — two GENUINE aesthetic stakes, a far better contest than "soul vs
  legality" (a non-contest once the piece is already legal).

**Staging (Sujit chose "LLM first, metrics next"):**
- **CHUNK A (this step):** the LLM Producer reasons over the SYMBOLIC arrangement +
  composition it is shown (section timeline, motif, riff line, lead line, ensemble,
  subgenre) — no computed metrics yet. Narrow Rasik. Debate becomes Rasik↔Producer. Flow
  runs THREE critiques. Hybrid triage over BOTH aesthetic critics. All pure-testable.
- **CHUNK B (✅ DONE — absorbs old step 5):** "code measures, LLM evaluates" — `crew/metrics.py`
  (pure) computes the per-section dynamics/energy curve (active voices, note density, mean
  velocity), the peak/resolution/flatness of the arc, `motif_share` (lead notes drawn from the
  motif → developed vs abandoned vs never-varied), `lead_riff_overlap` (independence), register
  overlaps + the everyone-playing fraction (balance). `render_metrics` hands them to the Producer
  as a grounding block (as `pakad_presence` grounds Rasik). The Producer JUDGES the numbers; it
  does not measure. Pure tests: `tests/test_metrics.py`.
- **CHUNK C (✅ DONE — closes the deltas vs ChatGPT's full 10-point list):** added the missing
  metrics + the `repetition` criterion. `crew/metrics.py` now also computes `motif_recurrence`
  (fraction of sections that RESTATE the motif contiguously — theme return, the flip side of
  motif_share → repetition/motif), `section_variety` (distinct kinds/total → repetition:
  through-composed vs recurring), `bass_riff_overlap` + `drums_tabla_overlap` (independence: a
  bass merely doubling the riff, kit and tabla in lockstep), and per-section `ornament_rate`
  (kan/meend density → climax/expressiveness). Audit of the 10-point list + coverage is in the
  session notes; the only items left to the LLM (no clean metric) are riff catchiness and
  subgenre mood, which are genuinely subjective.

**Hybrid triage (both aesthetic critics):** illegal ⇒ forced revise (Ustad). Else the
debate opens if EITHER Rasik OR Producer is dissatisfied — a CRITICAL criterion below the
pass line (Rasik: pakad/idiom; Producer: motif/structure) OR that critic's overall mean
below `RASIK_OVERALL_FLOOR` — so a lone weak non-critical criterion doesn't burn a debate.
Else accept. The Conductor then decides whether either concern is worth the single revise.

**Roadmap — Sujit chose "do all together" (one campaign, committed in tested chunks;
Producer as a 3rd critic). Progress:**
1. ✅ **Mix pass** (deterministic) — DONE, commit `40048f6`.
2. ✅ **Riff extended-chords + techniques** — DONE (contract + render + guardrail + prompt + tests).
3. ✅ **Producer as the 3rd critic + reframe the debate** — DONE (chunks A+B+C above). Ustad
   EXITS the debate; Rasik narrows to authenticity; new Producer (composition quality, 9-criterion
   rubric grounded in `crew/metrics.py`) debates Rasik; hybrid triage over both.
4. ✅ **Composition memory** — DONE. Each Lead/Riff section is generated seeing the REALIZED
   prior sections (`LeadMemo`/`RiffMemo`, threaded through `generate_lead`/`generate_riff` and
   rendered as a `{previous}` block), so the music DEVELOPS — restate/vary the motif, answer the
   previous section, bring back the main riff (a hook), reserve the peak for the climax — instead
   of collaging unrelated ideas. Within-voice for now; cross-voice seeding (lead sees riff) stays
   deferred. Pure tests in `tests/test_lead.py`, `tests/test_riff.py`.
5. ✅ **Producer's computed metrics** (chunks B+C above — "code measures, LLM evaluates"), DONE.
   A computed cross-section consistency check remains open (can fold into `metrics.py`).
6. ✅ **Structured-output robustness** — DONE. Verified `gemini/gemini-3.5-flash` runs on the
   NATIVE `GeminiCompletion` provider → native controlled generation, so the reviewers' "parse it
   yourself" concern targets the LiteLLM path we DON'T use → the manual JSON text-parser was dropped;
   the complex `meend` union was flattened to `meend_swara` + `meend_oct` (`e5e5d53`); and **fuzzy
   `pakad_presence`** shipped (commit `5c3cfa3`) — a three-state hint (literal / fuzzy / absent) where
   the fuzzy tier is a bounded-gap in-order subsequence, so a stray grace note no longer breaks the
   match. See PROMPTING.md §2.
7. ✅ **Prompt hygiene** (PROMPTING.md) — DONE (commit `c3c5346`): **positive-over-negative**
   (interpreter goal + the `Do NOT` lines), **per-criterion 1/3/5 judge anchors + anti-length lines**
   for Rasik and the Producer, the **rubric/scoring instruction placed AFTER the composition data**,
   and **dialed-back ALL-CAPS** mandates. Few-shot landed where it earns its tokens — a worked
   transformation example in the rewritten `generate_lead` (step 9).
8. **Live-hardening** — ⏳ STILL OPEN. fast mode; failsafe pre-rendered chart; concurrent Lead∥Riff.
   ALSO fold in the **temperature/reasoning reconciliation** (see the OPEN TENSION below) — needs a
   live A/B. (A couple of bounded live renders were run this session to confirm steps 6/7/9/10 by
   ear, but the hardening + temp A/B themselves are not done.)
9. ✅ **Lead compositional craft — `phrase_plan`** — DONE (commit `1a0fefb` code + `c3c5346` prompt).
   External review (GPT+Gemini) and our own live render agreed the lead produced a straight SCALE run,
   not a raga taan. Crucially, **Rasik CAUGHT it** ("the scalar run dilutes the raga; use vakra
   phrasing + andolan on komal g/d") — proving the critic works but the GENERATOR couldn't act on the
   directive. The bug was concrete: the old prompt literally told a taan to "run along the aroha and
   avaroha." Fix, generation-side: a **REQUIRED `phrase_plan`** (seed / contour / transformations /
   climax) ordered BEFORE `notes` in the schema (reasoning-first made structural — the model must
   DESIGN before it writes), plus a rewritten prompt that builds the taan from chalan/vakra fragments
   (sequencing, question-answer, contour, ~80% from pakad/chalan). Live-confirmed: the taan went from
   a straight run to a pakad-derived, rhythmically-varied line and Rasik's idiom read rose.
10. ✅ **Meend realism** — DONE (commit `1a0fefb` density guard + `6b6f897` render). Diagnosed by ear
    plus pitch-contour + FFT measurement: the meend was pitch-CORRECT (lands on the swara; bend range
    honored) but sounded out of tune on EVERY patch (flute/synth/guitar/sitar), so it was the GESTURE,
    not the sitar sample or the renderer. The old glide crawled LINEARLY over 60% of the note, dwelling
    audibly on the out-of-scale micro-pitches. Two-part fix: (a) a **density guard** strips meend from
    sub-beat notes so fast taan runs articulate cleanly (kept on held/cadential notes; direction free —
    kan/khatka/murki/meend all bend either way); (b) the render is now a **quick, capped, cubic-ease-out
    pull ANCHORED ON THE TARGET** — the note sounds at the target's home sample, the wheel pre-bends to
    the source and eases to 0, and it ends at 0 (no bleed). See the research notes below.

**OPEN TENSION (decide in the live pass, do NOT silently flip):** PROMPTING.md §3 — Google
STRONGLY recommends **temperature 1.0 for the Gemini-3.x family** and warns <1.0 degrades reasoning
(looping/flat output), yet our critics run 0.2 and the extractor 0.0. And the CLAUDE.md premises
"Gemini has no reasoning-effort knob" / "temperature is the main steering knob" are STALE — the code
already passes `reasoning_effort="low"` and Gemini 3 exposes `thinking_level`. Resolve EMPIRICALLY:
run a critic at 0.2 vs 1.0 on a fixed composition, read both traces, keep the stabler one; then
reconcile `crew/config.py` temperatures + the CLAUDE.md wording.

### Meend realism — research notes (2026-07-12, from the live audio review)

Replicating a sitar meend in a MIDI + SoundFont(FluidSynth) pipeline (subagent research, cited):
- **A real meend is a single-pluck, EASED glide** (low-order polynomial, not linear); the transition
  occupies a MINORITY of the note and the endpoints are HELD. The origin pitch also keeps ringing on
  the fixed-tuned SYMPATHETIC strings — an anchor a single bent GM sample cannot reproduce (the hard
  ceiling on realism). Upward bends lose HF energy. (ISMIR 2022 sitar-bend spectrogram abstract;
  Hindustani-MIR contour-transcription work; UNSW portamento-perception notes.)
- **Our fix, in order of impact:** (1) short, interval-scaled, CAPPED glide time (~80–220 ms), not a
  fraction of the note; (2) ANCHOR on the target's home sample (pluck the target, pre-bend to source,
  ease to 0) so the sustain is in tune and natural-timbred; (3) cubic ease-out curve; (4) dense 14-bit
  ramp (~event/6 ms, no zipper). Implemented in `src/render.py`.
- **MIDI portamento (CC5/CC65): supported by FluidSynth but REJECTED** — it only fires between
  overlapping mono/legato notes (fiddly from MIDIUtil) and its glide shape is fixed/untunable, which
  would throw away the ease-out curve that is the actual fix. Keep the manual pitch-wheel path.
- **FluidSynth:** keep default 4th-order interpolation (7th-order can ring); interpolation was a red
  herring. No new renderer or soundfont needed.
- **Deferred polish:** a small CC74 brightness roll-off on ascending meends + light chorus (cheap
  stand-ins for the missing sympathetic strings); and a first-class **andolan** ornament (schema +
  renderer) — the slow oscillation on komal g/d that DEFINES Darbari and is Rasik's standing ask.

**RESUME HERE (2026-07-12):** steps 1–7, 9, 10 DONE + committed (commits `5c3cfa3` fuzzy pakad,
`1a0fefb` phrase_plan + meend guard, `6b6f897` meend render, `c3c5346` prompts). Remaining:
- **Step 8 live-hardening** — fast mode, failsafe pre-rendered chart, concurrent Lead∥Riff; AND the
  **temperature/reasoning A/B** (OPEN TENSION above — resolve EMPIRICALLY, do NOT silently flip).
- **One full-band live render** to hear the taan + clean meend together in context (the isolated
  meend is confirmed good).
- **Deferred meend polish** — CC74 roll-off + chorus; and the **andolan** ornament (the one Darbari
  feature we still can't produce).
- **Triage bite** — make a weak Rasik idiom score actually FORCE a revise (worthwhile now that the
  generator can produce idiomatic phrasing, so a revise has something better to become).
- **★ HEADLINE FEATURE — bounded cooperative collaboration — ✅ BUILT (2026-07-13).** The studio session
  (steps 1–5) is done and green (321 pure tests); opt-in behind `RMA_STUDIO=1`, the parallel path still the
  default. See the dedicated design section below for the as-built breakdown. The talk's second named pattern.

## Headline feature — bounded cooperative collaboration ("the band composes on a canvas")

*Decided 2026-07-12 (Sujit's idea; Claude + GPT independently converged). **BUILT 2026-07-13** — opt-in
behind `RMA_STUDIO=1`, the parallel generate-in-isolation path still the default until it's heard on stage.*

**AS BUILT (steps 1–5, all pure-tested; one step-4 live render confirmed it end-to-end):**
1. **The cooperative loop** — `crew/studio.py::run_studio`: a PURE driver over the bandleader+clock that
   walks each section's schedule, filling a `SectionCanvas`, with the note-writing INJECTED as a
   `contribute` callback (the same seam as the Flow's `Stages`, so the whole loop tests with no LLM).
   `active_roles`/`section_turns` honour which voices actually play (a solo alaap, a silent breakdown).
2. **Canvas-aware generators** — `crew/lead.py`/`crew/riff.py` render a `{move}`+`{canvas}` block so a
   voice ANSWERS what the other just played (respond) or reworks against the ensemble (refine); one prompt
   serves both the studio and the standalone path ("no canvas / propose" ⇒ compose solo). `studio_lead_fn`/
   `studio_riff_fn` are the canvas-aware per-section calls.
3. **The LLM-backed shell** — `crew/studio_session.py::make_contributor`/`compose_studio`: bridges the loop
   to the generators, PRESERVES riff-slot recurrence (a returning hook reprises without an LLM call), and
   assembles the filled canvases into the band's `(lead_layers, rhythm, events)` shape.
4. **Flow wiring** — `_generate` routes to `compose_studio` when `RMA_STUDIO=1` (else parallel); both return
   the same shape so assembly/critics/Conductor/render are untouched. `RMA_CANVAS_PASSES` tunes the fast-mode.
5. **Canvas-aware revise** — the step-4 live render exposed that a surgical revise regenerated the flagged
   voice in ISOLATION, silently OVERWRITING the collaboration (the lead you hear was composed blind). Fix:
   retain the canvases in `ComposeState`, and `regenerate_layer` reworks the flagged voice CANVAS-AWARE (a
   refine turn that still sees the other voice's line). The collaboration now survives the critique loop.
   *Lesson (talk-gold): the cross-voice state must LIVE in durable Flow state, or the revise un-does the
   collaboration.* The parallel path still revises standalone (no canvas to be aware of).

**Deferred (not needed for the pattern):** `SectionIntent` AUTHORING (the leader declaring
energy/tension/groove as a semantic layer the deterministic voices read) — the follower currently answers
the LINE, which is musically legitimate; wire intent-authoring when the drums/bass/dynamics should read it.
A live re-render ON the canvas-aware revise (to HEAR it) is still open — the mechanism is proven by tests.

*(Original pre-build design notes below, kept for the record; the AS BUILT block above supersedes the open
items — leader/follower table, canvas shape, pass count — which are now settled in code.)*

**Why.** The talk needs a SECOND named multi-agent pattern beside the critique loop, and real
collaboration is rarely showcased (most demos are plain workflows — Sujit's differentiator). Musically,
voices are generated in ISOLATION today (why the Producer even scores independence/balance); cross-voice
response yields cohesion. Decision: build **L2/L3 bounded, orchestrated, blackboard collaboration** at the
GENERATION stage — NOT autonomous L4 (agents choosing turn order / termination), which would break the
project's visible-and-terminating thesis and be unsafe live.

**Shape — a "studio session" on a shared canvas:**
- **Blackboard:** a `SectionCanvas` in the Flow state, one per section, holding each voice's current line
  + the leader's seed. Every creative pass reads it and writes back.
- **Agents = the two creative voices ONLY** (Lead ⇄ Riff). Drone/Bass/Drums/Tabla stay DETERMINISTIC and
  arrange themselves around the finished canvas — honors "only 2 LLM voices" and bounds cost to 2 agents ×
  passes.
- **Pass loop (code-terminated, bounded by `CANVAS_PASSES`):** (1) leader proposes → canvas; (2) follower
  responds to the canvas; (3) optional — leader refines given the ensemble. Legality guardrail on each LLM
  contribution. Fast-mode = 1 pass (= L1 seeding) for live safety.
- **Stream the canvas as events** (like the debate stream) so the audience WATCHES the score fill in.
  Gives the talk TWO money moments: the band COOPERATES (build), then the critics DEBATE (argue) —
  cooperate-then-critique, same guarantees, different social dynamic.

**Sequencing (Sujit's question — this IS the design): code decides the order, never the agents** (the
"bandleader + clock").
- **Leader (who goes first) is derived from the SECTION KIND**, by a code rule — not chosen at runtime.
  The composers set the sections + kinds upstream (the chart); code maps kind → leader. Draft rotation:

  | section kind | leader | follower's move |
  |---|---|---|
  | riff / breakdown | Riff | Lead answers sparsely (call/response) |
  | melody | Lead | Riff supports the theme |
  | alaap | Lead (sitar) | Riff lays out (silence is a valid contribution) |
  | taan / solo | Lead | Riff drives the bed underneath |
  | outro | Lead | Riff winds down / resolves |
  | climax | unison (a tihai) | both converge on one figure |

- **Who goes next = the fixed pass loop** (leader → follower → optional refine), code-driven.
- **Same every time?** DETERMINISTIC per section kind (repeatable = stage-safe); the leader ROTATES across
  sections, so the piece varies while each kind's session is fixed. Not random — by design. (Real
  collaboration is emergent/anyone-starts; we make the "who leads" convention EXPLICIT in code, trading
  spontaneity for determinism while keeping the collaborative FEEL — the cool the audience hears is the
  cross-voice RESPONSE, not a random opener. A tiny leader-router agent could add emergence later, but
  keep it deterministic — it buys realism you can't hear and costs the guarantee.)

**Locked decisions (Sujit):** 3 passes with fast-mode 1; rotating leader by section kind; Bass/Drums stay
deterministic.

**Open for the build session:** the exact leader/follower rules per section kind (the table is a DRAFT —
nail the music); the `SectionCanvas` contract shape; whether pass 3 is always on or auto-skipped for short
sections; cost/latency tuning + a fast-mode path. **Touchpoints:** `crew/contracts.py` (SectionCanvas),
`crew/generators.py`, `crew/lead.py`, `crew/riff.py`, `crew/band.py`, and `_generate` in `crew/flow.py`.
Precedent already in the codebase: the composers' bounded dialogue over a shared transcript — this brings
the same pattern DOWN to the note-generation, but COOPERATIVE (build) rather than ADVERSARIAL (debate).

## Riff library + recurrence — song form (decided 2026-07-13; step 1 built)

**Problem.** Real metal songs have a *main riff* that RECURS (verse), a different riff or power
chords for the *chorus*, and another for the *breakdown/bridge*. The old riff engine generated a
**fresh** riff per rhythm section with only a soft prompt hint to "bring the main riff back" — so
the hook never reliably returned, and there was no first-class verse/chorus/breakdown contrast.
This is the step-9 lesson again: the Producer already *scores* `hook`/`repetition`/`structure`, but
the generator couldn't reliably *deliver* it.

**Design (the pattern: code owns the recurrence, the LLM composes each riff once).** A section names
a **`riff_slot`** — a small library of labels (`main`/`chorus`/`breakdown`). Sections that share a
slot REPLAY the same riff; distinct slots get distinct riffs. Identity lives in the slot (in code),
not in the LLM remembering to reprise. `None` falls back to the section `kind`, so same-kind sections
reuse one riff by default (recurrence out of the box). Mirrors the raga side too — a recurring riff
landing on the sam is a mukhda/refrain.

**Mechanics.** `generate_riff` writes a riff ONCE PER SLOT (via a `slot -> pattern` library) and
reuses it wherever the slot recurs; a new slot is generated seeing the *other* realized slots so it
CONTRASTS them (chorus vs main). A recurring section emits a light `reprise` INFO event (the hook
returns on the timeline) instead of a fresh `propose`. Fewer LLM calls (~3 riffs, not one/section).

**Build order.**
1. **Contract + pure placement — DONE (2026-07-13).** `Section.riff_slot` (`crew/contracts.py`);
   `generate_riff` generate-once-per-slot + reuse + reprise events (`crew/riff.py`); `RiffMemo.kind`
   -> `.slot`; `_slot_for`. Pure tests in `tests/test_riff.py` (reuse/reprise/distinct-slots/default).
   No LLM, no cost. UI unaffected (same `DebateEvent` contract; propose `data.slot` added).
2. **Metrics — DONE (2026-07-13).** `riff_recurrence` / `riff_variety` / `riff_slots` in
   `crew/metrics.py` (computed from the section->slot map; slot resolution mirrored inline so the
   module stays LLM-free), surfaced in `render_metrics` as a "riff form" block. Pure tests in
   `tests/test_metrics.py`.
3. **Composer prompt — DONE (2026-07-13).** `config/tasks.yaml` teaches Pandit/Riffsmith to
   assign a `riff_slot` per rhythm section (reuse "main" for the hook; distinct slots contrast);
   the output schema + `_render_draft` show slots (so the counterpart aligns); the composer
   guardrail (`_validate_turn`) now REJECTS a rhythm section with no slot (bounded retry, beside
   the motif-legality check). Pure tests in `tests/test_composers.py`.
4. **Producer prompt — DONE (2026-07-13).** The riff-form metrics already reach the Producer
   (step 2 added them to `render_metrics`, which `crew/producer.py` injects); this step wires them
   into the RUBRIC — the `hook`/`repetition`/`structure` anchors now reference a *returning* main
   riff, and the grounding block maps them to `riff_recurrence`/`riff_variety`. Prompt-only
   (`config/tasks.yaml`); no code/test change. (Deferred: rendering the per-slot riff *library* to
   the Producer — the test comps carry only a first-cycle riff, so it adds fixture churn for
   marginal gain; revisit if the Producer needs to judge chorus-vs-main contrast at the note level.)
5. **One live confirmation — DEFERRED (2026-07-13) to the NEXT session.** Rather than a one-off
   CLI `compose_flow`, we'll do UI improvements first so a LIVE run can be triggered and watched
   from the UI itself (`RMA_UI_LIVE=1`, the `/api/compose` path in `ui/server.py`), then use that
   run to confirm the feature end-to-end: the composers assign `main`/`chorus`/`breakdown` slots
   and reuse `main`; the Riff emits `reprise` events where a slot returns; the Producer's
   `hook`/`repetition` reasoning cites the riff-form numbers. Steps 1–4 (all offline/pure) are
   DONE and green; only this live check remains for the riff-library feature.

**Note:** default fallback (same kind -> same slot) is a deliberate BEHAVIOR CHANGE — two `RIFF`
sections now replay one riff (a hook) rather than two independently-developed figures. Composers get
contrast by assigning explicit slots or using distinct kinds (`BREAKDOWN` is already its own kind).

## NEXT CAMPAIGN — song-quality improvements (GPT feedback triage, 2026-07-14)

*Sujit shared a fresh GPT review of the prompt/architecture (chord progressions for structure,
clean electric guitars + arpeggios, better taans, more authentic raga feel). To be BUILT IN A NEW
SESSION, one reviewable step at a time. GPT reviewed a single prompt BLIND to the codebase, so much
of its list is ALREADY built — the value is the few genuinely-new levers below.*

**Already built (GPT was blind to these — do NOT re-do):** richer raga data
(aroha/avaroha/vadi/samvadi/pakad/chalan/thaat/samay), composition MEMORY, the lead's `phrase_plan`
(taan development), riff recurrence via `riff_slot`, meend realism, and the Producer as the 3rd
critic (Rasik's two jobs already split).

**Push back on (do NOT adopt as-is):**
- **"Drop the ~80% pakad/chalan rule"** — CONFLICTS with the shipped `phrase_plan` (step 9), built +
  live-validated precisely because the lead ran straight scales. The transformation vocabulary
  (sequence/invert/fragment) is the anti-formulaic mechanism; do NOT loosen the ratio.
- **"Add a SongBlueprint planner agent"** — the COMPOSERS are the arrangers (the Arrangement IS the
  blueprint); a planner agent bloats the lean roster. Kernel of truth: the energy curve isn't
  first-class — so WIRE UP the already-designed-but-unwired `SectionIntent.energy` spine instead.

**Genuinely-new levers, ranked (impact × fit × talk value):**
1. **Harmony layer with modes** (Sujit's own top question — chords for structure). A harmony
   DECISION the composers make per section: `drone` (Sa–Pa / Sa–Ma, for alaap/taan), `modal_pedal`
   (one tonic pedal + changing legal upper voicings — the raga-metal default), and a short
   `raga_compatible_progression` reserved for CHORUSES only. NEVER force Western V–I (it kills the
   raga's melodic gravity — a musical-accuracy red line and a talk point). `Note.chord` +
   `_stack_above` already give legal-by-construction voicings; what's missing is the time-varying
   plan + the mode selector. Feeds a Producer `harmony_flow` criterion.
2. **Clean electric guitar + arpeggios** (Sujit's question). No clean voice today (every guitar is
   distorted); the Dethmetal soundfont already HAS a clean preset that `route_guitars` never
   addresses (zero sample cost). Arpeggiation = a new render mode that walks a voicing into a note
   sequence; pairs with #1 (arpeggiate the active voicing; thin out under a taan). The textural
   contrast the Producer's `balance` wants but can't currently find.
3. **Best-of-N generation + rank** — the only genuinely NEW agentic PATTERN (generate 2–3 candidate
   leads/taans/riffs, rank CHEAPLY via the deterministic validator + `metrics.py`, NOT N× critic
   calls). Real quality gain, talk-friendly — but it'd be a THIRD named pattern beside the critique
   loop + the collaboration; decide deliberately (pattern-overload vs. escalating sophistication).
4. **More ornaments — `andolan` first.** Data is ALREADY encoded per-raga; there is NO andolan
   renderer, so the model is told to oscillate notes it can't. Highest authenticity-per-effort, and
   Rasik's standing ask. Gesture = a slow, shallow pitch oscillation on the flagged komal swaras.
   Then gamak/murki/khatka. (GPT is right: ornaments-as-gestures beat adding more notes.)
5. **Tala position to the LEAD + taan taxonomy** (a real gap GPT caught). The riff gets tala / cycle
   / accents; the lead gets NONE, yet its prompt says "land on the sam" without saying where the sam
   is. Hand the lead cycle_beats + sam offset within the section + beats-to-next-sam. Then a
   taan-type taxonomy (sargam/aakar/gamak/vakra/tihai) + sitar↔guitar call-and-response.
6. **Richer raga fields** — add `nyas_swaras`, a real `rasa` (Rasik conflates it with `samay`
   today), and weak/forbidden movements; feed them to Rasik as grounding (aligns with the adopted
   "precompute facts for Rasik to JUDGE, not measure").
7. **Riff variants** (A / A_prime / halftime / stripped / octave_double) — a CODE transform of a base
   slot's pattern; extends the `riff_slot` recurrence so the identity survives while the figure
   evolves.

**Recommended first step (Sujit confirms in the new session):** #1 harmony modes + #2 clean guitar as
one campaign — it directly answers the chord-progression question and is the biggest structural lever;
scope it carefully (source-check the raga-compatible progressions). Cheaper/safer alternative: #4
andolan + #5 tala-aware taans (highest authenticity per unit effort).

## GAT-LED SONG CAMPAIGN (Sujit's direction + a 2nd GPT review, 2026-07-14) — IN PROGRESS

*Sujit listened to `out/fusion.mid` (~4:32) and heard the real problem: it is a **riff loop with a
sitar floating on top**, not a **gat-led composition**. He wants the sitar GAT to be the source —
`mukhada → manjha → antara` with the mukhada as a returning hook — plus short taans as fillers, one
long taan/solo for the peak, richer riff/taan rhythm, and layers that build. A second GPT review
agreed and proposed: make the gat the source, a shared `anchor` (gat_first default; riff_first
supported), a **riff family** (A/A′/stripped/double), separate short-filler vs long-development
taans, and layer-by-function. This supersedes the ranked list above as the active plan.*

**Which critic judges what (settled this session — do NOT blur it):** the "sitar isn't faithful /
gat isn't authentic" complaint is **Rasik's** axis (raga authenticity + idiom), and "does the gat
work as a song" is the **Producer's** (structure/hook/arc). Ustad must NOT become a taste critic on
the gat/taans — that would collapse the three orthogonal critics (its whole signature is owning NO
aesthetic verdict). The one principled way Ustad may grow: extend *legality* from raga-grammar
(pitch) to **tala-grammar (time)** — taan lands on sam, mukhada resolves to sam, cycle complete —
all checkable facts, code-owned. Talk point: **legality has two grammars, pitch and time.**

**Build order (one reviewable step each; the working agreement):**
1. **Gat form spine + anchor — ✅ DONE (this session).** Added `FormRole` (intro/mukhada/manjha/
   antara/taan_short/taan_long/breakdown/tihai/outro) as a closed `Literal`, an **orthogonal**
   `Section.form_role` (kind = how to render; form_role = its place in the gat), and a first-class
   `anchor = gat_first | riff_first` on the draft, carried onto the `Arrangement`. `form_role` is
   `Optional` in the schema but **required by the composer guardrail** (the same optional-in-schema /
   required-in-guardrail split as `riff_slot`, so the ~50 unrelated fixtures didn't churn). The
   guardrail now enforces the gat STRUCTURE — every section has a form_role, a **mukhada is stated
   AND returns** (≥2), at most one `taan_long` — while the melodic realisation (what the mukhada IS,
   how the riff reduces from it) stays the composers' creative call. The pattern: **"code decides the
   checkable, the LLM decides the rest" applied to song FORM, not note legality.** Prompt teaches the
   gat arc + anchor. Pure tests green (composers 18/18; full suite 21 files green). Live composer
   confirmation still pending.
2. **Riff family — ✅ DONE (this session).** `crew/riff_family.py` (pure): four transforms of a
   slot's base cycle — `base` (A), `prime` (A′: same pitches, palm-mut chug + slide turnaround),
   `stripped` (half the attacks, sustained — room under a taan), `double` (octave power chord on
   every note — the climactic hit) — all **legal by construction** (each reuses the base's own
   swaras, or adds a note's OWN swara for the octave), so no new guardrail. `variant_for_bar` is
   the CODE policy: no form_role → `base` (a form-less demo/fixture is placed literally, so the
   whole existing suite stayed green); a taan section → `stripped`; the final rhythm section's last
   bar → `double`; every 3rd bar of a section ≥3 bars → `prime` (no >2 identical cycles). Wired via
   `rhythm_layer_from` → `develop_section` (placement factored into a per-bar `_place_cycles`
   primitive; `place_riff` kept as the literal-repeat wrapper). The talk lesson extends step 1's
   "code owns the recurrence" to "code owns the VARIATION too." Pure tests: `test_riff_family.py`
   (14) + full suite 22 files green. Cross-recurrence priming (a returning section differing from
   its first statement) is a noted easy extension; today variety comes from within-section
   development + the climactic final double + distinct slots.
3. **Energy + layer-by-function — ✅ DONE (this session).** `crew/dynamics.py` (pure):
   `apply_dynamics` is a post-assembly MIX pass, run as the last step of `band_layers` (the single
   assembly chokepoint for BOTH the parallel and studio paths, confirmed via `flow._assemble`).
   Two jobs, per section, driven by step 1's `form_role`: (1) an ENERGY ARC — each section's energy
   (`_ENERGY` table: intro/outro low, mukhada/manjha mid, antara high, `taan_long` = 1.0 peak, final
   non-outro floored to 0.85 so it lands strong — pairs with the riff `double`) scales velocity so
   the piece BUILDS; (2) LAYER-BY-FUNCTION — the section's `foreground` sits at gain 1.0 and the
   rest make room, with the **mix fix**: the rhythm guitar ducks to 0.55 under a lead-foreground
   section so the sitar cuts through. The drone is EXEMPT (a constant anchor spanning the whole
   piece). Gated on `form_role` (a form-less chart is untouched → the whole suite stayed green).
   Scales both `Note.vel` and `DrumHit.vel`. Pure tests: `test_dynamics.py` (10) + full suite 23
   files green. **Not yet built here:** drum-DENSITY-by-energy (velocity build only for now),
   dropping the double-track entirely under a lead section (velocity duck only), and reading
   `SectionIntent.energy` as an override on the studio path (form_role-derived energy is the
   universal spine; the override is an easy add). Constants (`_DUCK_RHYTHM_UNDER_LEAD`, the energy
   table) are tuning knobs to revisit after a live render.
4. **Taan taxonomy + tala-aware lead — ✅ DONE (this session).** The lead was TALA-BLIND (told to
   "resolve on the sam" with no idea where the sam was — GPT's catch). Now `_LeadContext` feeds it
   the tala + `_render_tala_position` (cycle_beats, the sam offsets inside its window, and that the
   phrase ends on the closing sam — sections are cycle-aligned, so start and end are sams), plus the
   section's `form_role`. The `generate_lead` prompt gains a "TALA POSITION — LAND ON THE SAM" block,
   a "SHAPE IT TO ITS GAT ROLE" block (mukhada = state/return the hook resolving to sam; manjha =
   develop in madhya; antara = lift to taar; **taan_short** = a ~1-cycle cadential filler resolving
   into the next mukhada; **taan_long** = the developed peak, space→16th burst→resolve), and a "FAST
   RUNS ARE SIXTEENTHS, EARNED" rule (dur 0.25, pickup→burst→held, not every beat). Pure — the lead
   loop tests unchanged (43/43), full suite 23 files green. **Not done here (noted):** no CODE
   enforcement that a resolving note lands exactly on the sam (informed prompt only — snapping
   durations would distort the phrase); voicing is still by `kind`, not `form_role` (a taan_short
   as a solo-sitar flourish vs. a harmonized third is a possible refinement).
4b. **Riff richness — ✅ DONE (this session; Sujit chose `strict_raga`).** Shipped: (a) fixed the
   `["P"]`-is-a-fifth MISLABELLING everywhere (contract `RiffNote`, `generate_riff` prompt, `render.py`
   comments + `_stack_above` docstring) — a chord tone is now described as "a raga swara stacked at
   the lowest octave above the root; add the note's OWN swara for a root+octave power chord; `["P"]`
   is Pa, a true fifth only above Sa"; STRICT_RAGA kept (no out-of-raga fifth). (b) A **`rest`** flag
   on `RiffNote` — a silent beat that occupies its `dur` but is never placed (so NO renderer change),
   letting a riff leave SPACE; `_sequence_cycle` skips rests and does not stretch a note over a
   trailing rest (silence into the sam); the guardrail exempts rests; the family transforms guard
   them (`double`/`prime` skip rests). (c) `generate_riff` now receives `form_role` and gains a
   SHAPE-IT-TO-ITS-GAT-ROLE block (mukhada = low-string hook + space; antara = open/wider; breakdown
   = sparse tihai hits; taan = thin out), a RHYTHM block (primary + contrast cell — gallop / 16th-chug
   / 3-3-2 / rest-stab — ≥1 rest per cycle, a turnaround to the sam), and a TECHNIQUE BUDGET (chugs =
   core, ~1 slide/cycle, 1–2 hammer-ons, bends at cadences only). Pure tests: `test_riff` (34,
   +rests), `test_riff_family` (16, +rest guards); full suite 23 files green. **Deferred:** the
   generator still writes ONE cycle (step 2's placement-side family provides the A/A′/turnaround
   development — a generator-side multi-cycle phrase was judged redundant with it); no scoped
   `power_chord_priority` (Sujit chose strict_raga).
   ---
   *Original triage (kept for context):* Sujit: current riffs are too simple/repetitive; wants power chords,
   sliding power chords, Megadeth-style hammer-ons, palm-muted low-string chugging, gallop, occasional
   bends, interesting RHYTHM, and DISTINCT riffs/chords for chorus vs bridge. Much of the *mechanism*
   exists (the schema already carries `chord`+`technique`; step 2 gives A/A′/stripped/double; distinct
   `riff_slot`s already contrast chorus/breakdown) — the gaps are (a) the GENERATOR still writes ONE
   cycle (GPT: have it write a **2–4 cycle phrase** with A/A′/turnaround-to-sam built in, complementing
   step 2's placement-side variation), (b) no **technique budget** (chugs = core texture; ~1 slide per
   phrase; 1–2 hammer-ons; bends only at cadences; ≥1 intentional rest per cycle — so it doesn't
   randomly decorate), (c) no **rhythm-cell** vocabulary (primary + contrast: gallop / 16th-chug+rest /
   3-3-2 / slide→sustain / hammer→chug / half-time hits), and (d) **section-role articulation** (verse/
   mukhada = low-string hook with space for the gat; chorus = wider OPEN power chords, less palm-mute,
   higher register; bridge = deliberately different feel — half-time/syncopated/technical; breakdown =
   simplified tihai-cell hits; final = the hook in its biggest form). Mostly prompt work on
   `generate_riff` + a small rhythm-cell/technique-budget scaffold; the section-role articulation keys
   off `form_role` (step 1) like the lead now does. **⚠ DESIGN FORK for Sujit (musical-accuracy
   non-negotiable):** GPT correctly points out **`["P"]` is NOT "a fifth" above every root** — it is
   only Pa (the fifth of the tonic Sa); our contract/prompt currently MISLABEL `["P"]` as "a fifth"
   and `["S"]` as "root+octave" (true only when the root is Sa). A real metal power chord is an
   INTERVAL (root + perfect-fifth + octave), not a raga scale degree. GPT proposes representing power
   chords as VOICINGS (`power5`) the renderer builds by interval, plus a `harmony_policy`:
   **`strict_raga`** (all sounding tones stay in the raga — our current hard line, Ustad-legal) vs.
   **`power_chord_priority`** (allow the neutral perfect fifth as a non-melodic distorted-guitar
   voicing even when out-of-raga, keeping roots + all melodic material raga-correct). `power_chord_priority`
   **breaks our raga-legality guardrail** (Ustad would flag the out-of-raga fifth) — so it is a genuine
   musical-philosophy decision, NOT to be adopted silently: is a power chord's fifth a *melodic* tone
   subject to raga law, or a *timbral* thickening exempt from it? Default recommendation: keep
   `strict_raga` (fix the MISLABELLING regardless — describe `chord` as "raga swaras stacked above the
   root", not "a fifth"), and only consider a scoped `power_chord_priority` (fifth-only, guitar-only,
   Ustad taught to treat it as a voicing) if Sujit wants the authentic metal fifth. Overlaps with step 2
   (extend the family), step 5 (bols/rhythm cells), and the harmony-modes lever from the earlier triage.
5. **Sitar bols / mizrab-bol phrasing (NEW — Sujit + GPT, 2026-07-14).** Make the gat sound
   *composed*, not MIDI-over-a-loop, by generating rhythm as **mizrab bols** (Da/Ra/Dir/Dra, chikari
   strikes, rests) with MIXED subdivisions (single/pair/four-stroke-16ths/explicit triplet) and a
   **recurring bol identity for the mukhada** that returns at each reprise (bol-bant/displacement for
   manjha/antara). Key distinction GPT flagged: **bols ≠ subdivision** (DaRaDa is three strokes, a
   triplet only when placed in triplet timing) — keep them separate. **Design decision to make when
   we build it:** our generators are duration-only ("LLM aims durations, code lays them on the grid")
   — durations ALREADY encode subdivision (0.5+0.5 = DaRa, 0.25×4 = DaRaDaRa, 1/3s = triplet), so we
   likely add a **`bol` + articulation layer on the note** (driving attack/velocity/timbre + a
   distinct chikari sound in the renderer) rather than GPT's full explicit-onset-grid rewrite —
   preserving the timing invariant. **Musical-accuracy gate:** the bol/baaj vocabulary must be
   source-verified (≥2 reliable Hindustani sources; GPT cited Pandit Arvind Parikh + a sitar-baaj
   study — verify before encoding). Renderer must make bols audibly distinct or the notation change
   won't be heard. This also feeds the riff-as-rhythmic-reduction anchor (the riff locks to the gat's
   bol rhythm).
6. **Gayaki ang — Imdadkhani / Vilayat Khan / Shahid Parvez (NEW — Sujit, 2026-07-14).** The sitar
   should SING (khayal-vocal style): long connected meend, sustained legato, andolan on komal/nyas
   swaras, vakra dwelling phrasing, kan/murki/khatka. Maps to: **Rasik** gayaki-idiom criteria (the
   authenticity judgment), **lead-generator** style so it can ACT on the critique, an
   **articulation-aware sustain fix** (see below), and finally an **andolan renderer** (data encoded,
   no gesture — DESIGN.md lever #4). **Source-verify** the gharana idiom before encoding as data.
7. *(optional)* **Ustad gains tala/time legality** — the pitch+time-grammar talk point above.

**Audio observations (deterministic render fixes — no agent hears audio, so critics can't catch
these; the "audio production is code" insight):**
- **Sitar sustain/decay** — a plucked sitar sample decays on long holds; the distortion guitar
  sustains far longer, so held sitar notes go weak. Fix is **articulation-aware**: fast gat/jhala
  passages re-articulate (re-pluck, as a real sitarist sustains), but gayaki meend lines must stay
  sustained (expression swell / layer, NOT re-plucked — re-plucking would destroy the vocal legato).
  Pairs with steps 5–6.
- **Rhythm guitar buries the lead** — two hard-panned full-gain tracks sum to a wall; folded into
  step 3 (foreground-dominates).
