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
- **The band cooperating (the second money moment).** Before the critics ever
  weigh in, two agents build a section together on a shared canvas — the riff lays
  down the hook, the sitar answers it, then they refine. Cooperate, *then* critique:
  the build and the argument, back to back. *(Built — the studio session; A/B it
  against "composed in isolation" via `RMA_STUDIO`.)*

---

## Pattern catalog → talk beats

*(Mirrors the table in PLAN.md §4; this adds the podium notes.)*

| # | Pattern | One-liner for the slide | Status |
|---|---|---|---|
| 1 | Structured output as a contract | "Agents don't return prose, they return data you can check." | built (schema) |
| 2 | Deterministic tool = hard guardrail | "The one thing you never trust the LLM to do." | built (`validate_composition`) |
| 3 | Separation of concerns / roles | "Small specialists beat one god-prompt." | built (interpreter, composers, generators) |
| 4 | Reflection loop | "Propose → critique → revise, on stage." | Phase 2 |
| 5 | LLM-as-judge | "How do you grade taste?" | Phase 2 |
| 6 | Multi-judge disagreement | "Legal vs lifeless — two judges, one conflict." | Phase 2 |
| 7 | Multi-agent debate | "The agents argue to converge." | Phase 2 |
| 8 | Arbitration + bounded termination | "Debate needs a referee and a clock." | Phase 2 |
| 9 | Hard guardrail vs soft judgment | The thesis, one slide. | built (core) |
| 10 | Cooperative collaboration (blackboard) | "The band builds a section together on a shared canvas — cooperate, then critique." | built (studio) |
| 11 | (stretch) Multimodal judge | "The AI grew ears." | stretch |

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

### Phase 2, agent #3 — the generators + the full band — 2026-07-11

- **The roster stays lean: only the CREATIVE voices are agents (the payoff of "decisions, not
  instruments").** Of seven voices in the full band, only TWO are LLM — the raga Lead and the
  metal Riff. The Drone, Bass, Drums, and Tabla are all DERIVABLE, so they're deterministic
  code. *Line:* "There's no bass agent and no drum agent, because in metal the bass and the kick
  FOLLOW the riff — that's derivable, not a decision. An agent is for a decision (intent,
  arrangement, legality, taste), never for an instrument." The "why so few agents" answer, made
  audible — and cheaper and more stage-reliable (fewer live calls).
- **Harmony computed INSIDE the raga — legal by construction.** A harmonized taan (sitar + lead
  guitar a "third" apart) takes the third by stepping up the RAGA's own swara ladder, not a
  fixed +4 semitones — so every harmony note is legal automatically, and the validator finds
  zero violations across all seven layers. *Line:* "We don't harmonize in Western thirds and
  then check; we harmonize in the raga, so it's legal before we check." (Honest caveat: a
  pentatonic like Malkauns has no clean third, so octave/unison are the safe voicings there.)
- **The drone is domain knowledge too — and it caught a bug.** Naive tanpura = Sa+Pa. But
  Malkauns has NO Pa; a Sa+Pa drone would be illegal in its own raga. `drone_swaras` derives the
  companion from the raga's allowed set (Sa–ma for Malkauns), so the drone is legal by
  construction. *Lesson:* even the "trivial" background pad is a fact, not a constant.
- **Deterministic ≠ canned — the drums READ the riff.** The worry with a rule-based groove is
  that it sounds robotic. The fix: the kick locks to the riff's on-beats (same rule as the
  bass), the feel changes per section kind (half-time breakdown, double-time taan), and a rule
  drops a tom fill at each transition. The groove is derived from the actual music, not a fixed
  pattern. *Line:* "Deterministic doesn't mean dumb — it means the rule reads the same chart the
  players do." (If the rule-fills ever sound plain, that's the one spot an LLM could earn a place
  — added only if listening proves it needed.)
- **LLM aims, code enforces (timing).** Generators emit swaras + DURATIONS, never absolute beat
  positions — LLMs are unreliable at cross-section arithmetic. Code lays the phrase on the grid,
  seats it in the right register, loops the riff to fill the cycle seamlessly, and truncates to
  the window. *Line:* "The model supplies the music; code supplies the clock." (A user question —
  "will the riff loop cleanly?" — became a hard guarantee: code fills any short cycle so there's
  no gap at the downbeat where the loop repeats.)

### Phase 2, agent #4 — Ustad, the legality critic — 2026-07-11

