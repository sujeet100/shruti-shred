# Talk prep — Shruti Shred: teaching agentic patterns

*Living document. Built up as we build the project, so the talk-gold (surprises,
analogies, "why it matters" lines) is captured while it's fresh — not
reconstructed the night before.*

Companion docs: `PLAN.md` (roadmap), `CLAUDE.md` (rules), and a future
`PATTERNS.md` (the code walkthrough — written in Phase 2 once every pattern is
actually in code). This file is the *narrative and stagecraft*; PATTERNS.md will
be the *code tour*.

---

## The talk in one sentence

A multi-agent system composes Hindustani-classical × metal fusion live on stage,
and by watching the agents propose, argue, and revise, the audience learns the
core patterns of building agentic AI — above all that **constraints make agents
creative**, and that good agentic systems pair **hard guardrails (code) with soft
taste (LLM)**.

## Two theses (say these out loud, twice)

1. **Constraints make agents creative.** A raga is a set of *forbidden* notes; a
   tala is a rigid cycle. Hand the agents these constraints and the output gets
   *more* interesting, not less. Freedom is not the input to creativity —
   structure is.
2. **Hard guardrails + soft judgment.** The thing you never let the LLM decide
   (is this note legal?) lives in deterministic code. The thing code can't decide
   (is this *beautiful*, is the raga's soul present?) is the LLM's job. Knowing
   which is which is the skill.

## Audience takeaways (what they leave able to do)

- Recognize the pattern catalog (below) and name which one they need for their
  own problem.
- Draw the line between "guardrail" work (code) and "judgment" work (LLM) in
  their own system.
- Understand why a bounded, refereed debate beats hoping agents converge.

---

## Narrative arc (the story spine)

1. **Hook** — play ~8 seconds of the fusion. "Agents wrote this, live, and two of
   them nearly came to blows over it."
2. **The naive strawman** — one god-prompt, "write metal in raga Bhairav." It
   produces something that's *in scale but soulless*, or worse, breaks the raga.
   No way to know which.
3. **Turn 1 — structure the output.** Agents return *data*, not prose. Now you
   can check it. (Pattern #1)
4. **Turn 2 — the guardrail.** A deterministic validator catches the illegal
   note the LLM will eventually produce. Show the red. (Patterns #2, #9)
5. **Turn 3 — split the job.** Small specialists (generators, critics) beat the
   god-prompt. (Pattern #3)
6. **Turn 4 — taste.** Legal isn't enough. Rasik grades soul. Now two judges
   *disagree*. (Patterns #5, #6)
7. **The money moment — the debate.** Ustad says legal, Rasik says lifeless. They
   argue. A Conductor referees with a clock and rules. (Patterns #7, #8)
8. **Payoff** — revise, re-validate, PLAY. The room hears constraints turn into
   music.
9. **Land the thesis** — one slide: code guardrail | LLM taste.

---

## Demo run-of-show (the live beats)

*(Fills in as the UI lands in Phase 3. Latency budget 60–90s per generation; the
streamed debate fills the wait — the wait IS the show.)*

- Presenter picks raga + subgenre from a dropdown ("audience chose it").
- Panels light up: generators emit, Ustad validates (swara grid turns
  green/red), Rasik scores a rubric.
- On conflict, the debate streams token-by-token. Conductor issues the verdict.
- Revise round; grid goes green; **PLAY**.
- A/B: naive one-shot vs the crew's output, back to back.
- **Insurance:** one-key pre-rendered fallback clip per hero combo, in case the
  network/model dies on stage.

---

## The money moments (where the room reacts)

- **The red note.** The validator catching an illegal shuddha Re in Bhairav,
  live, in red. Visceral proof of the guardrail. *(Built — see the naive-vs-legal
  contrast in `demo.py`.)*
- **The argument.** Two AIs disagreeing about art, then a third ruling. *(Phase
  2.)*
- **The A/B.** Soulless one-shot vs the debated composition. The ear hears the
  difference the patterns made.

---

## Pattern catalog → talk beats

*(Mirrors the table in PLAN.md §4; this adds the podium notes.)*

| # | Pattern | One-liner for the slide | Status |
|---|---|---|---|
| 1 | Structured output as a contract | "Agents don't return prose, they return data you can check." | built (schema) |
| 2 | Deterministic tool = hard guardrail | "The one thing you never trust the LLM to do." | built (`validate_composition`) |
| 3 | Separation of concerns / roles | "Small specialists beat one god-prompt." | Phase 2 |
| 4 | Reflection loop | "Propose → critique → revise, on stage." | Phase 2 |
| 5 | LLM-as-judge | "How do you grade taste?" | Phase 2 |
| 6 | Multi-judge disagreement | "Legal vs lifeless — two judges, one conflict." | Phase 2 |
| 7 | Multi-agent debate | "The agents argue to converge." | Phase 2 |
| 8 | Arbitration + bounded termination | "Debate needs a referee and a clock." | Phase 2 |
| 9 | Hard guardrail vs soft judgment | The thesis, one slide. | built (core) |
| 10 | (stretch) Multimodal judge | "The AI grew ears." | stretch |

---

## Podium notes — per pattern (analogies + why it matters)

**#1 Structured output.** The naive agent returns a paragraph of music
description; you can't validate a vibe. Ours returns swara-JSON — notes with
timing. *Analogy:* the difference between an intern emailing "I think the
contract looks fine" and handing you a redline you can diff.

**#2 / #9 The guardrail (the heart of the talk).** Raga legality is a *fact*, not
an *opinion*, so it lives in code — `validate_composition` checks every note,
including ornaments, against the raga's allowed swaras. *Line:* "You don't ask
the LLM whether the note is legal for the same reason you don't ask it what
1,000,000 × 12 is — not because it can't, but because you can't *trust* it to, and
you don't have to." The whole system is built so the creative, fallible part
(LLM) can never overrule the certain part (code).

**#3 Separation of concerns.** RagaGrammar, MetalRiff, Tala, Ustad, Rasik,
Conductor — each has one job and one prompt. *Line:* "A prompt that does six
things does none of them well; six prompts that each do one thing can be tested,
swapped, and argued with."

**#6 / #7 Disagreement → debate.** The two critics are *designed* to conflict —
Ustad optimizes legality, Rasik optimizes soul, and those pull apart. That's a
feature: the tension surfaces the real tradeoff instead of hiding it inside one
averaged score.

**#8 Referee and a clock.** *Line, verbatim on a slide:* "Debate needs a referee
and a clock." Never ship a multi-agent loop that relies on organic consensus —
live, it hangs. The Conductor caps rounds and always issues a verdict. Bounded
termination is a safety property, not a nicety.

---

## Talk-gold captured during the build

*(Append as we go. Each is a concrete, true story from the actual code — far more
convincing than a hypothetical.)*

### Phase 1 (knowledge core) — 2026-07-11

- **Knowledge = data, reasoning = LLM.** Every raga/tala fact is hand-encoded and
  cross-checked against ≥2 reliable Hindustani sources (recorded in the code);
  the LLM never supplies a fact. *Slide:* show `RAGAS["bhairav"]` — a dict a
  human verified, not a model hallucinated. *Line:* "The agents reason over the
  rulebook; they don't get to write it."

- **Orthogonal axes = combinatorial creativity.** Three small independent
  libraries — 5 ragas × 6 talas × 4 subgenres — already give **120** distinct
  starting points, and they're independent because raga = which notes,
  tala = the cycle, subgenre = the character, with zero overlap. *This is thesis
  #1 made countable:* tight constraints on three axes multiply into a huge,
  navigable creative space.

- **Guardrail completeness (the kan/meend story).** When we let notes carry
  ornaments — *kan* (grace notes) and *meend* (pitch-bend glides) — we extended
  the validator in the *same commit*, because a grace note or a glide-target is a
  real pitch that could otherwise smuggle an illegal note past the guardrail.
  *Lesson for the audience:* every time you widen what an agent may emit, widen
  what the guardrail inspects — or you've quietly opened a hole. *The subtle
  line:* a meend's two *endpoints* are law (validated), but the microtones it
  *slides through* are expression (not validated) — **the guardrail checks
  decisions, not samples.**

- **"Never guess on facts" — modeled in the data.** Sources disagreed on one
  Ektaal bol (*Kat Ta* vs *Kat Tin*); we encoded the common form and flagged the
  variant in a comment rather than silently picking. *Line:* "When your data is
  contested, say so in the data. A confident wrong fact is worse than a flagged
  uncertain one."

- **Testable knowledge.** Because the knowledge is code, it has tests —
  `check_raga_consistency`, `check_tala_consistency`,
  `check_subgenre_consistency` assert e.g. every pakad note is legal, vibhags sum
  to the matra count, every drum voice exists in the kit. *Line:* "If your
  domain facts live in a doc, they rot. If they live in code with assertions,
  they can't."

- **A genuinely alien rule — Rupak's sam-on-khali.** Rupak's cycle resolves onto
  an *unstressed* beat (its sam is a khali, a wave, not a clap). Great 15-second
  aside proving the domain has real depth and the system honors it rather than
  flattening it to "7/8."

- **Drums generated, not tabled.** We chose to *generate* drum grooves at the
  tala × subgenre intersection rather than hand-author a lookup table. *Line:*
  "The moment you catch yourself building a 24-cell lookup table, ask whether
  that's data or whether it's the reasoning you're supposed to be delegating to
  the agent." Keeps creativity in the agent, not in a spreadsheet.

---

### Phase 2 (agentic flow design) — 2026-07-11

- **Agents map to DECISIONS, not instruments (the design money-lesson).** The naive
  instinct is one agent per track — sitar agent, drums agent, tabla agent, solo agent,
  harmonizer agent — and it balloons to ~15 agents. Wrong axis. Instruments are *data*
  (`layers` in the JSON), rendered deterministically; "taan" and "solo" are *sections* a
  generator emits, not agents. The right axis is **responsibility**: understand-intent,
  arrange-form, generate-content (×3 by function), judge-legality, judge-taste, arbitrate.
  ~7 agents, not 15. *Line:* "If you're drawing one agent per *noun* in the output, you're
  organizing by type — the same mistake as a `utils.py`. Draw one agent per *decision*."
  *Why it matters on stage:* every agent is an LLM call, so the wrong axis = 15× latency,
  15× failure surface, and a debate too noisy to follow. Fewer, sharper agents = a legible show.
- **Two roles the domain forced out:** an **Interpreter** (free text → validated brief) and an
  **Arranger** (who decides song *form* and length) — distinct decisions that earned their own
  agent, vs. the instrument-agents that didn't. Good illustration of the judgment call.

### Phase 2, agent #1 — the Interpreter — 2026-07-11

- **The LLM extracts fuzzy; code validates authoritative.** The Interpreter is split in two:
  an LLM turns free text into a loose `RawIntent` (what the user *said*), and a pure Python
  `resolve_brief` validates it against the raga/subgenre libraries into a `CompositionBrief`.
  *Line:* "The model is allowed to be wrong about what you said; it is never allowed to decide
  what's legal." The guardrail thesis, now at the *front door*.
- **Extract, don't decide — separation of concerns as a design boundary.** First cut had the
  Interpreter *choosing* the subgenre and tempo when unspecified. That's a creative decision,
  and it belongs to the composers, not the front door. Corrected: the Interpreter invents
  NOTHING; nothing is even required (a mood-only "make it angry" is valid), and every unstated
  dimension — *including the raga* — is left OPEN for the composers to decide from the mood.
  *Line:* "An intake that quietly picks doom for you is hidden magic; push the creative call
  to the agent whose job it is."
- **Prompt before effort (the debugging lesson).** When mood-only extraction hallucinated a
  whole brief, the reflex was to crank reasoning effort. Wrong reflex. The real gap was the
  *prompt* — missing rules and examples. Solid rules + un-copyable examples fixed it at LOW
  effort (concrete examples, it turned out, got *regurgitated* — the model copied a sample
  raga verbatim). *Rule:* fix the prompt before spending compute; effort/model are coarse
  levers that hide the real bug.
- **The resolver as safety net.** Even when the extractor emits junk (the string "null", a
  bpm of -1, or the word "subgenre" in the key field), boundary validators normalize it and
  the resolver keeps only supported values — so a bad extraction degrades to "OPEN," never to
  a crash or an illegal value.
- **Free-tier reality check (logistics for the talk).** Gemini free tier = **20 requests/day**
  for flash — a handful of test runs exhausted it. The full crew makes many calls per
  generation, so the live demo *needs a paid tier* (or a pre-rendered fallback). Budget this.

### Phase 2, agent #2 — the composers + observability — 2026-07-11

- **Opposed agents, one goal — the debate IS the show.** Pandit (tradition) and Riffsmith
  (metal) hold deliberately opposite priors. Two *neutral* agents collapse into
  agreement-theater with nothing to watch; opposition forces a real exploration of "how
  traditional vs. how aggressive." *Line:* "We didn't give them a goal to disagree — we gave
  them opposite *tastes*, and let them argue toward one chart."
- **Own the loop; don't let the framework be autonomous.** CrewAI *has* built-in
  "collaboration" (agents delegate to each other) and levers to bound it (`max_iter`, timeouts,
  `step_callback`). We deliberately DON'T use it. Our cap falls on a clean *turn boundary* with
  a complete, validated artifact; delegation's caps are circuit-breakers that fire mid-thought.
  *Line:* "A referee with a clock beats hoping agents converge — and the framework's headline
  feature was the wrong tool for a debate you want the audience to *read*." (We do use its
  per-turn levers as within-turn safety: `allow_delegation=False`, `max_iter`, a guardrail.)
- **THE money design beat — the LLM composes, code guarantees.** First cut had *code* copy the
  raga's first pakad as the motif. Sujit caught it: then every Malkauns piece opens with the
  same four notes — mechanical. Fix: the LLM composes the motif (and the form, tempo, tala);
  code only *validates* it's legal in the raga and *derives* verified facts (the tala's accent
  grid). *Line:* "Creativity is the model's; legality and the raga's facts are code's. Give the
  machine the pen, keep the rulebook."
- **Emergent fusion under constraint (the jaw-drop).** Given the raga/tala facts and a nudge to
  design the *seams*, Riffsmith independently proposed a **tihai** (a phrase thrice, landing on
  the sam) doubling as the metal **breakdown**, with the double-kick locked to the tabla's bols.
  Nobody coded "tihai." *Line:* "We handed it constraints from two traditions and it found a
  genuine bridge between them — that's the whole thesis in one breakdown."
- **Chain-of-thought in the schema beats parsing the output.** The Interpreter's hallucination
  wasn't fixed by more effort or by post-hoc string-grounding (a workaround) — it was fixed by
  adding a `reasoning` field *first* in the structured output, so the model justifies each field
  before committing. Same trick sharpened the composers' debate. *Rule:* make the model reason
  in the schema; don't parse your way out of a model problem.
- **`output_pydantic` crashes on any validator that can fail.** Structured-output parsing treats
  a raising validator as a parse crash (it bit us on an empty `registers: {}`). The pattern:
  the schema validates *shape*, a **guardrail** validates *domain* (motif legal in raga → bounded
  retry), and junk gets *normalized* at the boundary. Clean separation, no crashes.
- **Local tracing = the black box opened.** Every run is a trace (unique id, Langfuse-style) of
  spans — each agent's actual prompt, response, tokens, and guardrail retries — browsable in a
  dependency-free local portal. *Talk use:* show the real prompts and a live guardrail retry;
  "this is what 'the agents argued' actually looks like under the hood."

## Anticipated Q&A

- **"Isn't the validator doing the real work, not the AI?"** Exactly the point —
  and the honest answer strengthens the thesis. The validator decides *legal*;
  the LLM decides *good*. Neither alone makes music. Show the soulless-but-legal
  strawman.
- **"Why not fine-tune a model on ragas?"** You'd bury the rulebook inside
  weights where you can't audit or update it, and you still couldn't *prove* a
  given note is legal. Data + validator is inspectable and certain.
- **"What if the agents never agree?"** They don't have to — the Conductor has a
  clock. Bounded rounds, guaranteed verdict.
- **"Hindustani vs Carnatic?"** We're strictly Hindustani (different ragas,
  different tala system); sources are recorded per raga/tala, Carnatic sources
  treated as a red flag.
- **"Is this real Hindustani music or a pastiche?"** We encode pakad/chalan
  (signature phrases), andolan, and kan/meend so output is *idiomatic*, not just
  in-scale, and Rasik checks the pakad is present. Be honest that it's fusion,
  not a classical recital.

---

## Slide seeds / visuals

- Thesis slide: two columns — **CODE: guardrail (certain)** | **LLM: taste
  (fallible)**.
- The `RAGAS["bhairav"]` dict on screen — "verified by a human, not a model."
- Three orthogonal axes diagram → 5 × 6 × 4 = 120.
- The swara grid going red on an illegal note.
- The live debate transcript, streaming.
- "Debate needs a referee and a clock."

## Open questions / still to decide

- Talk length + venue? (drives how deep we go on each pattern)
- How much live-coding vs pre-built? (recommend: all pre-built, narrate live)
- Which hero combos to pre-render as the safe fallbacks (pick by ear in Phase 4).
