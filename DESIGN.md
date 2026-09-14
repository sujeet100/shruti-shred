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
5. **Sitar bols / mizrab-bol phrasing — ✅ DONE (this session).** A `Bol` closed set on `LeadNote`
   (`da`/`ra`/`diri`/`darada`/`chikari`) + `crew/lead.py apply_strokes` realises each stroke as
   sitar ARTICULATION before placement (PURE, no renderer or `Note`-contract change — our GM sitar
   can't do true stroke timbre, so velocity is the honest lever): `da` strong, `ra` softer, `diri`
   a da+ra DOUBLE-stroke (note split in 2), `darada` a da+ra+da TRIPLE-stroke (split in 3, for
   triplets), `chikari` a bright high-Sa drone-string accent (its melodic swara IGNORED → taar Sa;
   the guardrail skips it). Splits preserve total duration (timing intact) and re-articulate (which
   also fights the sitar decay). `generate_lead` gains a MIZRAB BOLS block: bol ≠ subdivision, the
   MUKHADA carries a recurring bol IDENTITY that returns with it, manjha/antara vary by bol-bant.
   `_local_token` now shows bols in the lead's memory so a return can restate the same pattern.
   Pure tests: `test_lead` (50, +bols); full suite 23 files green.
   **Sources (verification tier — the musical-accuracy rule):** VERIFIED to ≥2 reliable Hindustani
   sources — da, ra, diri, chikari, and "a bol is a STROKE not a subdivision" — via Pandit Arvind
   Parikh *Bandish on the Instruments* (panditarvindparikh.org / nadsadhna.com), omenad.net, India
   Instruments (india-instruments.com), kksongs.org, corroborated by chandrakantha.com (David
   Courtney). **`darada`** (da-ra-da, a triplet) — the syllable is attested single-published-source
   (Parikh) and CONFIRMED by Sujit as a practitioner; encoded on that basis, tier flagged here.
   NOT encoded (couldn't reach ≥2 sources): `dra` and the other Parikh compounds' mechanics, a
   distinct "sustain/rest" bol (handled structurally via `rest`), the 14th-matra Vilayat Khan start.
   **Deferred:** the masitkhani/razakhani fixed thekas (style, not a fixed pattern — GPT + omenad
   agree); gayaki density is step 6. *(Original triage note follows.)*
   Make the gat sound
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

### ★ GAT OVERHAUL — the NEXT-SESSION campaign (diagnosed 2026-07-14 from a LIVE run)

*Steps 1–5 + 4b are committed (`bf359da`, `4a2d21b`) and green, but the first full LIVE render
(`out/fusion.wav`/`.mid`, trace `f20b9d65ddcb`) revealed the fixes touched the PERIPHERY and missed
the HEART of the gat. Sujit's critique + a second GPT review CONVERGE. This subcampaign is the fix.
Everything below is from the actual trace — start here, no re-analysis needed.*

**The run:** Bhairavi × doom, jhaptaal (10 matras, 2+3+2+3), 70 bpm, anchor gat_first, motif
`g m P d m g m r S` (= the encoded Bhairavi pakad ✓). Form the composer produced: intro(20) →
mukhada(40) → manjha(40) → antara(40) → taan_long(20) → breakdown(30) → mukhada(40) → outro(20)
matras. The high-level ARRANGEMENT was correct; the failure is in how the gat is REPRESENTED.

**Root diagnosis (trace-confirmed, Sujit + GPT agree):**
1. **THE core bug — the mukhada is a 40-matra through-composed phrase, not a looping ~10-matra
   cell.** The lead composes ONE continuous phrase spanning the whole 4-avartan window, so there is
   no recognizable, repeatable HOOK and no clear begin/end. A gat mukhada must be ~1 avartan
   (10 matras) that RESOLVES to sam and REPEATS. (The riff already does this; the gat must too.)
2. **`LeadNote` has NO `rest` field** (a real design bug — `RiffNote` got one in 4b, the lead did
   not). Asked for space/nyas, the lead can only lengthen notes → "pauses after every 1–2 notes" and
   no true nyas rests.
3. **The mukhada RETURN is regenerated from text memory, not CACHED** — the riff-slot cache reuses
   its cell verbatim; the lead doesn't, so the "return" needn't match the head. (Leads #1 and #5 both
   START `g m P d m g m r S` but diverge.)
4. **Rhythmically flat GAT:** the mukhada/manjha are ~all even quarter notes (lead #1: 27 of 38 notes
   dur 1.0, almost all single da/ra, ~2 diri) → bland. The TAAN, by contrast, DID use the new work
   (32 sixteenths, 19 eighths, 28 diri) — so bols/subdivision work; the gat just doesn't use them.
5. **Vadi/nyas ignored:** vadi `m`, samvadi `S` are passed THROUGH, never dwelt on or cadenced to;
   no sam landing each avartan. Legality ≠ raga identity — nothing enforces nyas / pakad-at-mukhada /
   sam resolution / gat-head-vs-manjha-vs-antara distinction.
6. **No andolan** on Bhairavi's komal `r`/`g`/`d` (no renderer) — the single biggest "doesn't feel
   like Bhairavi" factor after the flat delivery.
7. **`doom` default** reinforces "sparse/heavy whole notes" downstream; the brief was a vague mood.

**CORRECTIONS to the raw reading (do not chase these):** the jhaptaal 10-beat loop + 70 bpm are
INTENTIONAL and fine — NOT a cause. And `fusion.mid` uses external Bank Selects (Indian Ensemble
bank 50, Dethmetal bank 126); in a GENERIC MIDI player those fall back to PIANO and the meend shows
as thousands of pitch-bends — so judge `fusion.WAV` (FluidSynth + soundfonts), not the raw `.mid`.
**OPEN QUESTION to confirm first next session:** did Sujit hear the `.wav` or the `.mid`? If the
`.mid` in a generic player, re-weight the timbre/andolan fixes (composition faults 1–5 hold either way).

**The fix plan (prioritised; 1+2 first — the difference between a melody-in-a-block and a gat hook):**
1. **Mukhada as a cached, looping ~1-avartan cell** — the lead composes EXACTLY one cycle for a
   `mukhada` section (pass window = beats_per_bar, not span.length); code LOOPS it across the
   section's bars with a small final-cycle variation, and CACHES the cell to reuse verbatim for the
   mukhada return (mirror the riff-slot cache / step-2 family). Prompt: a memorable 10-matra head
   that resolves to sam.
2. **`rest: bool` on `LeadNote`** (+ `place_phrase` skips it, like the riff) + nyas rules in
   `generate_lead`: sam landing on matra 1 (strong `S` or `m→S`), sustain/rest on `m`/`S`/`P`, 1–2
   intentional rests per avartan, stop the per-note pausing.
3. **Andolan renderer** on the raga's `andolan` swaras (data already encoded; no gesture yet) — a
   slow shallow pitch oscillation on flagged komal notes. Rasik's standing ask; highest
   authenticity-per-effort for Bhairavi.
4. **Rendered-score verifier + repair pass** (GPT #4; = the "Ustad gains tala/TIME legality" idea):
   assert each avartan lands the sam, mukhada cycles are self-similar, the final mukhada matches the
   head, accents follow 2+3+2+3, and ONLY the taan carries sustained 16ths — then REGENERATE a weak
   hook (the critics run too late today; there is no repair for a bad mukhada).
5. **Operational brief** (GPT #5): steer the composers to concrete rhythm (e.g. double-time kit under
   the 70-bpm doom pulse, 8th-note chugs, one 16th turnaround per avartan, lead gat = a 10-matra
   mukhada with nyas on Ma/Sa) instead of a vague mood; consider defaulting/encouraging progressive
   over doom when the user wants rhythmic life.

**Deferred (still queued from before):** gayaki-ang density/meend/sustain (step 6 orig) folds into
2+3; the sitar-decay articulation-aware fix; Ustad pitch+time-legality talk point (now = fix #4).

#### GAT OVERHAUL build log (2026-07-14, this session — pure tests green, live render pending)

**Fixes 1+2 (mukhada cache/loop + rest) — DONE.** The core gat bug: the lead composed ONE
through-composed phrase across the whole mukhada window (no repeatable hook) and REGENERATED the
return (which drifted). Now `generate_lead` writes a `mukhada` as EXACTLY ONE avartan
(`_one_cycle_span` coerces bars→1), CACHES the cell, and REUSES it verbatim on every return (a
reprise event, no second LLM call); `_place_lead_section` LOOPS the cell across the section's bars.
This is the riff-slot cache pattern applied to the gat — *code owns the recurrence, the LLM composes
one cell*. `LeadNote.rest` added (skipped in placement, ignored by the guardrail/strokes) + a
NYAS/SPACE prompt block. Sujit's calls: the mukhada loops IDENTICALLY (a returning head, not a
developing phrase); and a LOOP-SEAM rule went into BOTH the lead and riff prompts — the last
note/chord must resolve into the first so the cycle *lands* on the sam rather than restarting.

**Fix 3 (andolan) — DONE.** The slow, shallow pitch SWAY that defines a komal note in some ragas.
`Note.andolan` flag → renderer `_andolan_wheel` (a slow sine on the pitch wheel, ~2.4 Hz, 0.4 st,
fitted to WHOLE cycles so it starts/ends at 0 — no bleed; `_bends` arms the range). Code sets the
flag in `_placed_note` on the raga's own `andolan` swaras, on HELD notes only, mutually exclusive
with a meend on the same note. Data-driven: fires for Darbari (g,d) and Bhairav (r,d); the
`andolan: []` ragas get nothing. The pattern: *andolan is a raga FACT — data + deterministic code,
never the LLM (it can't hear audio); the renderer stays raga-agnostic and just draws the flag.*

#### Murki/khatka — the CONTRASTING ornament (source-verified 2026-07-14) — DONE

Diagnosis #6 said "andolan on Bhairavi," but the source-verified data says Bhairavi's andolan is `[]`
— it leans on **murki/khatka**, a different gesture. Flagged the discrepancy, trusted the data,
verified murki/khatka against ≥2 Hindustani sources (Tanarang, chandrakantha/David Courtney,
raag-hindustani, ITC-SRA via Wikipedia; no Carnatic source relied on):

- **Murki** = a light, delicate, fast neighbour-cluster wrapping a note (a turn/trill). **Khatka** =
  the same shape but SHARPER and HEAVIER, distinct surrounding notes, no slide.
- **Key finding (high confidence):** the murki↔khatka distinction is **WEIGHT/ACCENT, not the notes**
  — the same cluster is a murki, khatka, or zamzama by how forcefully it's delivered. A notes-only
  distinction is explicitly *not* supported, so we encode ONE shape and differ by velocity/duration.
- **Per-raga (of our five):** ONLY **Bhairavi** uses them, on the komal g / komal r descent (`m g r S`).
  Darbari/Bhairav/Malkauns use andolan; Bhimpalasi uses meend + kan. Flags carried forward: the
  khatka slide-vs-no-slide split is real (we take the discrete/no-slide reading for MIDI); the exact
  Bhairavi `m g r S` example was single-source (illustrative, not canonical).

**Encoding — the counterpoint to andolan.** Andolan is a raga FACT code applies; murki/khatka are an
expressive CHOICE the LLM places (like `bol`/`grace`). `LeadNote.ornament` (`murki`|`khatka`) is
LLM-set; `apply_ornaments` (pure, runs before `apply_strokes`) realises the cluster from the raga's
OWN scale neighbours (`scale_step_up` ±1 → legal by construction: upper + lower neighbour crushed,
then the main note sustains), a khatka louder + eating more of the note than a murki. A new raga fact
`ornaments` GATES it — a raga that doesn't list them (all but Bhairavi) has the flag stripped and
plays plain, so a light Bhairavi flick can't leak into grave Darbari. *Talk beat: two ornaments, two
ownership models — andolan a fact code owns, murki/khatka a choice the LLM makes and code keeps legal.*

#### Fix 4 — the gat verifier + TARGETED repair (2026-07-14) — DONE

The talk point made real: **legality has two grammars — pitch AND time.** `validate_composition`
owns pitch legality; `crew/gat_verifier.py` (pure) is the TIME counterpart for the mukhada head —
three checkable structural invariants the pitch guardrail can't see: it FILLS ~one avartan (loops as
a cycle, not a fragment), it CADENCES to a resting swara (Sa/vadi/samvadi → lands on the sam and
loops), and it is NOT rhythmically flat (the diagnosed failure — a gat of even quarters). Scope
discipline held: it checks structure (checkable), never gat/taan taste (that stays Rasik/Producer).

Why it matters: the aesthetic critics run LATE (after the whole piece assembles), so today a weak
hook poisons everything and nothing repairs it. This runs EARLY — right after the head is generated,
before it's cached and looped — so `generate_lead._generate_mukhada_cell` can RE-ROLL a weak hook
(bounded, best-of-N). **Repair strategy (Sujit's call): a TARGETED feedback re-roll, NOT code note-
surgery** — the exact violations are fed back into the regeneration (`_render_repair` → the `{repair}`
prompt block) so the LLM re-composes the head to fix precisely what failed. Code decides WHAT is
wrong (deterministic verify); the LLM fixes it (composition). We explicitly rejected having code
edit the notes (pad-to-avartan / append-Sa / mechanical un-flatten) — that would cross the "code
never composes" line; keeping repair as an LLM re-roll keeps every pitch/rhythm decision with the
composer. Talk beat: the verify/repair split is the critique loop in miniature, one voice, early and
local. Pure tests: `tests/test_gat_verifier.py`, repair loop in `tests/test_lead.py`.

**Still to do this campaign:** fix #5 (operational brief — steer the composers to concrete rhythm
instead of a vague mood); then ONE batched full-band live render to hear the looping mukhada + rests
+ andolan + murki + the gat verify/repair in context.

---

## ★ GAT DEVELOPMENT — the NEXT-SESSION campaign (feedback 2026-07-15, NOT yet built)

*Fix #5 + the menu expansion shipped (`e67270f`). Sujit then heard a full live render (`out/fusion.wav`)
and gave detailed feedback; a second Gemini review INDEPENDENTLY converged on the same points and cracked
the one weakness Sujit couldn't pinpoint. This section captures the whole plan so a new session starts
cold. **Nothing here is built yet.** Build order: A (intro) → B (riff dissonance) → C (manjha) → D (taans).*

**WINS to preserve:** "way better", "the gat structure came out well", "the mukhada being repeated
sounds TOO GOOD" → the mukhada cache/loop (fixes 1+2) is VALIDATED. Do not regress it.

**Root theme (Sujit + Gemini agree):** the manjha and the intro have the SAME gap the mukhada had before
the overhaul — no definition, no resolution to the sam. And (Gemini's framing) LLMs can't invent silence
or cyclical tension from "be spacious / develop the head"; they need feel translated into RIGID, CHECKABLE
constraints — which is exactly our verify + feedback-re-roll pattern (extend it, don't re-prompt vaguely).

**A. Intro / alap — random, never resolves to Sa, no space.** (self-contained Lead fix)
  - Requirements: RESOLVE to a held Sa; play Sa OFTEN (Gemini: Sa ≥ ~30% of the alap BY DURATION); real
    RESTS (Gemini: force ≥2 rests of 2–4 beats) with a rest AFTER landing on Sa; and a LONG pause between
    the alap's last Sa and the mukhada.
  - Design (was half-drafted, then reverted): a `verify_intro(cell)` in `crew/gat_verifier.py` — resolves-
    to-Sa + Sa-duration-share ≥ 0.30 + ≥2 true rests — fed through the SAME bounded feedback re-roll as the
    mukhada (generalise `_generate_mukhada_cell` → `_generate_verified_cell(gen_span, arr, memory, gen_fn,
    verify)`; mukhada and intro both call it). Trigger on `form_role == "intro"` (add `is_intro`).
  - The LONG pause is CODE, not the LLM: rests render as silence and there are NO cross-block ties (see
    "rendering facts" below), so the pause must live INSIDE the intro window. Reserve a trailing gap —
    generate the alap for a SHORTENED window (`end = span.end − gap`, gap ≈ min(cycle, span·0.35)) and
    `_place_lead_section` leaves that tail silent before the mukhada. Prompt: alap Sa-anchored, rest after Sa.

**B. Riff sounds muddy — THE insight Gemini cracked (highest audible impact; affects EVERY render).**
  - Root cause: our STRICT-RAGA chord rule stacks raga swaras (`_stack_above`), so a "power chord" built on
    a root whose stacked tone is a TRITONE/dim-5th (e.g. on Yaman's tivra Ma, or Ni) is consonant-enough on
    a clean sitar but turns to MUD under high-gain distortion. The new tritone-heavy ragas (Yaman,
    Puriya Dhanashree — both tivra Ma) make it worse.
  - Fix (code-checkable — interval math, so CODE owns it): only allow a stacked power-chord interval when it
    is CONSONANT under distortion — the OCTAVE (root + its own swara, always safe) or a TRUE perfect fifth
    (7 semitones, i.e. Sa→Pa). For any other stack, compute the root→tone interval; if it's dissonant
    (tritone 6, minor-2nd 1, etc.), DROP the stack to a single-note chug (or substitute the octave). Guard
    in the riff voicing / renderer `_stack_above` path. Plus a prompt rule ("power-chord only Sa and Pa;
    elsewhere single-note chugs; never stack a tritone"). NOTE this REVISITS the earlier `strict_raga`
    decision — legality kept the chord IN the raga but ignored metal consonance; reconcile with Sujit.

**C. Manjha is not a manjha — same "no definition / no return" gap.** (structural heart)
  - It's complementary to the mukhada: mukhada ×3–4 → manjha comes to the sam → mukhada again = a cohesive
    CYCLE. Its LAST note must connect FLUIDLY into the mukhada's FIRST note (Gemini: end on a lead-in like
    Ni/Ga that pulls to the mukhada's first swara; the final ~2 beats match the mukhada's rhythmic subdivision).
  - Design: the manjha is generated KNOWING the cached mukhada cell (esp. its first note) — CROSS-CELL
    awareness (thread the mukhada cell into the manjha's prompt context). Extend the gat verifier with a
    `verify_manjha(cell, mukhada)` seam check (resolves toward the mukhada's opening; lands on/approaches sam)
    → the same feedback re-roll. This is the mukhada cache extended cell-to-cell.

**D. No short fast (1/16) taans while the mukhada plays; taans don't resolve back cleanly.** (builds on C)
  - Technique: cut a few matras OUT of a mukhada statement, play a short 16th-note taan there, then resolve
    cleanly BACK into the mukhada (same fluid-seam rule as the manjha).
  - Options (Gemini): (1) a new `form_role = "mukhada_with_fills"` — "half an avartan of the mukhada head,
    then a 1/16 taan for the remaining matras, resolving onto the next sam"; OR (2) CODE splices a short
    taan into gaps of the cached mukhada cell. Reuses C's return-to-mukhada mechanism. `taan_short` already
    exists as a form_role but currently neither fires during the mukhada nor resolves back — fold this in.

**Rendering facts (answer to Gemini's question — anchor the above in reality):** a `rest` note is skipped
at placement (`place_phrase` advances time, sounds nothing) = TRUE silence; there are NO tied durations
across blocks; sections are independent windows laid end-to-end on ONE timeline, TRUNCATED at the boundary
(a transition is pure adjacency, no crossfade/tie). Consequence: any inter-section pause must be reserved
INSIDE a section's window (why A's long pause is code inside the intro).

**Also captured:** a TOOLING win — save the `Composition` JSON beside the WAV on live runs, so the riff/
manjha/intro can be diagnosed SYMBOLICALLY for free next time (this session had only the `.mid`, no symbolic
data, so the riff couldn't be inspected directly — Gemini diagnosed it from the PROMPTS instead).

**Git state at handoff:** committed — `2244132` (GAT overhaul), `e67270f` (menu expansion + pakad-to-riff +
groove_brief). UNCOMMITTED but COMPLETE + green — the live-UI `RUNNING`/placeholder fix (`contracts.py`,
`crew/flow.py`, `ui/app.html`, `UI_CONTRACT.md`), pending Sujit's live eyeball before commit.

---

## GAT DEVELOPMENT — BUILT (2026-07-15, this session)

*The A→D campaign above is IMPLEMENTED (all pure tests green — 448 across 24 files). The symbolic
analysis of `out/fusion.mid` (finally possible — and now automated: every render saves the
Composition JSON beside the WAV) CONFIRMED Sujit's structural feedback and OVERTURNED the riff
hypothesis. Build log + the evidence, so the next session knows what changed and WHY.*

**The riff finding (talk-gold — evidence beat a converging review):** both Sujit's instinct and
Gemini's review blamed TRITONE CHORD STACKS for the muddy riff. The MIDI disproved it: the 118
chord stacks were 110 octaves + 8 true fifths — ZERO dissonant stacks. The real causes, measured:
  1. **Register:** 62% of riff onsets had roots BELOW D2 — down to D1 (36.7 Hz, an octave under a
     real metal guitar). `voice_registers` floored the REGISTER at -2, but the riff LLM's local
     `oct:-1` sank notes past it. Fix: clamp each note's ABSOLUTE octave at `RHYTHM_FLOOR` in
     `_sequence_cycle` (riff.py) — "a guitarist out of frets plays the open string".
  2. **Bass collision:** at the old floor the bass (riff−1, floored −3) landed IN THE SAME OCTAVE
     as the riff (both 26–42) — unison mud, not an octave under. The clamp fixes both at once.
  3. **CLIPPING:** the WAV peaked at 0 dBFS (0.06% of samples pinned) — gain 1.2 with no limiter.
     That harsh digital noise IS a big part of "the tone sounds like noise". Fix: `_GAIN = 0.5`
     (calibrated on that same MIDI: 0.6 → −0.3 dBFS, 0.8 → clips again).
  4. **Dry raw samples:** no reverb sends — Dethmetal played bone-dry. Fix: per-role CC91 sends
     (`_REVERB_SEND` in render.py: lead 68 / drone 48 / tabla 52 / drums 38 / rhythm 30 / bass 12)
     + a modest FluidSynth room (room-size 0.55, damp 0.35, level 0.7).
  5. **Mono-ish double-track:** Dethmetal routes BOTH rhythm sides to the SAME patch (the GM
     overdrive/distortion split vanishes) — fix: `detune_cents=8` on the right take (RPN fine-tune)
     on top of the Haas offset.

**Chord voicing (Sujit's ask, kept even though tritone stacks weren't the culprit):**
`_stack_above` → `_seat_chord_tone` (render.py): a chord tone seats at a distortion-consonant
interval — own swara = octave (power chord), P/fourth keep their seats (the fourth = the INVERTED
power chord Sujit asked for), a second lifts to an ADD9, a third to a TENTH (colour above the
octave — the Yaman brightness without low-register grind); semitone/tritone/sixths/sevenths have
NO seat and degrade to octave weight. Riff prompt now teaches the vocabulary (["R"] = add9 etc.).

**Cross-voice consonance (Sujit, mid-session):** `harmonize_riff_to_lead` (generators.py) — where
a rhythm note overlaps a SUSTAINED (≥1 beat) lead note at interval class 1/6/11, it loses its
chord, clips to a 0.5-beat palm-mute chug, and softens 10% — the clash turns percussive. The riff
YIELDS; the raga line is never re-pitched. Runs before bass/double-track derive (band.py).

**A. Intro/alap:** `verify_intro` (gat_verifier.py) — ends on a HELD Sa (≥2 beats), Sa ≥30% of
sounding duration (chikari counts as Sa — Sujit: re-emphasize Sa with chikari/jod between phrases;
prompt teaches it), ≥2 true rests of ≥1 beat, and a rest immediately after a Sa landing (nyas).
The long pause before the mukhada is CODE: `_intro_gen_span` shortens the generation window by
min(cycle, 0.35·window) and placement leaves the tail silent.

**C. Manjha:** generated KNOWING the cached head — `LeadMemo` now carries `form_role`, the prompt
gets a `{mukhada_head}` block naming the head's first swara — and `verify_manjha` checks: fills its
window to the closing sam (0.85–1.15), last note within 2 ladder steps of the head's first swara
(`_seam_violation`, shared), not rhythmically flat. COMPOSER guardrail now enforces the cycle:
every manjha AFTER the first mukhada and IMMEDIATELY followed by a mukhada; plus Sujit's cap —
any lead-less (riff-only) section ≤2 bars, so the gat never vanishes (the old render had an
80-beat sitar gap).

**D. Taan fills:** ONE extra LLM call after the head is cached (`_maybe_generate_fill`): a
half-avartan sixteenth-note taan (`verify_fill`: all 16ths, one longer landing allowed, exact
length, same return-seam rule) spliced by CODE into the middle statement of every mukhada section
≥3 bars — head front half, taan back half, next statement re-enters on its sam. Never the first
or last bar.

**Shared machinery:** `_generate_mukhada_cell` generalised to `_generate_verified_cell(gen_span,
arr, memory, gen_fn, verify)` — one bounded feedback re-roll loop serves mukhada / intro / manjha /
fill (best-of-N kept); `_gat_repair_event` labels which cell was re-rolled.

**Tooling:** `render_composition` writes `out/<name>.json` (the symbolic Composition) beside the
WAV on every render — the free diagnosis this session had to reconstruct from raw MIDI bytes.

**Verified live (end of session):** one batched `compose_flow("Yaman heavy metal fusion")` run —
see the session summary / trace `gat-development-live` for the outcome.

**ANTARA + TAAN architecture (added same session, from Sujit's follow-up + GPT/Gemini convergence):**
- Sujit: "antara sounds random — it should start mid octave, go higher, come down to Sa; repeat the
  motif." GPT/Gemini both diagnosed the same root: "lift into the upper octave" reads to an LLM as
  "new tune, high notes" — it needs a TRAJECTORY (a melodic story), not a register constraint.
- **Antara** = the second movement of the SAME gat: prompt now teaches the 4-step trajectory (quote
  the head in madhya → develop/climb → single late taar peak → descend to madhya Sa, hand off to the
  returning mukhada), and `verify_antara` checks the checkable: quotes the head's opening in its
  first half (`_quote_present`, bounded-gap subsequence, octave-agnostic), opens ≤ madhya, reaches
  taar, peak past 40% and not the final note, ends on madhya Sa. Same feedback re-roll.
- **Taan (taan_long)** = the composition's peak, not "the scale quickly": `verify_taan` checks — grows
  from the MOTIF (fuzzy quote), the shared earned-arc rules (`_arc_violations`, shared with antara),
  lands on a resting swara (Sa/vadi/samvadi), has a real 16th BURST (≥4 consecutive ≤0.25), breathes
  (a rest or ≥1-beat hold), mixes ≥3 distinct durations. `PhrasePlan` gains OPTIONAL
  `taan_style`/`register_plan`/`rhythm_plan` (free strings — the prompt carries the vocabulary; a
  lenient field never burns a schema retry) so the model plans the taan architecturally before notes.
- Taan STYLE taxonomy: GPT proposed badhat-ang/chhoot/vakra/gamak-ang/layakari — per the musical-
  accuracy rule this went to a source-verification pass BEFORE entering the prompt (the tritone
  episode above is exactly why). Verdicts recorded below when in.
- **Queued (next session):** the Producer rubric's antara-architecture criterion (GPT: contrast
  without abandoning the motif / rises to taar / creates the peak / returns to the mukhada — a 10th
  scored criterion + metrics grounding), so the CRITIC can also see the arc, not just the generator.
- **Known gap (fine for now):** the verified gat cells (intro/manjha/antara/taan/fill) live in the
  FAN-OUT path (`generate_lead`); the opt-in studio session (`RMA_STUDIO`, default OFF) bypasses
  them — port the verify+re-roll into the studio loop before flipping the studio on.
- **Taan taxonomy — research verdicts (2026-07-15, web pass; sources in the research trace):**
  GPT's five "styles" partially corrected before encoding. VERIFIED types (all sitar-applicable):
  **sapat** (straight run), **koot** (zig-zag — canonical exam-board name; "vakra" the informal
  synonym), **mishra** (sapat+koot), **gamak** (forceful oscillation), **alankarik** (palta-pattern
  built — "palta taan" as a NAME is unattested), **chhoot** (swift dash down from the taar; the
  descent is the emphasized element). VOCAL-only (not encoded): bol/sargam/aakar/halak/jabda taans
  (though the SITAR has its own "bol tan" = plectrum-stroke patterning — distinct thing, same name).
  The sitar's fast-run idiom is the **toda** — diri DOUBLE-STROKES per note (our bol field already
  renders diri) — "musicians resort to toda once tempo prohibits tan" (Slawek). Masitkhani facts
  now 3-source verified: gat+mukhda begin matra 12, bols dir-da-dir-da-ra; Razakhani start is
  VARIABLE (commonly matra 7, also sam/khali) — encode as variable if ever needed. **badhat(-ang) is NOT a taan type** — it is the gradual-development principle
  (vistar) of the whole performance; encoded as the ARC rule, not a style. **layakari is a
  PARAMETER** (notes-per-matra, dugun/tigun etc.) applied to taans, and the **tihai** is the
  cadence device (phrase ×3 landing on the sam) — both framed that way in the prompt. Structural
  conventions verified: a taan resolves ON THE SAM by rejoining the gat's mukhda; no source
  prescribes a landing SWARA (our resting-swara check is a raga-grammar/nyas design choice, kept).
  Sitar-specific: the instrumental taan is the **toda** (gat-toda; note chandrakantha's divergent
  "toda = tihai" usage); jhala = the chikari-driven fast close. Masitkhani mukhda-from-matra-12 is
  attested but NOT page-verified — flagged, do not encode as hard fact.
- **Post-render catch (same session): the END-ANCHORED-CELL TRUNCATION bug.** The first live run
  with the antara verifier showed "antara re-rolled -> clean" yet the PLACED midi ended the antara
  on Re at exactly the window edge: the verified cell ended on Sa but OVERRAN its window, and
  `place_phrase` truncated the cadence off. The verifier judged the cell; placement changed it.
  Fix: every end-anchored cell now carries a window-fill bound (`_CELL_FILL_MIN 0.85` /
  `_CELL_FILL_MAX 1.02` — the ceiling is ~1.0 because overrun is fatal to the cadence): manjha
  (tightened from 1.15), antara, taan_long, the taan fill (from 1.1), and the intro (ceiling only —
  shorter = more silence is fine; overrun would erase the code-reserved pause). Lesson (talk-gold):
  a verifier must judge what the pipeline will actually PLACE — or bound the input so placement
  cannot change what was approved.

**SECOND FEEDBACK BATCH (same session, Sujit heard the 132bpm render) — ALL BUILT, pure tests
green (475 across 24 files), NO live render yet (Sujit's rule: ask first):**
- **Multiple taan fills:** long mukhada sections now cut ALL middle statements (1..bars-2, cap 3),
  and up to 3 DISTINCT fill cells are written (each verified; later fills see the earlier ones in
  memory to contrast) and ROTATED across the slots — several taan+mukhada phrases per piece, no
  repeated lick.
- **The AOCHAR (intro) — research-verified then encoded** (sources in the research trace; key:
  The Raga Guide pp.2-8, chandrakantha, raga.hu, Deepak Raja, Skidmore/Thompson, ragajunglism):
  the short pre-gat alap opens AROUND madhya Sa, dips into the MANDRA first, unfolds swaras
  gradually (badhat), phrases end sustained on nyas swaras with chikari Sa-punctuation between,
  and closes on the section's LONG final Sa; the gat's own mukhada (not a mohra) is what brings
  the tabla in. `verify_intro` gains: opens ≤2 ladder steps from Sa (never taar), touches the
  mandra, ≥3 separate Sa RETURNS (`_sa_returns`); composer guardrail: intro ≥3 avartans (2 was
  heard as rushed). **The ring-out:** the verified final Sa is EXTENDED by code to ring through
  the reserved gap with a CC11 decay (`Note.fade` + `_fade_ramp` — quadratic ease to a quiet
  floor, snap back at note end): Sujit's "long Sa like a chord with sustain dropping volume".
  Articulation, not composition.
- **Form rules:** the mukhada AFTER a manjha needs ≥2 bars (the head re-establishes before the
  interlude); at most ONE lead-less section in the whole form (the second bridge/breakdown is
  gone); intro ≥3 bars.
- **Cross-voice seeding (deferred no more):** the riff's mukhada-slot prompt now receives the
  sitar's CACHED HEAD (swara+durations) and is framed as its RHYTHMIC REDUCTION — quote the
  accented swaras on the low strings, chug on Sa between. Plumbing: the head rides the lead's
  event stream (`mukhada_cell_from_events`) into `compose_riff(arr, mukhada=...)` — no signature
  churn on compose_lead.
- **Call-and-response solo:** TAAN sections no longer play sitar+guitar in constant harmony —
  the voices TRADE avartans (sitar call, guitar response, alternating) and JOIN in a raga third
  only for the final bar(s) (`_voice_taan_call_response`): the two voices arriving together IS
  the climax.

## DRUM MACHINE V2 — the metal drummer (2026-07-15, this session)

*Sujit's feedback on the groove: pop-like patterns, one groove looped unchanged for whole
sections, no fills or ghost notes, no antara change (half-time, ride instead of crash), no
dramatic entrance — with Logic Pro's Drummer as the north star. A research pass over
drum-education sources (Wikipedia's blast-beat/D-beat/gallop tabs, DRUM! Magazine, Drumeo,
Hudson Music, Toontrack + Nail The Mix programming guides, Logic Drummer architecture docs)
grounded a full rewrite. The drums remain deterministic CODE (derivable, no agent).*

**Root cause:** the old engine knew three shapes (snare 2&4, half-time snare, 8th hats) and
read almost none of the vocabulary the subgenre data already declared — `blast_beats: True`
was never consulted, ride/china/ohat/toms went unused, and the tala accent grid drove only
the tabla. "Groove = tala × subgenre intersection" existed in the docstring, not the code.

**The build** (`crew/drum_patterns.py` = the pure pattern vocabulary; `crew/groove.py` = the
orchestration; only `band.py`'s unchanged `groove_layer(arr, rhythm)` call sits above them):

- **Pattern vocabulary (research-grounded 16th grids):** the kick-doubled heavy backbeat,
  thrash skank + D-beat, traditional/hammer/bomb blasts, the Maiden gallop cell, the
  double-kick carpet, half-time, and the prog "quadruple-meter backbeat" (steady hands, a
  dotted-8th kick drift realigning at the window edge). Patterns tile PER VIBHAG, so odd
  talas (Rupak 3+2+2, Jhaptaal 2+3+2+3) reshape the cells — the lurch IS the fusion.
- **Section energy (the Logic Drummer lesson):** kind + gat form_role → VERSE / DRIVE /
  CLIMAX / HALF, then a per-subgenre style table picks the pattern (death:
  double16→blast→bomb; black: skank→blast→hammer; thrash: dbeat→skank→double16; heavy &
  melodeath gallop; prog follows the riff). **form_role OVERRIDES kind:** the ANTARA rides
  HALF-TIME (Sujit's explicit ask) and `taan_long` is the climax.
- **Cymbal orchestration per section:** tight closed-hat verses; the drive timekeeper per
  subgenre (death rides tight, melodeath/prog punch the bell, doom washes the crash);
  climax = crash wash; breakdown = china quarters; ride-led sections land the sam on the
  BELL — no crash washing over the antara's raga line. New GM voice `bell` (53); death
  gained ride+bell (research: death blasts ride a tight ride). Cymbal fallback chains
  degrade to whatever the kit has.
- **The tala finally drives the kit:** crash+kick on every phrase-opening sam, the tali
  cymbal leans in (+8, belled when riding), the khali vibhag sits back (−10). The phrase
  (A-A-A-B unit) groups short cycles: a 16-beat Teentaal cycle is one phrase, Keherwa
  groups two (`_phrase_cycles`).
- **Variation & fills (fills are BOUNDARY properties, per Logic):** the phrase turnaround
  adds ONE 16th kick pair into the sam + a hotter last backbeat; a mini-fill closes every
  2nd phrase; crescendo snare→tom seam fills at section changes (2 beats, a full vibhag
  into a CLIMAX) with the kick carpet playing through (the metal fill); an open-hat
  wind-up thins the cymbal line before every fill.
- **Entrances:** a kit entering after a kit-less section gets a 16th pickup roll (70→127)
  carved into the previous section's last beat and an everything-at-127 downbeat; a riff
  opening with 2–3 spaced accents gets matched STOP HITS instead (unison crash+kick per
  accent, the groove holding back until vibhag 2).
- **Humanity (velocity, not timing — extreme metal stays near-grid):** four velocity
  levels; ghost snares in the idiomatic pockets (roomy grooves only, never crowding a
  backbeat); the alternate-feet double-kick ladder (112/106/110/104); DETERMINISTIC jitter
  (±4, keyed on position+drum — reproducible, test-stable; black metal stays icy at ±1);
  doom backbeats drag ~15 ms behind the grid.
- **Riff lock kept** (kick on the riff's on-beats); progressive now shadows EVERY riff
  onset 16th-quantized — the Meshuggah/djent "follow".

**Tests:** `tests/test_groove.py` 15→30 pure tests (per-subgenre pattern identity,
antara-rides-half-time, khali dip, A-A-A-B grouping, crescendo/mid-section/into-climax
fills, pickup + stop hits, ghosts, prog follow, determinism, velocity bounds, kit subsets
for all 7 subgenres). Full pure suite: 490 green across 24 files. Deterministic sound
check (fixed riff, NO LLM): `out/drum_machine_v2_demo.wav` — alaap → stop-hit entrance →
drive → ride-led antara → crash-wash taan → breakdown.

## RIFF CAMPAIGN chunk 1 — texture modes + the riff verifier (2026-07-15, this session)

*Sujit's feedback: riffs sound light/happy not metal, no low-string chugs between notes
(hollow), no audible slides/pull-offs/hammer-ons, and — his instinct — long sustained
chords serve sitar fusion better than busy riffs. A GPT review said the same thing
architecturally: the agent treats rhythm guitar as note sequences, when metal is
articulation + rhythm + sustained energy + space ("Rhythm Guitar Arranger, not riff
generator"). EVIDENCE FIRST (out/fusion.json, the render he judged): the piece was YAMAN
(the brightest raga — part of "happy" is the menu pick) with bright chord stacks
outnumbering power weight (36 add9/tenth colours vs 42 octave/fifths); a 79% consecutive
pitch-change rate (a melody, not a riff — LoG/Megadeth sit ~30-50%); techniques WERE
emitted (76% palm_mute, 30 slides, 36 legato) but are nearly inaudible in render — so
half the fix is the RENDERER (chunk 2), not the prompt; and only 2 notes ≥ 2 beats
(nothing blooms).*

**Built (chunk 1 — modes, verifier, prompt):**
- **`crew/riff_texture.py` (new, pure):** `RiffMode` — DRIVE (the chugging engine) /
  PADS (sustained ringing power chords under the sitar — Sujit's texture instinct; antara,
  taans, intro/outro) / STABS (sparse low syncopated chorded hits; breakdown, tihai) —
  decided by CODE from form_role/kind (same pattern as the drums' GrooveEnergy).
  `MODE_BRIEFS` render into the prompt; the numbers in the ask match the enforcement.
- **`verify_riff` — the metal counterpart to the gat verifier:** checkable TEXTURE budgets,
  never taste. DRIVE: ground share ≥35% on one pitch, pitch-change ≤55% ("this is a melody,
  not a riff"), ≥1 true rest (≤35% silence), weighted sam (chord or ≥1 beat), bright-colour
  ration ≤2 (the add9/tenth seats measured as the "light and happy" source). PADS: ring
  share ≥55% of sounding time, ≥1 chord held 2+ beats and every long hold chorded,
  sixteenths a minority. STABS: ≥20% true silence, oct ≤0, ≥half the hits weighted,
  pitch-change ≤45%. All modes: durations ≈ fill the cycle, pick_scrape ≤1, long_slide ≤2.
- **`verified_riff` — the bounded feedback re-roll at the LLM BOUNDARY:** unlike the lead's
  gat cells (verified in the generate loop), the riff wraps its two composition roots —
  `_LLMRiff` (solo path) and `studio_riff_fn` (canvas path + `regenerate_layer`) — so BOTH
  live paths enforce one grammar while the pure loops stay about recurrence/placement and
  injected test fakes bypass verification. 1 re-roll, exact violations fed back ({repair}
  block), best-of-N — a weak riff plays; a live run never dies on texture. Re-rolls are
  visible in traces (each retry is a traced crew call carrying the repair block).
- **Prompt overhaul (`generate_riff` + the riff agent):** reframed as the rhythm-guitar
  ARRANGER (decide where to chug/ring/move/rest); GROUND AND MOVEMENT block (chug ground as
  default texture, movement earned, attack-vs-resonance, the strip-the-pitches test);
  POWER WEIGHT AS DEFAULT with the bright-colour ration named; reasoning must name the
  ground + where the cycle breathes; {riff_mode}/{mode_brief}/{repair} placeholders (a new
  pure test asserts every placeholder has an input — interpolation misses only used to
  surface live).
- **Two sitar-fusion gestures (Sujit's ask):** `long_slide` (wide slow position shift, from
  a fifth below over 40% of the note) and `pick_scrape` (a dive from an octave ABOVE down
  onto a downbeat chord) — RiffTechnique + renderer wheel gestures (`_render_slide`
  generalized) + prompt budget + verifier ration.

**Tests:** new `tests/test_riff_texture.py` (19: mode mapping, per-mode budgets catching
the measured failure shape, re-roll/feedback/best-of-N); test_riff 39→42 (mode+repair
inputs, event mode, the placeholder contract); test_render +1. Suite: 513 green.

**NEXT (chunk 2, approved direction):** make the technique vocabulary AUDIBLE — palm-mute
chugs on a genuinely muted timbre (GM 28 Electric Guitar Muted on a layered channel),
hammer_on/pull_off as true legato (the quick-pull meend gesture, not just a soft attack),
slide from the PREVIOUS note's pitch over an audible window. Then ONE live render (ask
Sujit) to hear modes + verifier + gestures together.

## RIFF CAMPAIGN chunk 2 — the techniques become AUDIBLE (2026-07-15, this session)

*The chunk-1 evidence showed the model was already writing 76% palm-mutes plus slides and
legato — the renderer was swallowing them. Chunk 2 makes the vocabulary sound like what it
says, all in `src/render.py`, contract unchanged (the routing is render-internal):*

- **Palm-mute = a TIMBRE, not a shorter note:** chug notes of a rhythm take route to a
  companion channel playing GM #29 Electric Guitar (muted) — a genuinely muted sample —
  with a soft copy (`MUTE_BODY_VEL` 0.6) left on the distorted take underneath for body.
  The companion (`_mute_channel`) claims the first free channel (never 9), inherits the
  take's pan/detune/reverb so the chug sits in the same stereo spot, and deliberately does
  NOT inherit a specialized bank — on a live Dethmetal render the chunk comes from the GM
  muted patch while the body stays distorted. Degrades gracefully when no channel is free.
- **hammer_on / pull_off = real legato:** besides the softer attack, the wheel now PULLS
  from the PREVIOUS note's pitch (capped ±4 st, over the first 15% of the note — a finger,
  not a slide), only when the previous note ends within 0.05 beats (a connected line) and
  the note is unchorded. `_pull_offset` is the pure helper; `_bends` now arms the range
  for legato notes.
- **slide starts where the line just was:** the fixed −2 st blip became a pull from the
  previous note's actual pitch (capped ±5 st, direction follows the line), falling back to
  the old default when there is no connected previous note.

**Tests:** test_render 25→28 (pure `_pull_offset` cases; byte-level: the companion channel
gets program 28 and the chugs' note-ons while open notes stay on the take; a connected
hammer-on emits wheel events). Suite: 516 green. Deterministic sound check (fixed riff, NO
LLM): `out/riff_texture_demo.wav` — drive cycle with scrape-dive sam + muted chug ground +
hammer/pull figure + slide + long_slide turnaround, then the PADS texture, then STABS;
MIDI verified: muted companion on ch 2 (program 28), 162 wheel events.

**NEXT:** ONE full-flow live render (ask Sujit) to hear modes + verifier + gestures in a
real composition; then judge whether `MUTE_BODY_VEL`, the legato pull window, or the
mode budgets need tuning BY EAR (batch any fixes, re-render once).

## SONGSTERR INVESTIGATION + SGM ADOPTION (2026-07-15, this session)

*Sujit benchmarked our riffs against Songsterr's playback (Obituary "Redneck Stomp" — the
slide-chord/chug showcase) and asked how they do it. Findings are FIRST-HAND (their shipped
player bundles + network capture by a research agent + our own bundle reading):*

**How Songsterr actually sounds good — a two-tier architecture:**
1. **The sound everyone praises is NOT synthesized in the browser.** Playback streams
   PRE-RENDERED per-track Opus stems from their CDN (one stem per track — mute/solo is stem
   mixing; only 100%/50% speeds pre-rendered, other speeds time-stretched client-side with a
   SoundTouch-style stretcher). The stems are almost certainly rendered OFFLINE through Vir2
   Electri6ity (a 28GB Kontakt guitar library) — their bundle contains a full articulation
   compiler in a `vst` mode with Electri6ity's exact CC scheme (CC1 articulation morph with
   palm-mute at amt=48, CC25 pick direction, CC32 string select, keyswitch legato/slides,
   per-STRING channel allocation for coherent chord slides).
2. **Their in-browser fallback synth IS our stack:** libFluidSynth 2.3.0 compiled to WASM +
   the SGM soundfont ("SGM_Plus_HQ", 94.7MB sf3, also split into ~278 per-preset sf2s
   fetched on demand). On this path a palm mute = a per-channel BANK/PROGRAM SWITCH to SGM's
   GS bank-1 articulation presets ("Muted Dis.Gt" for distortion, "Overdrive_GT_PM", ...).
   Their CDN blocks non-browser fetches (403), so we sourced SGM V2.01 from archive.org —
   verified to contain bank1:28 "Muted Dis.Gt" + the POWER drum kit.

**Adopted (built this session):**
- **SGM V2.01 as a stacked extra** (`soundfont.py`, bank offset 300; setup.sh fetch,
  ~236MB, RMA_SKIP_SGM=1 to skip). **Sujit picked SGM's guitar tone by ear** → when
  present, `route_guitars` prefers SGM for ALL guitar voices: GM-compatible, so each take
  keeps its own program (Overdriven L / Distortion R — the two-tone double-track survives
  the swap). Priority SGM > Dethmetal > GM base. Sitar/tabla stay on the Indian Ensemble.
- **The chug companion channel bank-selects SGM's `Muted Dis.Gt`** (`route_palm_mutes` →
  `pm_bank`/`pm_program` on guitar layers; render `_mute_channel` honors it and SKIPS the
  distorted body layer — the distortion is in the sample). GM-mute layering remains the
  fallback.
- **Fixed wall-clock palm-mute gate:** all engines converge on ~60-80ms (TuxGuitar 60,
  alphaTab 80) — `PALM_MUTE_MS = 70`, capped at the written duration, replacing the old
  tempo-relative dur×0.5.
- **A/B piece (original composition, style-level only — the actual song is copyrighted so
  its tab was NOT transcribed):** `out/slide_chug_ab.wav` — 12 measures of slide-chord/chug
  groove at 92bpm through the full new chain (SGM both takes + PM companions on bank 301 +
  double-tracking), verified in the MIDI. Compare against Songsterr's Redneck Stomp playback.

**The transferable tuning menu the research surfaced (NOT yet built — next round, by ear):**
tail-loaded slides (the slide occupies the END of the source note and lands ON the target's
beat — ours slides at the target's start; "never slide from the note's start" is the
TuxGuitar mistake); multi-fret slides as CHROMATIC RETRIGGERED steps (≤1/16th per fret, −2
dynamics) instead of one long wheel glide — the same lesson as our meend fix; legato slide =
no retrigger; per-STRING channels for chord slides (each chord tone gets its own wheel);
RPN bend range 24 (we arm 12); if FluidSynth tone ever caps out, the Songsterr endgame is
offline per-voice stem rendering through a better bank — architecture we already have.
(520 pure tests green after this session's chunks.)

## SONGSTERR MASTERING — there is none to copy (2026-07-15, bundle evidence)

Sujit asked to replicate Songsterr's mastering (comp/EQ/gain). First-hand answer from
their shipped code: **their client applies NO mastering.** Zero DynamicsCompressor /
BiquadFilter / EQ nodes across the FluidSynth worker, the stem-streaming worker, AND the
959KB main appClient bundle. The synth path's whole "mix" is: SGM_Plus_HQ + `synth.gain
1.2` (+ FluidSynth reverb settings whose values are passed at runtime, not shipped as
literals — likely defaults). The "bassy and heavy" of popular tabs lives in the OFFLINE
Vir2/Kontakt stem renders (amp + processing baked in, parameters never shipped to the
client — unknowable from outside). Consequences:
- We now have their EXACT fallback font: `soundfonts/SGM_Plus_HQ.sf3` (94.7MB, public
  URL, license = SGM freeware family / their build UNVERIFIED — demo-only), verified:
  bank 1:28 "Muted Dis.Gt", POWER kit; renders fine on our brew FluidSynth (sf3 OK).
- Their gain 1.2 on OUR mix pins peaks at 0.0dBFS (mean -12.6) — some clipping; their
  own player runs the same hot gain, which is part of the "loud" impression.
- The stem-tier weight is approximated with an ffmpeg master pass (bass shelf +4dB@110Hz,
  3:1 comp, limiter 0.93) — `out/sujit_riff_sgmhq_mastered.wav`. If a variant wins by
  ear, the chain can be wired as an optional post-render step (and/or SGM_Plus_HQ as
  the preferred base font). Chug-parity fixes this session: PM velocity cut removed,
  companion CC7=127, distorted body under chugs at FULL vel (MUTE_BODY_VEL=1.0),
  PALM_MUTE_MS=80.

## DARBARI ANDOLAN — the slow sway, research + gesture v2 (2026-07-17, this session)

Sujit's finding on `fusion_20260716_233308` (Darbari x death, teentaal @160): the
andolan on komal g/d — the ornament that IS Darbari — was inaudible/wrong. Evidence
from the composition JSON + trace, all four causes distinct:
1. **Holds too short.** At 160 bpm the longest ga hold was 2.5 beats = 0.94 s; the old
   420 ms symmetric sine got ~1-2 wobbles — vibrato, not the grave sway.
2. **Tempo negotiation lost the raga's stake** (talk-gold): Pandit's turn-1 reasoning
   SAID "the slow oscillation on komal ga and dha must be allowed to breathe" and
   drafted 140 (death's floor); Riffsmith pushed 160 "too sluggish for a true blasting
   subgenre"; Pandit folded. Nothing in the prompts arms the raga's pace character.
   AND: death is encoded blast-only (`bpm [140, 240]`) — Obituary-style mid-tempo
   groove death (~100-140, Sujit's reference) is UNREACHABLE in the current menu.
3. **Gesture shape wrong.** Symmetric ±0.4 st sine around the note; real Darbari sways
   BELOW the swara only.
4. **Perfect periodicity** reads as machine LFO (confirmed by ear on gesture v1's
   half-semitone 850 ms sin² too — "does not sound natural").

**Research (verified across sources 2026-07-17):**
- AUTRIM/NCPA "Music in Motion" (pitch graphs, autrimncpa.wordpress.com/darbari-kanada):
  ga's intonation is "a progressive series of movements that occur between Re and Ga"
  (i.e. BELOW the swara), "the oscillation on Ga and Dha is slow and subtle",
  "all the movements are slow and dignified"; symmetrical treatment `S R g~ m \ r` /
  `m P d~ n \ P`.
- Rajan Parrikar (parrikar.org/hindustani/kanada): approach notes are the identity —
  ascending `(R)g`, descending `(m)g`; dha mirrored via P (ascent) / n (descent); dha
  often SKIPPED in descent (langhan) while ga is indispensable; "much is made of its
  ati-komal nature" but the nuanced swara-uccharana (kan, volume, attack direction)
  is the defining feature. (Our kan table already encodes exactly these approaches.)
- Practical MIDI corroboration (GPT notes Sujit supplied): depth ±20-35 cents only;
  settle ~250 ms after landing BEFORE the sway; ~1 oscillation/s; aperiodic (every
  wave different); mostly below the note; subtle CC11/brightness tracking the dip;
  meend-into-andolan (R -> g~) is the most convincing entry; don't overuse — alap/
  vilambit heavy, taans nearly none.

**Gesture v2 (built, `src/render.py`):** land -> settle (ANDOLAN_DELAY_MS 250) ->
slow waves BELOW the note only; depth ANDOLAN_DEPTH_ST 0.30 (~30 cents, in the
research band); period ~900 ms; per-wave length (±15%) and depth (65-100%) jittered
DETERMINISTICALLY (the drum machine's `humanized` hash idiom, keyed on note start +
wave index — reproducible renders, unison doubles sway in phase); each wave sinks
faster than it rises (trough ~40% via sin²(π·frac^0.8)); last sample exactly 0 at
note end. CC11 shimmer rides the same curve (ANDOLAN_CC11_DIP 8, full at the swara,
dipped at the trough), disabled when the note carries a fade (fade owns CC11).
**Real-time gate moved into the renderer:** holds < ANDOLAN_MIN_MS (1000) play plain —
only the renderer knows the tempo; the generator flags the swara (raga fact), real
time decides the gesture. `crew/lead.py` keeps its coarse 1-beat cut. Verified: 36
render tests (settle/uneven/deterministic/below-only/gate) + full suite green; demo
MIDI shows every dip below the note, deepest exactly -30 cents, CC11 riding each
wheel event. Sound check: `out/andolan_demo.wav` (A/B plain vs swayed, kan graces on).

**v2.1 — the krintan iteration (same day, Sujit's ear on the v2 demo):** the two
swayed holds entered via a struck kan grace (GRACE_LEN crushed notes = TWO attacks)
read as KRINTAN, and the subtle 30-cent sway underneath couldn't carry the note.
Research answer (AUTRIM; GPT note 8): the Darbari entry is a GLIDE — "R -> g~~", one
attack. Built: meend + andolan now COMPOSE on one note (previously mutually
exclusive) — `_andolan_wheel(after_glide=True)` drops the settle-at-0 event so the
glide owns the onset (safe because ANDOLAN_DELAY_MS 250 > MEEND_GLIDE_MAX_MS 220 —
the first wave always departs from a settled swara). Placement fix that fell out of
the MIDI check: the andolan flag now keys on the note's RESTING swara (the meend
TARGET when it glides, else its own) — the contract is attack-on-written-swara,
glide-to-target, so "R -> g" rests (and sways) on ga, "g -> m" plays straight; the
old check against the written swara could never flag a glide-entered ga. Demo MIDI
verified: attack -100 cents (R), ease onto ga, settle, sway 0..-27 cents below.

**Queued from the same feedback (Sujit's meend notes, GPT-corroborated):** meend is
THREE ornaments, not one — alap meend (300-1500+ ms, ease-in-out, may dwell on an
intermediate swara, destination held), gat meend (~50-300 ms quick connection, glide
belongs to the END of the previous note, lands ON the beat), taan meend (20-80 ms
legato flick — our current capped pull IS this). Plan: a code-set per-note style tag
(from section kind — alap/outro slow, gat medium, sub-beat fast), renderer picks
duration range + curve; LLM never emits bend points. Also queued:
death subgenre widened to the groove pole + per-raga pace/saptak facts (chunk D).

## GAT CATCHINESS CAMPAIGN — Vilayat Khan / Parikh research → five gaps built (2026-07-20, this session)

Sujit's feedback: gats are "not very memorable or catchy — like Vilayat Khan style".
Researched (web agent) against the Imdadkhani-Etawah tradition's own sources — Pandit
Arvind Parikh's "Bandish on the Instruments" + FAQ (the gharana's senior-most voice),
Deepak Raja, Lokogandhar's Masitkhani-baaj articles, a Vishwamohini matra-by-matra gat
notation. Verified findings (full citations in the 2026-07-20 conversation; distilled
facts now encoded in `src/gats.py`):

- **The mukhda is a 5-matra ANACRUSIS** — matras 12-16 of teentaal, launching inside the
  khali vibhag and landing its arrival stroke ON the sam. The anticipation→arrival engine
  is the catchiness mechanism of the form.
- **The stroke pattern IS the gat's identity** (Parikh: without the bol pattern "they are
  just vilambit gats"). Masitkhani grid verified: "da da ra dir da dir da ra" ×2,
  phase-locked, dir on matras 4/6/12/14. Razakhani: bol set "da ra dir dir dar dar da,
  da dir dara da da ra", flexible; mukhda starts sam/7/khali. FLAGGED: no source gives a
  trustworthy Razakhani matra grid (one paper mislabels the Masitkhani grid) — encoded as
  vocabulary + start options, never an invented grid.
- **Parikh's FOUR-line model**: mukhda (home) → manjha (mandra) → antara (taar) → AMAD,
  the composed descent "down to the point where the composition started". 2.5-3 octaves.
- **Tihai** (phrase ×3, last stroke exactly on sam): an adjunct to a taan, antara-only
  within the gat; introduced on sitar by Enayat Khan — this gharana's signature cadence.
- **Improvisation etiquette**: the taan runs matras ~1-11; the mukhda re-enters at 12 to
  land the next sam. **Sam-note rule** (JETIR/Raja): the swara ON the sam is deliberate —
  Sa or the vadi, ideally the pakad's landing.
- **Vilayat Khan** kept the teentaal + Masitkhani/Razakhani frames; composed gats AS VOCAL
  BANDISHES first ("you have to sing to be able to play"), ornaments written INTO the line.

**Built (all five, ~60 new/updated pure tests, suite 686 green):**

1. **Fill geometry inverted → fixed** (`crew/lead.py`): the old splice cut the BACK half of
   a mukhada statement — deleting exactly the approach-to-sam the tradition keeps
   sacrosanct. Now the taan fill LAUNCHES FROM THE SAM and takes the front; the head's own
   APPROACH (its notes from `approach_cut` — the boundary nearest the 5/16 mukhda line,
   tie later) re-enters at its natural beat and lands the next sam. `verify_fill`'s seam
   now targets `reentry_swara` (what the head sounds AT the cut), not the head's first note.
2. **Sam-note rule** (`verify_mukhada`): the head's FIRST note (it sounds on every sam)
   must be a resting swara — Sa/vadi/samvadi, ideally the pakad's landing.
3. **Bol frames as knowledge + verifier + prompt** (`src/gats.py`, `verify_bol_frame`,
   `_render_bol_frame` → `{bol_frame}` in generate_lead/generate_gat): frames picked by
   laya (`frame_for_bpm`: <90 bpm = masitkhani i.e. doom; else razakhani). Three tolerant
   checks — sam struck "da"; dir doublings (position-PINNED to grid matras 12/14 for
   masitkhani-on-16, density-only ≥2 for the flexible razakhani); bols on ≥half the notes.
   A dir = two attacks in one matra (two fast notes or one "diri" — `apply_strokes`
   already splits it). Melody is never judged — the frame is rhythm.
4. **Tihai primitive, code-built** (`make_tihai`/`splice_tihai` in lead.py): the verified
   taan's own closing phrase ×3 + two equal gaps sized so 3P+2G exactly fills the taan's
   final avartan; landing = the section edge where the returning mukhada's arrival IS the
   sam. Applied on `taan_long` only (Parikh's discipline: adjunct to a taan, never sthayi).
   Rejects thin material (<2 sounding notes) and stranded statements (gap > phrase).
5. **Amad — Gat's fourth line** (`Gat.amad`, `verify_amad`, roles.amad brief): rides the
   antara section's FINAL avartan when it has ≥2 bars (`needs_amad`); antara proper is then
   verified `with_amad` (keeps its whole arc, homecoming handed to the amad). Checks: opens
   within 2 steps of the antara's landing, net descent, no re-peak (>2 st above opening),
   ends ≤ madhya, seams into the head's first swara, fills its window, not flat. Placed as
   one combined phrase (antara + pad rest + amad) so the pipeline is untouched. The
   synthetic `amad` form_role rides `model_copy` (no re-validation) — deliberately NOT in
   `FormRole`, so composers can't emit chart-level amad sections.

**Also updated:** mukhada/taan_short/taan_long role briefs (approach framing, tihai now
code's), generate_gat prompt (4 parts + stroke frame), `_good_head` test fixture (frame-
conformant; approach cut at beat 11). NOT built (deferred): #6 singability verifier (leap
cap + survives-ornament-stripping); Razakhani start-option variety (mukhda from matra 7 —
would need cross-bar anacrusis placement); antara riding the head's stroke skeleton.

**Flagged discrepancies (recorded, not resolved):** manjha "middle" vs Parikh's "lower
octave" (we follow Parikh — already built that way); taan-return matra 11 vs 12; Vilayat
Khan's pen name (Nath Piya vs Sajan Piya); tihai landing convention — ours ends AT the
window edge so the NEXT section's downbeat is the landing (the returning head's arrival),
matching the mukhda-as-landing reading.

**Not yet heard** — prompts/verifiers are live-untested; batch a live confirmation with
the next approved render (ask Sujit first, per the standing rule).

### Live fallout (2026-07-20, same day): absorb-don't-raise at the structured-output boundary

First live runs after the campaign died hard: three separate composes each crashed at a Lead
per-section call — the model emitted junk (`meend_swara: ":"`) and the raising pydantic
validator fired INSIDE the native provider's structured-output validation, BEFORE any
guardrail/verify feedback loop could see it → the whole flow died, and the UI silently fell
back to the demo replay (Sujit couldn't even tell it had failed). Three fixes:
  * **Contracts**: every OPTIONAL decoration now ABSORBS junk instead of raising —
    meend targets, grace lists, bols (with "dir"→"diri", "dara"→"darada" aliases: today's
    frame prompts say "dir" everywhere, a Literal landmine), ornaments, riff chord tones and
    techniques. Junk degrades to a plain note / thinner chord; ONLY the core `swara` stays
    strict. In-vocabulary-but-illegal values still hit the raga guardrail, which DOES feed back.
  * **Lead resilience**: `_generate_verified_cell` keeps its best-of-N when a re-roll call
    crashes; `_verify_or_repair_part` keeps the jointly-composed part (legal, flagged) when the
    isolated repair crashes — a dead LLM call downgrades quality, never kills the compose.
  * **UI honesty**: live failure now shows a loud FAILED status + error line in the log and
    re-enables Compose; the silent swap-to-demo on live failure is gone (it was the stage
    failsafe, but it hid real failures — demo is one Source-toggle away when wanted).
Rule of thumb going forward: a validator that RAISES belongs only on fields where wrong data
is meaningless; anything optional/decorative absorbs, because the structured-output layer has
no retry-with-feedback path.

## RIFF RENDERING CAMPAIGN — step 1: the renderer's note model (2026-09-14, this session)

Sujit's ear ("the riffs aren't authentic metal, and they're very choppy") plus a detailed
GPT MIDI analysis of three renders. The review's headline claim was that the choppiness is
ENCODED in the MIDI rather than being a tone problem, and reading the source confirmed it —
along with two more defects the review couldn't see from the MIDI alone. Triage below; only
the renderer's note model is BUILT in this step.

### Verified against the source (not taken on faith)

* **The fixed gate.** `PALM_MUTE_MS = 80` and `_apply_technique` gated every chug to a fixed
  wall-clock chunk. Measured on `out/fusion_20260720_183403.json`: 273 of 419 rhythm notes
  palm-muted, written at 0.25/0.5/1.0/2.0 beats, and **21% written a beat or longer still
  played for 0.16 beats** — a click followed by up to 1.84 beats of dead air. An ordinary
  8th-note chug ran at a 32% gate, which is a deliberate dead stop used as the default.
* **The unimplemented branch.** `_mute_channel` returns `(channel, has_real_pm)` and its
  docstring has always said a routed muted-DISTORTION patch "needs no body layering" — but
  `real_pm` was unpacked and **never read**, so every chug fired two identical attacks (same
  pitch, velocity, length) on two channels. With SGM HQ as the locked base that is the LIVE
  path: a comb-filtered machine-gun transient, exactly what the review heard.
* **Rubber power chords** (Sujit, mid-session: "pitch-bend style chord riffs sound weird,
  nobody in metal does that"). MIDI pitch bend is CHANNEL-WIDE and our chord tones sound on
  their root's channel, so a `slide` on a chorded note sweeps the whole voicing. Measured:
  **85 of the rhythm guitar's 146 wheel gestures (58%) rode a chord**, on both takes.

### Corrected: the review's #3 (hollow chords) is downstream of #1, not a missing model

GPT proposed a `sustain: until_next_attack` field. Measuring the transitions separately by
articulation showed we already have those semantics: `_sequence_cycle` lays durations
BUTT-JOINED, so **79% of post-open transitions have exactly zero gap** — an open chord
already rings until the next attack cuts it. After a palm-muted note, **100%** leave silence
(median 0.34 beats). The hollow PADS sections were the 80 ms clamp reaching into manjha /
antara / taan, where the agent writes its long chords palm-muted. No contract change needed;
fixing the gate closes most of it. (`until_next_attack` as a *field* is therefore REJECTED —
it would encode as a schema what the geometry already guarantees.)

Also checked and found NOT a problem: MIDIUtil sorts NoteOff (sec_sort_order 2) before
NoteOn (3) at the same tick, so butt-joined repeats of a pitch are safe and GPT's suggested
5–20 ms pre-release is unnecessary.

### Built

* **Slot-relative chug gate** (`_chug_gate`): a chug sounds for `PALM_MUTE_GATE = 0.62` of
  its written slot, floored at `PALM_MUTE_MIN_MS = 55` (a 16th stays a picked chunk), capped
  at `PALM_MUTE_MAX_MS = 700` (a damped string cannot ring longer, so a stray long chug reads
  as a held mute rather than a sustain) and never past the slot. Replaying the SAVED
  composition through it: total dead air 198 → 142 beats, half-beat-plus holes after a chug
  29% → 21%, and +1.3 dB RMS at the same peak (fuller, not just louder).
* **`real_pm` honoured**: the distorted body layers only under GM's CLEAN mute companion,
  which has no gain of its own; a routed muted-distortion patch now plays alone.
* **The wheel invariant**: `polyphonic = len(seated) > 1` disarms every pitch gesture on a
  note that sounds a chord. A guitarist moving a shape strikes it again at the new position,
  so that is now the only way to write it. (The legato branch already had this guard for
  chords; it became the rule for all gestures.)
* **Prompt honesty** (`crew/config/tasks.yaml`): the sentence "a palm-muted note gates to a
  short chunk whatever its written duration" is GONE — see the talk-gold note below. In its
  place: the mute damps to roughly two-thirds of its slot; an OPEN note rings until the next
  attack so its duration IS its ring; silence is composed, never a side effect. Plus THE
  SITAR BENDS; YOU ANCHOR — every pitch gesture single-note only, rare and short (Sad But
  True), a chord position change written as two attacks.
* Tests: `test_render.py` 39 → 42 (gate scaling + both bounds, chord-is-fretted vs
  single-note-still-slides, routed-patch-not-doubled). Suite 692 green.
* Free A/B for the ear: `out/gatefix_183403.wav` — the SAME saved composition as
  `out/fusion_20260720_183403.wav`, re-rendered. Replaying a saved composition JSON costs
  nothing; it is why every render saves its contract.

### Queued, in order (NOT built — each its own step)

1. **`verify_riff` budgets the gate can't fix**: reject a normal chug on a slot ≥ 1 beat
   (the renderer now honours what is written, so the composition must stop asking for a
   2-beat chug); a per-role ground floor (the 083950 render sat at 47%, 183403 at 73%);
   a consecutive-non-ground cap and return-to-ground rule; a `slide` budget (only
   `long_slide`/`pick_scrape` are capped today, and plain `slide` was the 64-per-take
   offender); chug-run velocity variance, so six identical chugs stop reading as programmed.
2. **Double-track humanisation**: `_DOUBLE_DT = 0.02` beats plus a constant detune makes the
   right guitar a delayed copy. Vary onset, velocity and gate per note.
3. **Anchor plumbing**: `arr.anchor` exists on the Arrangement but `inputs_for` never passes
   it, so the prompt tells EVERY riff it "REDUCES" the gat head — a `riff_first` piece is
   still composed gat-first. Pass `{anchor}` with operationally different instructions.
4. **`arrange_riff_against_lead`** — GPT's best structural idea, and the one worth an agent.
   Today `generate_riff` chooses chords from raga legality plus metal weight, never from
   what the sitar is sounding on that beat, and `Section.harmony` (drone / modal_pedal /
   progression — already decided by the composers) is NOT passed to it. A second pass AFTER
   the lead exists, with LIMITED AUTHORITY: it may change voicing, open-vs-muted, sustain,
   velocity, and chord root at stable arrivals; it may NOT move attacks or change the cell
   rhythm, ground pattern or turnaround. Code precomputes a `HarmonicGuide` (lead focus,
   stability class, meend destinations, phrase endings) so the LLM answers only the musical
   question. Default hierarchy: Sa pedal >> Sa + colour >> another supporting root >>
   progression. Rule: hold harmony through movement/meend/taan; change only at nyas, stable
   arrival or a planned harmonic change. The third question nobody currently asks is "do
   these two lines coexist?" — the riff composer asks "is this a good riff?" and the lead
   composer "is this a good raga line?".
5. **Short-cell riff architecture** (`cells` + `cycle_form` over 1/2/4-beat units instead of
   a 16-beat event stream). Real merit, biggest contract change; revisit after the above are
   HEARD. Note the review's premise that the cycle repeats unchanged is STALE — `riff_family`
   already develops per-bar variants (base / prime every third bar / stripped / double).

**REJECTED**: a dedicated LLM Riff Critic. Every failure it would score — ground share, gate
distribution, pitch economy, slide density, velocity uniformity — is deterministically
checkable, so by our own rule (code decides the checkable) they belong in `verify_riff`,
free, not in a paid judge with a debate surface. **REJECTED**: the shared GrooveGrid planner
— it inverts our actual dependency, since `groove.py` derives the drums FROM the finished
riff, so the kick already follows the guitar.

### Step 2 — the coexistence report (BUILT, pure; the arranger pass is NOT)

`crew/coexistence.py` — the detection half of Sujit's ask ("an agent that checks whether riff
and melody align, and asks one of them to change"). Pure, no LLM, `(comp, arr)` like
`composition_metrics`. Built first on purpose: it is the evidence the repair pass reads, the
trigger deciding whether that pass runs at all (a clean section costs no tokens), and it
sizes the problem before we spend anything on it.

**Two findings, different cures.** GRIND = a riff pitch at a harsh interval class (1/6/11)
under a SETTLED melody note; classified by what the melody is doing — HELD (≥1 beat, the ear
tunes to it), STABLE (≥0.5), PASSING (shorter, movement). A harsh interval under a passing
note is ordinary metal and is counted as context, never reported — flagging it would flatten
the music. CHASE = the riff changing ROOT where the melody is still moving, which is what
makes chords feel random: the floor should hold through a run and change at an arrival.

**Three things the existing guard missed,** found by writing the detector:
* `harmonize_riff_to_lead` compared the WRITTEN swara, but the renderer sounds a meend at its
  TARGET (`build_midi`: `sounding = target if target is not None else pitch`) — so a glide's
  clash was judged against a pitch nobody hears. `_note_pitch` is now `sounding_pitch`,
  shared by both the guard and the report (one definition, and the guard is fixed).
* Chord TONES were never checked. `_seat_chord_tone` seats them consonantly against their
  ROOT and never against the melody, so a stack can fight the tune where its root is clean.
  Interval class is octave-invariant, so seating is irrelevant and no render import is needed.
* Only notes under a lead note held ≥1 beat were considered at all.

**Measured on `out/fusion_20260720_183403.json`** (post-guard — these SURVIVE it): 185
grinds over 419 riff notes, 126 of them under HELD melody notes, 28 from chord tones, split
81 major-sevenths / 73 semitones / 31 tritones; 27 chases; and 474 passing grinds correctly
filtered out as context. The guard's dampening is real but partial, and it leaves no trace,
so none of this was visible to any critic or to us.

`render_coexistence(report)` emits the prompt block (flagged sections only, one line when
clean) an arranger pass will read. Tests: `tests/test_coexistence.py` (11). Suite 703 green.

**Gap noticed:** a render saves its Composition but NOT its Arrangement, so a historical
render cannot be attributed per section (the run above had to treat the piece as one span).
The arranger pass needs per-section attribution; saving the Arrangement beside the JSON is a
one-line change to make when we build it.

**Still to decide before building the repair pass** (Sujit's call): direction of yield. Our
recommendation stays asymmetric-by-default with the ANCHOR as the right-of-way rule —
`gat_first` ⇒ the riff yields (the raga line is already certified by the gat verifiers and
re-rolling it discards that verification and spends the slowest agent), `riff_first` ⇒ the
lead bends around the hook. Direction decided in CODE, never negotiated between two agents:
a symmetric negotiation is an unbounded loop with no referee.

### Step 3 — the ARRANGER, the repair pass (BUILT 2026-09-14)

Sujit's ask, with the right-of-way rule he approved. `crew/repairs.py` (pure) + `crew/arranger.py`
(the agent) + the `arranger` / `arrange_against_lead` prompts; wired into `compose_band` after
the lead and riff exist and BEFORE the orchestra and the derived voices, so everything
downstream inherits the repaired lines.

**Not a re-generation.** Regenerating the riff against the melody would destroy the hook every
time the melody changed, so the arranger chooses from a MENU of legal local edits to ONE note.
It cannot move an attack or change a cell's rhythm — the riff's identity survives by
construction, not by asking an agent to be careful. Verified on the real piece: 0 attacks moved.

**Three properties make it live-safe:**
* WHO MOVES is code (`right_of_way`) — the anchor's rule, never a negotiation: `gat_first` ⇒ the
  riff yields, `riff_first` ⇒ the melody bends. A section whose gat role makes one voice the
  identity overrides the anchor (nothing re-pitches a taan; nothing softens a breakdown).
* WHAT IS LEGAL is code (`grind_repairs`) — every option offered is already raga-legal, and
  reseats refuse direction-sensitive swaras outright since a local repair cannot see phrase
  direction. The agent chooses taste and only taste; an id it was never offered falls back to
  the safest legal repair (the menu is the authority, not the reply).
* IT ALWAYS TERMINATES — one bounded pass, then a deterministic sweep damps what is left. A
  decider that throws, answers short, or keeps everything cannot leave the piece worse than the
  old guard did (all three are tests).

**Cost follows the evidence:** a clean section never reaches the model (a test asserts the
decider is not even called), and only the worst `_MAX_FINDINGS = 8` clashes per section are put
to it — a prompt that grew with the damage would cost most exactly where the music is weakest.

**What the measurements changed while building** (each a case of code being musically wrong in
a way only the data showed):
1. Reseating with no preference rebuilt the riff around whichever swara the raga listed first —
   95 roots moved onto tivra Ma. Reseats are now ranked: hold the PREVIOUS root (the floor stays
   put), then the ground Sa, then nearest pitch.
2. Even ranked, it moved 88 GROUND strokes onto the leading tone. The ground is most of what
   makes a riff read as metal, so when the ground itself clashes the repair is to DAMP it, as a
   guitarist does; only a movement note is worth relocating. Ground share now 73% → 74% across
   a full pass (it was falling to 62%).
3. The detector over-reported: a short unchorded palm-muted note is a percussive TOUCH, over
   before the ear can tune it — which is exactly what damping produces. Counting it meant a
   repaired note still read as broken and the pass could never converge. With touches excluded
   the honest figure for the 2026-07-20 piece is **107 grinds, not 185** (the difference is what
   the old guard had already reduced to touches — it was working, just invisibly).
4. Damping preserved a slide, so the clash survived at half a beat with a gesture that made no
   sense there. `damp_note` now forces palm_mute, and it is ONE definition shared by the repair
   menu and the last-ditch guard so the two cannot drift.

**Dry run on `out/fusion_20260720_183403.json`** (deterministic decider, no LLM): grinds
**107 → 0**, 69 of 419 riff notes touched (16%), 0 attacks moved, 0 melody notes moved (the
piece is `gat_first`), repairs 66 damp / 24 drop_tone / 26 hold_root / 6 reseat.

**Honest limitation — chases barely move** (27 → 27: 8 fixed, 8 cascaded onto the next note, 19
unchanged). Holding one root just relocates where the root changes, because the real cause is a
riff that changes root far too often under a moving melody. That is a PITCH-ECONOMY problem and
belongs in `verify_riff` (queued step 1), not in a one-note repair. Worth saying plainly rather
than tuning the number.

**Live cost note:** the arranger is wired into `compose_band`, so the next live run makes one
extra small call per flagged section. A clean section costs nothing.

### Step 4 — riff verifier budgets + double-track humanisation (BUILT 2026-09-14)

**The budgets** (`crew/riff_texture.py`) — the composition-side half of the gate fix. The
renderer now honours what the riff writes, so the riff has to stop asking for the impossible,
and the prompt states each of these so the ask and the enforcement agree:
* **No chug written as a sustain** — a palm-muted note longer than 1 beat is a request the
  articulation cannot deliver (a quarter-note chug stays legal; a test pins that, so the cap
  cannot creep into outlawing ordinary doom).
* **No pitch gesture on a chord** — the wheel is channel-wide, the renderer now drops such a
  gesture, and a gesture the model believes it wrote is worse than one it never wrote.
* **Ground floor 0.35 → 0.55**, calibrated on the two real renders rather than picked: the riff
  Sujit called "light, not metal" sat at 47% ground, the one he called the best foundation at
  73%. 0.55 separates them; 0.35 could never fail.
* **Non-ground run cap (3)** — a share alone is satisfiable by one long tune followed by a
  block of chugs, so how long the riff may wander before coming home is checked separately.
* **Plain `slide` budget (1/cycle)** — only `long_slide` and `pick_scrape` were capped, and
  plain slide was the 64-per-take offender.
* **Chug-run accent** — a run of 4+ palm-muted notes at ONE velocity is the "programmed" tell.
  Rests break a run (the detector reads the full cycle): counting over sounding notes alone
  glued two three-chug figures either side of a rest into a run of six nobody played, which the
  existing clean fixture caught immediately.

**The double-track** (`crew/generators.double_track`) was one performance shifted by a constant
`_DOUBLE_DT` with a constant detune — the review measured exactly 19 ticks on every note, which
the ear hears as slapback or chorus rather than a second guitarist. Each note now lands, is
picked and is held slightly differently (`_second_take`): onset ±~6 ms around the Haas offset,
velocity ±5, duration ±10%, each salted separately so they drift INDEPENDENTLY — varying them
in lockstep would just be a second copy with a different constant. Deterministic and keyed on
the note (the drum machine's idiom), never an RNG, so re-renders stay reproducible and tests
stay stable; capped under ~25 ms so the pair still fuses instead of flamming.

Tests: `test_riff_texture` 36 → 44, `test_generators` 32 → 35. Suite 732 green.

### Step 5 — the Conductor's repair vocabulary + a prompt batch (BUILT 2026-09-14)

Triage of GPT's whole-prompt review (my verdicts per item are in the session record; the two
I acted on are below, the one I rejected is noted).

**The repair vocabulary (GPT #14 — adopted, and the reason it mattered).** `ConductorRuling`
named a LAYER, which was the only vocabulary available while every repair was a regeneration.
That forced the wrong operation on a whole class of faults: told "the guitar fights the
sitar", the referee could only re-roll the riff — discarding a working hook AND re-rolling it
against the same information that produced the clash. `RepairOperation` now names WHAT to do
(`regenerate_lead` / `regenerate_riff` / `regenerate_orchestra` / `arrange_riff_against_lead`),
the Flow dispatches on it, and a relationship complaint routes to the Arranger instead of a
generator. `repair_operation` reads a layer-only ruling as "regenerate that voice", so a model
answering in the old shape is never a failed run. A relationship repair threads no directive
into the chart (there is no generator to steer) — a test pins that.

**Found while wiring it:** the Arranger was only reachable from `compose_band`, and the real
pipeline is the Flow, which calls `compose_lead`/`compose_riff`/`band_layers` directly. So the
pass we built would never have run in a live composition. It is now in `_compose_voices`,
before the orchestra scores around the two lines and before bass/drums/double derive from the
riff.

**Prompt batch** (all verified against the code first):
* **Rasik's scope was a false claim.** The prompt asked about "this finished composition" but
  `_RasikCrew.run` passes only the lead line — so a beautiful sitar line over strange guitar
  colours scored 5/5 on raga authenticity. Renamed to the melodic line's authenticity, with
  the prompt saying explicitly what it is not being shown and why (accompaniment legality is
  code's; how it SITS under the melody is the Arranger's).
* **The sequence instruction was a real musical bug.** "S R g, then R g m, then g m P" teaches
  marching one contour up successive degrees — a Western device that can be perfectly legal
  and still erase the raga, especially in the vakra ragas whose zig-zag IS their identity
  (Bageshree, Jog), and which can walk straight through a `directional_varjya` rule. Now
  conditional on the chalan supporting it, with the Hindustani devices (repeat, fragment,
  layakari, register shift, nyas displacement, question/answer) listed ahead of it as always-safe.
* **"aim to fill it"** rewarded density in the one voice whose silences are the point — the
  same failure the lead-latency campaign fought with its anti-over-fill schema example. Now
  "compose WITHIN the window; a held note and a deliberate silence are part of the phrase".
* **The 80% pakad quota** is now a placement rule (openings, resolutions and phrase boundaries
  carry the pakad; connective passages move more freely) rather than arithmetic, with the
  opposite failure — a line that paraphrases the pakad end to end — named explicitly.

**REJECTED — GPT #13's Performance critic.** The gap is real (no critic could hear an 80 ms
chug, a rubber chord or a hollow sustain), but every criterion it proposes — gate distribution,
sustain continuity, bend realism, velocity dynamics, double-track realism, density — is a
NUMBER. By our own rule those belong in `verify_riff` and `crew/metrics.py`, where several now
are, not in a paid judge with a debate surface.

**REVERTED mid-change:** GPT #4 wanted the intro's 3-avartan minimum relaxed as over-rigid. It
is enforced by the composer guardrail (`_MIN_INTRO_BARS`) and the comment records it as Sujit's
own ear ("a 2-avartan intro was heard as rushed", 2026-07-15). Relaxing the prompt alone would
have fought the guardrail; a recorded listening judgement outranks a reviewer's prior.

Also cleared three stale unused imports in `crew/orchestra.py` so `ruff check crew/` is usable
as a gate again. Suite 736 green.

### Step 6 — the harmonic guide, the brass hierarchy, performance metrics (BUILT 2026-09-14)

The rest of the queue from the prompt review, and the end of this campaign.

**The harmonic guide (`crew/harmonic_guide.py`, pure)** — GPT #10, adapted. The failure is
assembled entirely out of correct decisions: the clean guitar rotates its composer-chosen
colours, the orchestra sustains its string/choir voicing, the riff stacks its own swaras, each
LEGAL and each chosen independently — and the piece ends up holding S, P, g, m and n at once,
a cluster nobody designed. The guide is DERIVED, not decided: per section it reads what the
melody actually settles on (held/stable notes, by sounding pitch so a meend counts where it
lands) and names the swaras that would grind underneath. The accompanying voices filter their
SUSTAINED tones through it and keep everything else — their orchestration, register and
rhythm are untouched. Two deliberate limits: it says nothing about passing notes (policing
every eighth note would flatten the writing), and `supported()` can never filter a voice to
nothing (a pad that drops out is a worse answer than a pad with one colour) — both are tests.
Rather than building GPT's new artefact from scratch it reuses the coexistence detector's
`stability_of`, so the two can never disagree about what "settled" means.
Wired at exactly two tone-picking points: `harmony.bar_voicings` (clean guitar) and
`orchestra._voicing` (strings + choir only — brass stabs and timpani are over too quickly to
stack into a cluster). Both default to no guide, so every existing caller is unchanged.

**The brass hierarchy** — GPT #11, adopted. Stabs landed on every sam AND every tali of every
avartan, so guitar + kick + tabla + brass arrived together, every cycle: if everything is an
arrival, nothing is. `_stab_beats` keeps the sam every avartan and answers a later accent only
on alternate cycles — the bar you expect it and the bar you don't.

**Performance metrics** — GPT #13's gap, our shape. Five piece-level numbers in
`crew/metrics.py`: `rhythm_ring_share`, `rhythm_chug_share`, `rhythm_silence_share`,
`flat_chug_runs` and `accompaniment_grinds`, rendered as a "HOW IT PLAYS" block, plus ONE new
Producer criterion (`performance`, the 10th). This is deliberately NOT the separate critic the
review proposed: every criterion it listed is a number, so the checkable half belongs in
`verify_riff` (per cycle, already there) and these metrics (piece-level, which the per-cycle
verifier structurally cannot see). `_silence_share` unions overlapping notes so a chord is not
counted as three voices' worth of sounding time.
Measured on `out/fusion_20260720_183403.json`: 65% chugs, 37% ringing, 21% silent, and **9
flat chug runs** — the "programmed" tell Sujit and the review both heard, now a number the
Producer reads. (Its 0 accompaniment grinds is vacuous: that render had no clean or orchestra
layer. The guide is unmeasured on real data until a symphonic run.)

Adding a required 10th criterion updated every `ProducerScores` fixture rather than giving it
a default — the other nine force the model to commit, and a silently-defaulted score is a
score nobody gave. Suite 753 green.

## INTRO / ALAP — the jod was a pad, the chikari a sustain (2026-09-14)

Sujit: "the chikari/drone in intro is not natural, it comes unnaturally out of rhythm — in
sitar we play it just like any note rhythmically; it's generally used when a note or matra is
empty, so to fill the space we play chikari." Measured all three 2026-07-20 intros (the first
64 beats) before changing anything.

### What the MIDI actually showed

* **The offender is the JOD LAYER, not the chikari** — and it is OUR deterministic code, not
  the model. `intro_jod_layer` struck a mandra Sa once per avartan and held it for the WHOLE
  cycle: four 16-beat notes per intro, in all three renders. (The external review saw the same
  events and attributed them to the chikari implementation; that was wrong.)
* **Chikari barely exists.** Exactly ONE per intro in each piece, written 1.5 / 2.0 / 3.0
  beats. So the device that should supply the alap's punctuation was itself a sustain.
* **Nothing in the intro keeps time.** Counting every rhythmic voice in the first 64 beats:
  083950 and 183403 have FOUR drum hits and nothing else; 084813 adds the clean guitar. Over
  that sit a 448-beat tanpura, four 16-beat jod notes, four 16-beat orchestral string pads, and
  a lead whose final note holds 21 / 17.5 / 11.5 beats. 084813's lead covers 37% of the intro.
  Four or five simultaneous sustains and almost no attacks is why it reads as random: there is
  no rhythmic frame to place anything against.

### Built

* **The jod is a STROKE placed where the melody leaves space.** `intro_jod_layer(arr,
  lead_layers)` now finds the holes the lead actually leaves in each avartan, quantises to the
  beat grid (played in time, like any note), strikes a short ringing Sa that fades, and caps
  the strokes per cycle so the drone string stays punctuation. No lead to answer ⇒ one stroke
  per avartan's sam — still a stroke, never a pad. A melody that never stops ⇒ silence.
* **A chikari is capped at 0.5 beats** (`_CHIKARI_MAX_DUR`, `verify_intro`) with the prompt
  rewritten to match: a struck drone string filling an empty matra, played in time and then
  gone; held, it becomes a second drone over the tanpura.

### Researched, NOT encoded — the raga-specific chikari tuning

Sujit: Bageshree tunes the top strings Sa Sa Dha Ma rather than Sa Sa Pa Ga, and strings 1-2
dominate. Two independent sources support the PRINCIPLE that this top-string tuning is
raga-dependent — Rāga Junglism's sitar page ("when playing ragas with an absent Pa and/or
strong ma, the top-layer Pa strings are set to ma instead") and the Malkauns/Marwa material
(Malkauns omits Re and Pa so that string is tuned to ma or dha; Marwa's drone strings tuned to
Dha and Sa). What is NOT sourced is Bageshree specifically, which DOES have Pa (vakra,
avaroha-only) — so it is not covered by the "absent Pa" rule, and encoding it would be
guessing against our own accuracy rule. Sujit is a practitioner and his own playing knowledge
is a legitimate primary source; it should be recorded AS THAT, with the raga entry saying so.

Related and also unresolved: `drone_swaras` picks the tanpura companion from a fixed
preference list (Pa, else Ma, else Ni), so it cannot see a Pa that is present-but-weak
(Bageshree) — and for Marwa it currently picks tivra Ma where the sourced practice above
suggests Dha. Both need a decision from Sujit before any change; the drone is raga knowledge,
not code style.

Suite 758 green. Not yet heard.

### The intro's MELODY — rhythm, phrase entry, and the octave arc (2026-09-14)

Sujit, after the jod fix: are prompt changes needed to make the intro right melodically and
rhythmically? Measured the same three intros before answering.

**What the rhythm actually was.** Note values were almost entirely 1.0 / 1.5 / 2.0 beats — a
flat stream with no contrast. Rests: exactly THREE gaps in every piece (the verifier's floor
of 2 rests + a nyas rest, treated as the target), totalling 6 of 64 beats (9%) in two of them.
And each intro closed on a single note of 17.5 / 21 / 11.5 beats — 27%, 33% and 18% of the
whole alap in one sound, because the brief asked for "the longest of the intro" with no
ceiling over a window the model was told to fill.

**Phrase entry was the real "randomness", and the fix already existed.** `_place_intro_phrases`
locks every phrase to the cycle — but it was only used when the clean guitar happened to be in
the section, as though the arpeggio were what made the cycle audible. The two renders WITHOUT
a clean layer are exactly the two whose phrases drift. It is now unconditional.

**Sujit's correction on the grid (important):** locking to the SAM is too coarse — teentaal's
sam comes every 16 beats, so one phrase per avartan leaves the alap threadbare. The unit is
the VIBHAG, which in teentaal (4+4+4+4) is exactly a 4/4 measure. `vibhag_starts(arr)` derives
them from the accent grid (sam + tali + khali), and `_next_vibhag` snaps phrase starts there,
falling back to the sam for a tala declaring none. Notes still flow freely WITHIN a phrase —
only entries snap, which is what makes the silence after a phrase read as anticipation.

**Built (verifier):** silence is now a SHARE (`_INTRO_REST_SHARE` = 18% of the alap) rather
than a count of rests, because a count is satisfiable by writing the minimum — which is what
happened; and no single note may exceed `max(4 beats, 15% of the alap)` — the beats floor
matters, since a share alone would outlaw the held closing Sa that `_INTRO_HELD_SA` requires
in a short window.

**Built (prompt):** phrases enter on a measure's first beat and the silence after runs as long
as it needs; silence is about a quarter of the alap; rhythm has contrast (a flat stream of 1-2
beat notes reads as a machine pacing itself); each phrase GROWS OUT OF the one before it
rather than being a fresh idea per avartan; the arc is an octave journey reaching the taar at
its widest and then either descending home or resolving on the taar Sa (the verifier already
permits either — the close requires Sa, not an octave); the closing Sa is 2-4 beats, not
however much window is left. Also corrected the line that described the jod as a SUSTAIN
holding home under the whole alap — it is now strokes in the gaps, and the prompt said
otherwise.

**On "should the sitar follow an arpeggio pattern?"** — no, and the reason is worth keeping.
A repeating arpeggiated figure is a regular subdivision; an alap's rhythm is irregular by
design, and imposing a pattern would trade one kind of generated-sounding music for another.
What is right in the instinct is the FUNCTION: a gentle pulse under a sparse melody. That job
now belongs to the jod strokes, which is why the sitar can be sparser rather than more
patterned.

### Chikari tuning — encoded as knowledge (2026-09-14)

`chikari_swaras(raga)` in `src/raga.py`. Strings 1-2 are Sa (the stroke's body); 3-4 carry the
raga's colour, DERIVED by default from the same substitution the tanpura makes (sourced:
Rāga Junglism's sitar page — for ragas with an absent Pa or a strong ma the top-layer Pa
strings are set to ma; Malkauns retunes to ma or dha; Marwa's drone strings sound Dha and Sa).
`_CHIKARI_TUNINGS` holds only the ragas that do NOT follow from that rule — currently
Bageshree (S S D m), which has a Pa and so is not the "absent Pa" case, but is tuned to its
vadi Ma and its strong nyas Dha. **Source: Sujit's guruji (oral tradition, via Sujit) —
recorded as a practitioner source rather than dressed up as a citation.** Tests assert every
string is legal in its raga, since these ring under every stroke.

NOT yet wired: a chikari still renders as one taar Sa. Sounding strings 1-2 as a pair (and 3
occasionally) needs a contract change — `LeadNote` has no chord field — plus per-string
velocity weighting (`CHIKARI_STRING_WEIGHTS`) and a few ms of stroke sweep in the renderer.
That is the next step, and it belongs with the jor/jhala work where the upper strings become
a rhythmic engine. Suite 764 green.

## FIRST LIVE RUN OF THE CAMPAIGN (2026-09-14) — `fusion_20260914_204815`

Query: "a symphonic doom fusion in Bageshree, in the key of D". Accepted on the first pass,
0 revise rounds, Ustad legal, both aesthetic critics satisfied.

**What worked, measured in the output:**
* **The Arranger made real calls** — 127 clashes repaired across 6 sections (36 / 4 / 36 / 8 /
  3 / 40). The pass exists in the live pipeline, which it would NOT have done before the
  Flow wiring fix.
* **The jod is a stroke**: 3 strokes of 2.0 beats, on the beat grid (was four 16-beat pads).
* **The intro breathes**: longest lead note 2.0 beats (was 17.5-21), silence 62% of the intro
  (was 9%), phrase entries on the vibhag grid. The tala came out JHAPTAAL (2+3+2+3), so the
  vibhag starts are beats 0/2/5/7 of a 10-beat cycle — the entries at 10/20/30 are sams, and
  the "4/4 measure" idea generalises to the vibhag exactly as intended.
* **The double-track is a performance**: 152 distinct onset offsets (was one constant).

**Two bugs the run exposed — both the morning's lesson repeating.** A deterministic pass
running AFTER the verifier undid what it had guaranteed:
* `riff_family._stripped` DOUBLED durations, turning verified 0.75-beat chugs into 1.5-beat
  ones — past `_PM_MAX_SLOT`, after `verify_riff` had passed the cycle. Worse musically: a
  longer palm mute is not a longer sound, it is the same chunk with more silence after it,
  which is the opposite of the room the variant exists to make. It now drops the mute when it
  lengthens a note, so the thinned riff actually rings under the taan.
* `_prime` wrote its turnaround slide onto whatever the last sounding note was, and `_double`
  chorded every note while keeping its technique — producing 13 of 16 pitch gestures ON
  CHORDS, which the renderer's new invariant silently drops. So the turnaround was vanishing.
  Both now avoid the combination.

**Not exercised:** the orchestra never joined (no `orchestra` in any section's layers), so the
harmonic guide's orchestra path and the brass hierarchy are still untested — `symphonic` IS a
supported subgenre, so either the Interpreter did not extract it from "symphonic doom" or the
composers did not add the layer. Worth a look before the next run.

Suite 767 green.

### Post-render fixes, batch 1 — the drone's Pa, the doubling, the breakdown (2026-09-14)

**The drone was sounding the raga's weakest swara.** `drone_swaras` picked its companion from
a fixed Pa → Ma → Ni list, which cannot see a Pa that is present but WEAK. Bageshree is exactly
that: its Pancham is vakra and avaroha-only (dropped from the aroha in our own encoded entry),
with Ma as vadi and Dha the strong nyas — and the live render droned Sa+Pa for the whole piece
while the clean guitar, which reads the same function for `harmony.mode == "drone"`, spent 34
of its 72 notes on Pa. The raga's most deliberately weakened swara was its most-sounded
accompaniment tone, in every bar. The companion now skips a swara the raga omits in ASCENT.

**CORRECTION to what I predicted:** I told Sujit this would change Bageshree and leave Todi on
Pa. It changes BOTH — Todi's encoded aroha (S r g M d N S) also drops Pa, so Todi now takes its
tivra Ma. That is defensible rather than accidental (madhyam tanpura is standard practice for
Todi, and our own notes record its Pa as sparse), but the prediction was wrong and the change
is wider than advertised. Darbari, Yaman, Bhairavi and the rest keep Pa — they have no
directional varjya at all.

**The unison guitar was shadowing the whole sitar line** — 86% of its notes shared onset AND
swara with the sitar. So the sitar stopped being the distinctive voice, every meend became an
ensemble gesture, and the fast passages turned thick and unarticulated. `_doubled_hook` now
gives the guitar the line's SUSTAINED stretches only: it plays the theme and lays out through
sixteenth-note development, and a lone long note inside a flurry is skipped (one hit in the
middle of a run reads as a mistake, not a part). The mukhada keeps its unison override — that
exists because the returning hook came back audibly thinner without it.

**The breakdown had nothing to drop from.** The live render's breakdown was 14 notes, all 14
palm-muted, with not one open note of a beat or more. `_weighted` counts a chorded palm-mute as
weight, so the existing budget passed it — weight on paper, a click in the air. STABS now
requires at least one OPEN ring, with the brief asking for it on the downbeat.

Suite 774 green.

### Post-render fixes, batch 2 — the empty peak, and saving the chart (2026-09-14)

**Half the taan was silence, and the verifier had already said so.** `verify_taan` requires the
cell to fill 85% of its window, the live taan covered 20 of its 40 beats, and it played anyway:
`_generate_verified_cell` is a BOUNDED repair loop that keeps the best-of-N, so a cell failing
twice still ships. That is the right call for a weak cell and the wrong one for an absent
one — the composition's peak ran for twenty beats with the band vamping under nothing.
`_restated_to_window` now restates the cell's OWN notes until they cover the window (no new
pitches, so it stays as legal and as motif-grown as the verifier found it), applied BEFORE the
tihai splice so the cadence still lands on the section's final sam.

The general lesson, third time this campaign: a bounded verifier guarantees a *bounded number
of attempts*, not an outcome. Wherever the fallback is "ship the best failure", code has to
decide what the failure degrades TO.

**Renders now save the chart.** `flow.finish` writes `<name>.arrangement.json` beside the WAV
and the composition, and `render_composition` takes an optional `arrangement` for direct
callers. Diagnosing this render meant reconstructing section boundaries by guesswork — "the
lead vanishes for 20 beats" could not be attributed to a section. Free to write, never fatal
if it fails, and the triple is everything needed to measure or replay a run with no LLM.

Suite 777 green.