- **"Code decides the checkable" made STRUCTURAL, not a promise.** The obvious way to build a
  legality critic is to ask the LLM "is this legal?" — and then you're trusting a model to not
  hallucinate a fact. We did the opposite: the deterministic `validate_composition` owns the
  verdict, and Ustad's LLM output type (`UstadNarration`) has **no verdict field it could
  fill** — only an explanation. Code assembles the final `UstadVerdict`. *The demo test:* a
  fake Ustad that LIES ("perfectly legal") still yields verdict `illegal`, because the model
  was never given the pen. *Line:* "We didn't tell the model not to decide legality — we built
  a type where it literally can't." The guardrail thesis, pushed into the type system.
- **One validator, two jobs — guardrail AND tool.** The same `validate_composition` is the hard
  guardrail that gates generator output AND the tool Ustad *calls* to see the violations so he
  can EXPLAIN them. *Line:* "The gate that stops a bad note is the same instrument the critic
  uses to teach why it's bad." Flag vs. explain, from one deterministic function.
- **The agent adds language, not facts — which is why it's the CHEAP tier.** Ustad's whole
  contribution is turning `{layer: lead, swara: R, beat: 1.0}` into "you played shuddha Rishabh
  in the lead; Bhairav wants komal Rishabh there." No judgment, no facts invented — so it runs
  at the low tier. *Lesson:* narration of a deterministic result is a real, useful agent job,
  and it's the one you spend the least on.
- **A subtle tool bug caught by design: no caching on a zero-arg tool.** The tool takes no
  arguments (the piece is bound to it), so CrewAI's default result-cache would key every
  composition to the *same* empty key and hand back the FIRST piece's verdict forever. Caching
  off. *Line:* "A cache is an assumption that same-input means same-answer — a zero-arg tool
  breaks that assumption silently." A nice cautionary aside on tool wiring.
- **Visible tool-call = the ReAct loop on stage.** The trace shows two LLM turns: Ustad calls
  the tool (prompt grows as the violations are injected), *then* answers. That two-step is the
  "visible tools, not autonomous magic" principle made literally watchable in the trace portal.

### Phase 2, agent #5 — Rasik, the taste critic — 2026-07-11

- **The clean contrast: Ustad and Rasik are OPPOSITE by construction.** Ustad's verdict is
  code's (legality is a fact); Rasik's verdict is the model's (taste isn't). *Line:* "Same
  interface — judge a composition — opposite answer to 'who decides?'. That single question,
  asked per criterion, is the whole 'guardrail vs. judgment' thesis." Put the two side by side
  on one slide: `Ustad → verdict from code` | `Rasik → verdict from the LLM`.
- **You don't fix LLM-judge bias by taking the pen — you DISCIPLINE the judgment.** LLM judges
  drift (verbosity = "longer looks better", a gestalt vibe number, self-preference). The fixes
  we actually used: a FIXED 1-5 scale over four NAMED criteria (bounded beats vibes), scores
  grounded in the encoded pakad/chalan/rasa facts, a code-computed pakad hint handed to the
  judge, and reasoning-FIRST so each number is justified before it's committed. *Line:* "We
  didn't tell it 'be objective' — we gave it a rubric, a fact to anchor on, and made it show
  its work per criterion."
- **Ground the judge in a FACT: the code-computed pakad hint.** Whether the raga's signature
  phrase appears *literally* in the lead is checkable, so code computes it and hands it to
  Rasik — who then judges whether it's present *in spirit* when not literal. *Line:* "We don't
  ask the judge 'is the pakad there?' cold. We tell it 'the phrase d-n-P-m appears literally at
  beat 8' and ask it to judge whether that's used with soul." Code supplies the fact, the LLM
  supplies the taste — the project thesis, inside a single agent.
- **The discipline is visible when the score is HONEST, not flattering.** In the live check the
  demo was only drone + lead (no rhythm section), and Rasik scored coherence 3, not 5 — and its
  note said exactly why (add a mid-register rhythm section; let the lead linger with andolan on
  komal ga/dha). *Talk beat:* a critic that dings its own demo is the proof the rubric bites —
  and it sets up the money moment: a piece Ustad passes as legal, Rasik still marks as lifeless.
- **Rasik scores ONE piece, so the position-swap countermeasure doesn't apply here.** Worth
  saying out loud: swap-the-order is for A/B *comparisons* (it belongs to the Conductor's later
  tie-breaks), not single-item scoring. Naming which bias fix applies where is itself the lesson.

### Phase 2, agent #6 — the Conductor (the money moment) — 2026-07-11

- **The debate only fires when code CAN'T decide — that's the whole point.** Triage first, in
  plain code: illegal ⇒ forced revise (no debate — legality is non-negotiable); legal + Rasik
  happy ⇒ accept (no debate); legal + Rasik flags a weakness ⇒ THIS is the one genuine
  judgment call, so THIS is the only case that spends an LLM debate. *Line:* "We don't debate
  what code already knows. The model argues exactly one question — the one with no right
  answer: is this legal-but-imperfect piece good enough, or worth another pass?" (Also the cost
  story: the expensive multi-agent debate is gated behind a free deterministic check.)
- **A debate needs a referee AND a clock — never organic consensus.** The Ustad↔Rasik exchange
  is a we-own-it bounded loop (Rasik opens, they alternate), capped at `MAX_ROUNDS`, and the
  Conductor ALWAYS rules at the cap. *Line:* "Two adversarial agents will never agree — they're
  designed not to. So you don't wait for agreement; you put a referee on a clock." This is the
  live-safety property made into a teaching beat: the terminator is in code, not in the model's
  goodwill.
- **The live debate was genuinely good theatre — and in-character.** On a legal Darbari piece
  Rasik marked weak on idiom: Rasik argued "it lacks the oscillating andolan on komal ga and
  dha… it's merely a flat minor scale"; Ustad argued "grammatically flawless, it executes the
  vakra phrases d-n-P and g-m-R-S with precision — a revision risks breaking that." The
  Conductor ruled REVISE the lead, with a surgical directive: "dwell on komal ga and dha,
  emphasize the andolan." Both critics cited REAL encoded Darbari facts — the grounding from
  the critics step paid off in the debate. *Demo beat:* this is the slide to land on.
- **The ruling is SURGICAL by contract — one layer, one reason.** The Conductor can't say
  "make it better"; `ConductorRuling` carries a single `layer` and an actionable `reason`, so
  the revise (step 6b) regenerates just that voice and leaves the rest. *Line:* "A good critic
  doesn't send you back to the drawing board — it points at one thing." The contract enforces it.
- **Symmetry worth drawing on one slide:** composers COLLABORATE-debate to CREATE (opposed
  emphases, shared goal, ends by agreement-or-cap); critics ADVERSARIALLY-debate to JUDGE
  (opposed verdicts, a referee, ends by cap-and-ruling). Same "bounded loop we own", but the
  critic loop adds the new element — a decision-maker. Two debate patterns, one framework.

### Phase 2, the Flow — the whole pipeline, one bounded loop — 2026-07-12

- **The loop lives in CODE, not in the model's goodwill.** CrewAI Flows have NO built-in loop
  cap — a documented footgun; a flow CAN spin forever. Our `@router` reads `state.round` and
  returns "done" the moment the cap is hit, so propose→critique→revise can revise at most
  `MAX_ROUNDS` times and then renders whatever it has. *Line:* "The framework will happily loop
  forever. The terminator is one line of your code, not a hope that the agents settle." This is
  THE live-safety slide — on stage you can't afford a loop that won't stop.
- **Surgical revise: regenerate ONE voice, not the whole piece.** On a `revise` ruling we
  rebuild only the flagged layer, and we thread the Conductor's directive into that voice's
  section `intent` so the re-run actually addresses the critique — then the deterministic voices
  (bass/drums/tabla/drone) re-derive around it for free. *Line:* "A revise isn't 'do it all
  again' — it's 'redo the lead, keep everything else', and the critic's note becomes the new
  brief for that one voice." Cheap, fast, and legible.
- **A real CrewAI gotcha, worth 30 seconds on stage: cyclic re-entry needs a ROUTER LABEL.** A
  plain `@listen(or_(begin, revise))` fires exactly ONCE — the second time round the revise
  step completes, the listener does NOT re-fire, so the loop silently dies after one pass. The
  fix: the loop-back must be re-emitted by a `@router` as a LABEL (`revise_layer` returns
  "recritique"), because CrewAI only re-arms an `or_()` listener for a repeat when a router
  re-emits a label it listens to. *Lesson:* in a framework, "it ran once" is not "it loops" —
  test the SECOND iteration, and read the runtime source when the docs are silent (they are).
- **The Flow is fully tested with NO LLM — because the pipeline steps are INJECTED.** Every
  stage (interpret, compose, generate, critique, arbitrate, regenerate, render) arrives as a
  `Stages` bundle; production wires the real agents, tests wire fakes. So the orchestration —
  routing, the round cap, "does an accept skip the revise", "does always-revise stop at the
  cap" — is verified free and fast, and only the end-to-end wiring needs a (single) live run.
  *Line:* "Separate the ORCHESTRATION from the WORK and you can unit-test a multi-agent flow
  with zero API calls." The dependency-injection payoff, made concrete.
- **It actually runs end to end.** One fixed chart → 6 LLM calls (lead, riff, Ustad, Rasik,
  Conductor) → a rendered WAV, with the whole debate streamed as events. `compose_flow(query)`
  is the one call that turns a sentence into Hindustani-metal audio through the entire crew.

### Phase 2, the audio-review pass — generation quality + meend realism — 2026-07-12

- **A critique loop is only as good as the GENERATOR's ability to act on the directive.** The lead
  was writing a straight scale run, not a raga taan — and Rasik CAUGHT it exactly ("the scalar run
  dilutes the raga; use vakra phrasing, andolan on komal g/d"), the very thing an external Gemini
  review said independently. But the music didn't improve, because the generator had no vocabulary
  to compose an idiomatic taan. *Line:* "Your judge can be completely right and the music still
  won't get better — a critique the generator can't act on fixes nothing." The fix was on the
  GENERATION side, not the critic.
- **`phrase_plan` — reasoning-first made STRUCTURAL.** Rather than ask the lead to 'plan first' in
  prose, the schema REQUIRES a `phrase_plan` (seed → contour → transformations → climax) ORDERED
  BEFORE the notes, so on native controlled generation the model literally cannot emit a note
  without first committing to an idea and how it develops. Same move as Ustad having no verdict
  field: *don't ask the model to be disciplined — make the schema enforce the discipline.* It turned
  a random scale into a pakad-derived, developed taan.
- **The loop is SYMBOLIC — no agent hears the audio — so timbre and gesture bugs are INVISIBLE to
  the critics.** All three critics passed a meend that sounded out of tune, because they read swaras
  and metrics, not sound. *Line:* "Your critics judge the score, not the recording — so a whole
  class of bugs (mix, timbre, the feel of an ornament) can only be caught by ear and fixed in
  deterministic code." An honest marker of where the agent layer's competence ends.
- **Measure, don't guess — and be willing to be wrong twice.** The out-of-tune meend drew two
  confident wrong diagnoses (the pitch-bend range, then the buzzy sitar sample) — each KILLED by
  measurement: a pitch-contour trace showed the notes landed dead on the swara, and the observation
  "it's bad on EVERY instrument" reframed it from timbre to gesture. The real cause was a slow
  linear glide dwelling on the micro-pitches; the fix was a fast, eased pull anchored on the target —
  one constant plus a curve, no new soundfont or renderer. *Line:* "I was wrong twice; the WAV wasn't."

### Phase 2, the studio session — bounded cooperative collaboration — 2026-07-13

- **A SECOND named multi-agent pattern — the mirror of the debate.** Beside the critique loop
  (adversarial: critics argue, a referee rules) the band now COOPERATES: the two creative voices build
  each section together on a shared blackboard (a `SectionCanvas`) — the leader proposes, the follower
  answers what it hears, then bounded refines. *Line:* "Same guarantees — bounded, refereed by code —
  opposite social dynamic: the critics argue to JUDGE, the band listens to CREATE." The talk now has two
  money moments: the band cooperates (build), then the critics debate (argue).
- **Code is the bandleader and the clock — never the agents.** WHO leads a section is a code rule keyed to
  its kind (the riff opens a groove, the sitar opens an alaap), and WHEN the session stops is a fixed turn
  budget — so the collaboration is stage-repeatable and always terminates. *Line:* "Real jams are emergent;
  a live demo can't be. We make 'who leads' an explicit convention in code and keep the collaborative FEEL —
  what the audience hears is the cross-voice RESPONSE, not a random opener." This is orchestrated L2/L3, not
  the autonomous L4 where agents pick their own turn order and quit when they feel like it.
- **The whole COLLABORATION is unit-tested with ZERO LLM calls.** The loop is pure and the note-writing is
  injected, exactly like the Flow's `Stages` — so turn order, termination, cross-section memory, and even the
  reprise of a returning hook are verified free. *Line:* "You can unit-test a multi-agent collaboration —
  who leads, when it stops, what each voice remembers — without spending a cent."
- **The critique loop nearly ATE the collaboration (the sharpest lesson).** First wiring: the initial
  generation was cooperative, but a surgical revise regenerated the flagged voice in ISOLATION — so on a
  piece the Producer sent back twice, the lead the audience finally heard was composed BLIND, the
  collaboration silently overwritten. *Line:* "It's not enough to collaborate ONCE; if your revise step
  throws away the shared context, the critique loop quietly un-does the very thing you built." The fix made
  the shared canvas FIRST-CLASS Flow state, so a revise is just another turn on the same canvas — the
  regenerated voice still hears the other. *Lesson:* cross-voice state has to LIVE somewhere durable, not be
  a transient the first pass discards. (Found by an actual live render, not by reasoning — hear-it-to-fix-it.)
- **One prompt, two modes — the A/B is free.** "No canvas / proposing" degrades cleanly to "compose solo /
  open the section," so the identical generator serves both the studio and the standalone path, and the
  studio is opt-in (`RMA_STUDIO=1`) with parallel still the default — so on stage you can flip between "the
  band composed in isolation" and "the band composed together" and let the room hear what collaboration
  actually changed.

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
