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

### Phase 2, gat development — evidence beats a converging review — 2026-07-15

- **Two reviewers agreed on a plausible mechanism; the artifact disagreed.** Sujit's ear
  and an independent Gemini review CONVERGED on "the riff is muddy because strict-raga
  chord stacking builds tritone power chords" — a mechanism so plausible we planned the
  session around it. Then we parsed the actual MIDI: 118 chord stacks, **110 octaves + 8
  perfect fifths, zero tritones**. The real culprits were measurable and boring: riff
  roots an octave below a real guitar (the LLM's local `oct:-1` sank past the register
  floor — 62% of onsets below D2), the mix CLIPPING at 0 dBFS, and bone-dry samples with
  no reverb send. *Lesson:* a critique loop that can't SEE the artifact converges on
  plausibility, not truth — ground the diagnosis in the artifact before you build the
  fix. (We now save the symbolic Composition JSON beside every WAV so this analysis is
  free next time.) *Line:* "Two smart reviewers agreed — and the MIDI file outvoted
  them both."

- **Feel → checkable constraint, three more times.** "The alap should breathe and come
  home to Sa", "the manjha should flow back into the head", "cut the mukhada and taan
  into the gap" — none of these survive as prompt vibes. Each became a deterministic
  verifier (`verify_intro` / `verify_manjha` / `verify_fill`) feeding the SAME bounded
  re-roll loop the mukhada already used (`_generate_verified_cell`) — the LLM composes,
  code measures, the re-roll tells it exactly what failed. The pause before the mukhada
  is the purest case: an LLM cannot emit silence reliably, so CODE reserves the gap by
  shortening the generation window. *Line:* "You can't prompt for silence — you have to
  own the clock."

- **The riff yields to the raga.** Cross-voice consonance (Sujit's ask): where the riff
  grinds a semitone/tritone under a HELD melody note, code strips its chord and clips it
  to a soft chug — turning the clash percussive. Crucially code never re-pitches: the
  accompaniment yields, the raga line is sacred, and no note is composed by code.
  *Line:* "Code edits the drummer's dynamics, never the singer's notes."

- **The verifier approved a cadence; placement cut it off.** First live run of the antara
  verifier: event says "re-rolled → clean" (the cell truly ended on Sa), but the rendered
  MIDI ends the antara on Re, clipped at exactly the window edge — the cell OVERRAN its
  window and the placement code truncated the approved ending. Two components, each correct
  in isolation, disagreeing about the artifact. Fix: end-anchored cells get a hard
  window-fill bound (ceiling ≈ 1.0 — overrun is fatal when the cadence IS the last note).
  *Lesson:* verify what the pipeline will actually PLACE, or bound the input so no later
  stage can change what was approved. *Line:* "The critic passed the take; the tape ran out."


- **The drum machine never read its own data (drum machine v2).** The subgenre profiles
  declared `blast_beats: True`, china/ride kits, gallop feels — and the groove engine
  ignored all of it: snare on 2 & 4, quarter hats, kick on 1 & 3, looped verbatim for
  whole sections. The audience-facing symptom was "the drums sound like a pop machine";
  the diagnosis was that the CODE never consumed the knowledge the DATA already encoded.
  The fix needed no agent: a research pass (real drum-education grids — skank, D-beat,
  three blast variants, the gallop cell — plus Logic Drummer's architecture: energy per
  section, fills as boundary properties, cymbal choice as a first-class input) became
  ~10 deterministic pattern builders and a tala-aware assembler. *Lesson:* before adding
  intelligence, check whether the system even USES the knowledge it has — "sounds
  robotic" was a data-plumbing bug, not a missing-LLM bug. *Line:* "The kit had blast
  beats in its spec — the drummer had just never read the spec."

- **"The riffs sound happy" — measure before you prompt (riff texture v1).** Sujit's ear
  said light/happy/hollow; a GPT review said "rewrite the prompt." The render's saved
  Composition JSON said something more precise: the piece was Yaman (the brightest raga on
  the menu — part of "happy" was the MENU PICK), the chord stacks were mostly bright
  add9/tenth colours rather than power weight, the line changed pitch 79% of the time (a
  melody wearing a riff's clothes — real metal riffs repeat one low note most of the time),
  and the slides/hammer-ons everyone missed WERE in the data — 76% of notes were marked
  palm-mute — but the renderer realized them so weakly they were inaudible. One complaint,
  four distinct causes in four different layers (menu, voicing, generation, render), and
  only the measurement could apportion blame. The generation fix reused the verify+re-roll
  pattern from the gat cells: translate the feel into budgets (ground share, pitch-change
  cap, colour ration, real silence) and re-roll with the exact violations. *Lesson:* when a
  critique is aesthetic, decompose it against evidence before touching anything — the
  prompt is rarely the only guilty layer. *Line:* "The model had written the slides all
  along; the renderer was swallowing them."

- **"Not catchy" was a geometry bug, not a taste bug (2026-07-20).** Sujit's feedback — the
  gats aren't memorable "like Vilayat Khan" — sounded like a prompt/taste problem. Research
  into the gharana's own pedagogy (Arvind Parikh's writings) showed the tradition had
  ENGINEERED catchiness centuries ago: the mukhda is a five-matra pickup landing ON the
  sam, and improvisation replaces the FRONT of the cycle while that approach stays
  sacrosanct. Our code did the exact opposite — the taan fill cut the BACK half of the
  head's avartan, deleting the hook's approach every time. One constant's semantics
  (`_FILL_FRACTION` back-half → `approach_cut` front-cut) carried more catchiness than any
  prompt rewrite could. The rest of the fix was the same encode-the-tradition move: the
  stroke grid as data (`src/gats.py`), the tihai as ARITHMETIC (phrase ×3 + 2 gaps == one
  avartan — counting is code's job, the phrase is the model's), the amad as a verified
  fourth line. *Lesson:* when a domain has a centuries-old craft, the craft IS the spec —
  research it and encode it as checkable geometry; don't ask the model to rediscover it.
  *Line:* "Vilayat Khan's catchiness was an algorithm all along — we just had it backwards."

- **We built the Debator pattern properly — and the evidence said "not yet" (2026-10-12).** The
  multi-agent-debate literature (Du et al. 2023; Liang et al. 2023; ChatEval) suggests composers
  that hear and argue with each other should beat one composer. We tested it fairly: SINGLE seed
  (1 call) vs BEST-OF-4 (6 calls) vs DEBATE (2 independent seeds, one round of argument over the
  notes AND code's measurements, an order-swapped selector — 6 calls), three prompts, rendered as
  short auditions, ranked BLIND by Sujit, twice. Result: debate beat best-of-4 3 times in 6 (a coin
  flip); the single seed scored the most points in BOTH rounds; and to Sujit's ear "all variants
  sound good enough". Three findings beat the headline: (1) the drafts barely differed (hooks up to
  83% alike, identical bol patterns) — debate needs DIVERSE starting ideas and the model writes the
  same hook four times; (2) the LLM judge flipped its choice when the order was swapped in 4 of 6
  selections — position bias, so code's tie-break chose most "winners"; (3) every debater revised
  toward the MEASURED numbers (riff-accent match 0% -> 100%) — show an agent a metric and it
  composes to the metric (Goodhart). Measuring the drafts then exposed the real ceiling: the
  PROMPTS were steering every seed (31/31 gat form, 23/31 the example's contour, 30/31 hooks
  opening on four one-beat notes — the "keyboard melody" Sujit heard). Decision (Sujit): keep the
  single Composer; revisit debate once the gat composition itself is rich enough to vary.
  *Lesson:* a pattern only helps when its premise holds — measure the premise (here: diverse
  candidates) before paying for the pattern. Agrees with Smit et al., ICML 2024 ("Should we be
  going MAD?"). *Line:* "Two composers arguing over the same idea is one composer with a bigger bill."

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

### The prompt that documented a bug (2026-09-14) — ★ a strong closing beat

The riffs sounded choppy. The critique loop never flagged it, and it couldn't have: the
renderer gated every palm-muted note to a fixed 80 ms regardless of the duration the agent
wrote, so a chug written for two beats played for 0.16 and left nearly a second of dead air.
Every verifier had already passed on a symbolic score that was fine.

The part worth the slide is what we had done about it earlier. Rather than fix the clamp, we
had written it into the riff prompt as a musical rule — *"a palm-muted note gates to a short
chunk whatever its written duration"* — so the agent dutifully composed AROUND a defect for
months, and its output looked correct to every check we had.

*The lesson, and it generalises past music:* **an agent's output is only as good as the
fidelity of whatever consumes it, and a prompt that documents your bug will make the model
reproduce it faithfully.** Three of the four things Sujit heard turned out to live downstream
of the last verifier — the clamp, a `real_pm` branch computed and never read (so every chug
fired twice on two channels), and channel-wide pitch bends rubber-banding 58% of the power
chords. No amount of critic intelligence reaches there. *Slide:* the deleted prompt line next
to the `PALM_MUTE_MS = 80` constant it was describing.

*Companion beat:* how we knew. Every render saves its symbolic composition JSON beside the
audio, so the diagnosis was measurement on a file we already had — gate ratios, gap
distributions, wheel-gestures-on-chords — and the fix was A/B'd by re-rendering that same
saved composition. Zero LLM calls to find or to verify a fault in an LLM pipeline.

### The rule that was backwards (2026-09-14) — ★ confirmed by ear

Sujit said the generated Bageshree gat didn't sound good, and sang me two he was learning:
`MaMa GaGa ReRe SaSa | Ni Dha NiNi Sa | Ga Ma — | Ma Ga Re Sa`, then sent Vilayat Khan's
notated Bageshree and Yaman gats. Measuring his against ours found the difference, and it was
not the notes — both lines were 50% stepwise, both sat in one octave, ours quoted the pakad and
landed on the vadi correctly.

**His gat used two note values, one covering 95% of the notes. Ours used five, the commonest
covering 31%.** A gat is sung and plucked: it moves at one pulse, with paired mizrab strokes
("dara") as its subdivision. You can clap it on a single pitch and still recognise it.

And our prompt was demanding the opposite, in as many words: *"MIX THE NOTE VALUES — at least
THREE distinct durations… A head of even values reads as a metronome and is rejected."* We had
written a rule that rejects the shape a real gat has. The instinct is right for a taan and
exactly wrong for the head.

Two more rules turned out tighter than the tradition in the same session. A vakra floor I tried
would have rejected a hand-written idiomatic phrase. And the sam-note rule — Sa, vadi or
samvadi — is refuted three times over by Sujit's own repertoire: Vilayat Khan's Yaman gat lands
its sam on Pa, a Bageshree bandish he is learning lands on Re (a swara our data marks
descent-only), another gat lands on Ma. That check is gone rather than widened, and its old
test is now its refutation, so nobody re-adds it from the docstring.

*The verdict, from the practitioner, on the next render:* **"intro and gat sound convincingly
Bageshree."** The head came back with three note values instead of five, the commonest covering
50%, and — unprompted — the paired strokes: `D D · P P · R R · S S`.

*The lesson, and it generalises past music:* **every one of those rules came from reasoning
about what the tradition "should" do, and every one was corrected by a real piece of it.** When
you encode a domain you do not practise, your rules will be confidently, plausibly, and
invisibly wrong until a practitioner hears the output. Build for that, and keep the refutation
as the test.

### The prompt that never reached the band (2026-10-11) — the lossy handoff

Sujit wrote a careful brief for the talk's opening piece: 60 seconds, Bhairav in E, teentaal
at 128, a tihai landing on the sam, the lead ending on upper Sa over a low-Sa hit, and a rhythm
part he could play live himself. Then he asked a simple question: *do the agents even see my
prompt?*

They did not. The Interpreter turned it into a structured brief, and every agent after it saw
only that brief. Five of his asks survived, because they matched a field: raga, key, tala,
tempo, subgenre. Everything else had nowhere to go, and one ask came out inverted: "I will play
rhythm guitar live" landed in `instruments`, which the composers are told to *honour*.

The fix is two channels for one intent. The structured brief stays: it is what code can
**enforce** (a legal raga, a real tala, a length in avartans). Next to it, the user's words now
travel **verbatim**, copied by code so nothing paraphrases them, to every agent that makes a
musical decision, each told what the words mean for its own job and what wins when they
disagree. And the asks that were really *capabilities*, a length, an ending, a playable riff,
became code: a form budget the guardrail checks, a final stroke the band lands together, and a
fretboard model that rejects a riff a human cannot play at 128 bpm.

*The lesson:* **a structured handoff is a compression, and a compression loses whatever the
schema did not anticipate.** Keep the schema for what you can check, and pass the original
intent alongside it for what you cannot.

### The decision nobody executed (2026-10-11) — a plan field the pipeline ignored

The composer agents make one big structural call for every piece: the **anchor**. Either the
sitar's gat is the source and the guitar riff is boiled down from it (`gat_first`), or the riff
is the source and the sitar's head sings its strong notes (`riff_first`). It sat in the
contract, the composers reasoned about it, and the trace showed them choosing `riff_first` with
care. Nothing downstream read it. The pipeline always composed the sitar first and told every
riff it was a reduction of the head, so half the composers' decisions were silently overruled
by the order of two lines of code.

The tempting fix was a prompt line: pass the anchor to the riff and say "you are the source".
That would have been a lie, because the gat it was supposedly seeding already existed. The real
fix was to let the decision change the *orchestration*: the source voice runs first, code reads
the riff's accented notes (the swaras on the sam and the claps), the gat is shown them, and a
verifier checks that the head actually sings at least half of them on the same beats.

*The lesson:* **an agent's decision only counts if something downstream changes because of it.**
Audit every field your planner emits and ask what reads it; a field nothing reads is a decision
the model is making for an audience of no one.

### The verifier that would have rejected the best riff (2026-10-11) — rules age

When the bare single call beat our pipeline on riffs, the obvious question was why our
carefully verified riffs were thin. The answer was in our own guardrail. The winning riff was a
half-step power-chord shuffle, Sa to komal re, E5 to F5, the darkest move a raga riff has. Our
verifier required 55% of notes on one ground pitch (it had 48%) and capped pitch changes at 55%
(it changed root on 82% of strokes). It would have been rejected twice, re-rolled, and replaced
with something more like what we shipped: 71% single chugs on Sa.

Those thresholds were not careless. They were calibrated in July on real failures, when the model
wrote busy low melodies and called them riffs. But the model moved on (requests now appear to be
served by a newer Flash) and the rules did not. We tried to replace the cap with a smarter
statistic and the data refused: on four real renders, no pitch measure separated a riff from a
melody. So the rule stopped being a rule. Code now rejects only what is physical (a palm mute
cannot sustain, a chord cannot bend, the loop must land on the sam) and everything about taste is
reported to a judge.

*The lesson:* **a guardrail calibrated against a model's weakness becomes a ceiling when the model
improves.** Keep hard checks for what is actually true about the world, and re-baseline the rest
against a single unconstrained call every time the model changes.

### Deleting agents (2026-10-11) — the decomposition was the bug

We spent months adding agents: a composer dialogue, a gat composer, a lead, a riff, a studio
session, three critics, a debate, a conductor, an arranger. Then one bare model call, asked for a
one-minute song, wrote a better riff than the whole system. Not better raga (it broke the raga 92
times), but better metal: power chords on every stroke, a half-step shuffle, a climax that grew.

Measuring why took an afternoon and every answer pointed the same way. The riff, the hook and the
form are one idea, and we had split them across agents that never shared a context. Our verifiers
were tuned to an older model's failures and now rejected the best riff we had. Our critics debated
two opinions that were already on the table, then accepted the weaker song. An agent narrated a
verdict that code had already computed.

So the redesign removed more than it added: one Composer owns the music, code owns only what is
genuinely true (the raga's notes, the loop, the physics of a guitar), one judge decides, and a
second judge — the ear — is measured before it is trusted.

*The lesson:* **split agents where the information or the judgment genuinely differs, never where
the job titles differ.** And keep a single unconstrained call as your control: the day it beats
your system, your decomposition is the bug.

### The fact we only told the model (2026-10-12) — knowledge that never reached the sound

An outside review of a Darbari render (GPT, reading the MIDI) said the hook "sounds like metal
using Darbari's notes, not Darbari": the komal Ga and Dha were short and bare, and the climax bent
every note the same way. Checking it against our own data was humbling. The raga file already
says how Darbari's Ga is approached (a touch of Re rising, of Ma falling) and warns that "a
straight g/d turns it into plain Asavari". That fact was correct, sourced and encoded, and it
went exactly one place: a sentence in the lead prompt, which the model mostly ignored. The bends
were worse, because they were ours. A code pass gave every climax note the same up-shake,
including the two swaras the raga defines by their slow sway.

Code now applies the approach from the data on every held Ga and Dha, keeps the climax shake off
the swaras that sway, and places the tihai's last note on the sam, which is arithmetic, not taste.

*The lesson:* **knowledge in your data is not knowledge in your output until something applies
it.** If a fact is deterministic, telling a model about it is a hope, not a mechanism. Trace each
fact to the place where it acts on the output, and when no such place exists, give it one.

## 2026-10-18 — what measuring taught us (talk-gold)

### The baseline moved: 92 wrong notes became zero
The experiment slide's headline was "one bare prompt, 92 wrong notes" (gemini-3.5, 2026-10-11).
Re-run on gemini-3.8 for Bhairav, Yaman and Darbari, the bare call plays **no** forbidden notes in
two of three ragas (4 in Darbari's guitar). The model learned the notes. What it still cannot do is
the raga: Rasik scores its mood 2-3 against the system's 4; it shreds in straight runs of 9-13
notes; it missed Bhairav's "G m d d P" pakad entirely ("Bhairav's pitch set treated as a Western
double-harmonic scale"). *The lesson:* **re-baseline your control on every model change** — a
headline about the model's weakness can expire in a week.

### Correct is not good — nine songs, measured
Three ragas × A (bare) / B (bare + the raga's rules) / C (the system). B made every pakad exact and
shortened the scale runs — and its mood score did not move (Rasik on Bhairav B: "a Byzantine
scale exercise"). C won the musical measures that are fair to compare: power chords on 81-100% of
guitar strokes (21-33% bare), the opening idea returning three times (0-2), all four parts ending
on the same beat (bare: up to 31 beats apart), mood 4 (2-3), and the only sway on Bhairav's re and
dha. *The lesson:* knowledge buys correctness; structure and ownership buy music.

### Our own prompt made the bare call look worse
The bare prompt said "with every part playing for the whole length" — meant to align the parts'
lengths, read by the model as "never stop". Two of our headline findings about the bare call
("every part plays every bar", "never breathes") are partly that sentence. *The lesson:* before
blaming the model, read your own prompt as the model reads it.

### A judge optimises whatever you show it
The seed debate (two composers argue, a judge picks) ran a third blind round. Every debate turn
rewrote about half the notes and most of the rhythm, and the arguments quoted our measurements:
"the rival correctly introduced authentic compound strokes … a recognizable stroke motif". Sujit's
ear: in Darbari the untouched single seed won — "more weight, the real character of Darbari"; in
Bhairav the debate won, where its revision happened to ADD breathing space. Across four blind rounds
debate is not reliably better than one composer. GPT's review named it: *correlated revision* —
two copies of one model, same facts, same numbers, converging on what is measurable. *The lesson:*
**if a judge or a critic can see a number, it will optimise the number.** Show the notes first; the
numbers only to check a concern.

### Code that applies a fact can be wrong, too
We moved raga facts out of prompts into code so they would always apply. Then code applied one
sway rule ("swing half way to the neighbour") to every raga: right for Darbari, a wrong note for
Bageshree (+98 cents, three times in 20 s), and for Bhairav a swing down onto pitch the raga does not
own. A research pass (Parrikar, Ragajunglism, and van der Meer & Rao's measurement of a real
Bhairav performance: the dha's whole movement inside ~32 cents, approached from above) gave the
right shape. *The lesson:* a generic rule reused across domains is a bug waiting for the second
domain — test each fact per case, and measure the output (we now audit the rendered pitch).

### Our harness lied twice in one day
A test summary counted lines containing "passed" and hid three failing tests; an experiment
auditioned the composer's sketched gat heads instead of the composed ones. *The lesson:* verify the
verification — check each file's x/y, check what an experiment actually played.

### Every pattern has a precondition (the slide this talk needs)
| Pattern | It needs | What we found |
|---|---|---|
| Debate | different information + a trustworthy judge | same model, same facts; rewrote, chased numbers |
| Role per job | separable work | riff, hook and form are one idea — one call beat eleven agents |
| Collaboration (shared canvas) | two equal owners | one owner did better |
| Sequential handoff | the next agent must see the finished work | works: the guitar answers the sitar |
| Plan → execute | a plan worth committing to | works: the hook returns, the form holds |
| Evaluator–optimiser | a critic that predicts the listener | unmeasured; 40% of the calls; anchors on numbers |
| Guardrails | a rule that is actually true | zero illegal notes; fake rules rejected the best riff |
| Tool use / ReAct | a tool that tells the model something new | Ustad's tool only narrated code's verdict |
| Human in the loop | a judge you trust | the ear decided every experiment |
*The line:* don't ask "which pattern is most advanced?", ask "what does it need, and does my problem
have it?" The patterns that survived are the plain ones.

### Human in the loop — the strongest pattern here (say it, don't build it)
Ground truth in this system is a listener. Every LLM judge we tried (the Seed judge, the Producer,
the debate) was a prediction of that listener, and each time Sujit's blind ranking was the deciding
evidence. The cheapest high-value design is a human at the one decision that matters most — pick
between two genuinely different seeds in under a minute — and machines everywhere checkable. On
stage: "the most advanced agent in this system is the person in the room; the architecture's job is
to spend that attention only where it counts."

### What the nine songs say to change (for the next build)
Breathing must be PLANNED (the system's Bhairav never drops a part); the raga's defining notes need
room (Darbari's ga and dha held 0 of 47 times, so never swayed); the energy arc should reach the
dynamics (the flattest velocities of all nine songs). Next session tries two patterns whose
preconditions this problem HAS: ReAct with tools that report what the model cannot see (does this
phrase linger on a wrong pitch? did I hold Darbari's ga long enough to sway?), and a challenger that
proposes one bounded alternative and never replaces the original.

### ReAct needs a tool that tells the agent something it can ACT on (2026-10-18, built)
The obvious first tool was "audit the ornaments: does a bend linger on a wrong pitch?". Reading the
code killed it: every ornament the audit checks (sway, kan, gestures, shruti) is stamped by CODE
after the model answers, so the agent would be told about faults it cannot fix — and since the
October fixes the answer is almost always "clean", a paid round trip that buys nothing. The tool
that earns its call reports the CONSEQUENCES of the agent's own choices that it cannot see: "your
0.5-beat Ga plays plain — too short to sway", "this Ga takes guruji's loop to Ma", "your draft runs
19 beats; the last 3 are cut". So the rule for a ReAct tool: it must return something the agent
(a) cannot compute itself and (b) can change. And it reports what WILL HAPPEN, never a score — a
judge optimises whatever number you show it, and a composer told "1 of 5 sway" would hold every Ga.
Second, quieter lesson: attaching a tool silently switched CrewAI off native structured output for
the whole call (the answer comes back as text the guardrail must parse). A pattern changes the
plumbing under it; read the framework before the first live call.

**The first live A/B (same call, same inputs, n=1):** without the tool, the Composer put a gamak on
8 of its 14 notes and never held Darbari's ga or dha. With it, the first draft held ga and dha one
beat each; the tool answered "0.47 s is too short to sway at this tempo"; the model rewrote both as
two-beat holds, listened again, and answered. Cost: 3 calls instead of 1, ~5x the input tokens,
~3x the time. That is ReAct earning its keep: the change it made is exactly the one the tool exposed.

**The fresh A/B (seeds stripped) and Sujit's ear: A (no tool) wins.** The first A/B was confounded:
song C's seed hook rode the prompt, so both were editing an old melody. From scratch, A wrote
Darbari's own cadence (`m P g~ m R S`) unaided; B fixed everything the tool reported and lost the
cadence. ReAct WORKED — the agent changed exactly what the tool showed it — and that is the lesson:
a tool decides what the agent pays attention to. Point it at a minor, measurable property and you
get a better score on that property and a worse piece. The same law as the judges: an agent
optimises whatever you show it, whether a judge's number or a tool's report.

### We skipped the baseline (found 2026-10-18 in the git history)
Day one (2026-07-11) went straight to agents: the "naive strawman" in the July talk plan ("in scale
but soulless, or worse, breaks the raga") was an EXPECTATION, never measured; the "naive" clip in
`src/demo.py` was a hand-written riff with one forbidden note swapped in; the earliest of 77 traces is
already a composer-agent run. The first real plain-prompt test came three months later (2026-10-11,
`talk/audio/pure_songs.py`): Gemini wrote legal, fluent melodies unaided, and its band-level riffs beat
ours (despite 92 forbidden guitar notes). The honest Act 1 opening is "we designed eleven agents
before measuring one prompt" — the lesson: measure the single call first, keep it as your control.

### The judge's own edit made the piece worse, by its own score (2026-10-18)
High-effort run (`talk/audio/high_effort.py`, trace 57af304fd1ad; Composer + judges at HIGH): the first
draft scored 5/4 across the board; the Producer asked for ONE edit (a mandra dip at the cadence); the
edited version scored LOWER on its own rubric (repetition 4 -> 3) and its next plan asked to undo the
repetition its edit introduced; the stop rule ended the loop and shipped the worse version. High effort
cost 4x the thinking (119k vs 30k) and 2.3x the time (14.5 vs 6.2 min) for one measurable gain: Ga/Dha
held long enough to sway, 0 -> 4. Blind pair for Sujit: `out/blind_producer_20261018_165129/`.
**Sujit's blind ear (same day): Y — the FIRST DRAFT — "clearly better"; X (the Producer's edit, shipped)
"had issues in rhythm and towards the end sounded off".** The ear agrees with the judge's own score drop,
and the fault sits exactly where the edit landed (section 4's cadence). The loop shipped the version
its own judge rated worse because the stop rule ships the LATEST, not the best. Lesson: an
evaluator-optimiser loop needs a keep-the-best rule, or the loop can only add risk.

### The Producer, measured across every run (2026-10-18; `talk/audio/producer_analysis_20261018.json`)
39 of 79 traces carry Producer verdicts; 14 runs had the accept/revise decision. It REVISED THE FIRST
DRAFT 14 OF 14 TIMES (notes praising "superb… fantastic energy", then revising one phrase). 30 of 36
plans copied a Rasik suggestion near-verbatim; 30 of 36 prescribed swaras; all 36 targeted the lead.
87% of its scores are 4 or 5 (round means 3.2-4.4); after an edit the mean went up 10 times, down 9,
flat 5 — a coin flip — and criteria an edit could not touch (mood_fit, structure, balance) moved
anyway: noise. 6 of 14 runs shipped a version below one of its own earlier rounds. 15 of 22 follow-up
plans re-targeted the sections it had just edited. Each reasoning cited ~11 numbers. The one blind ear
test (57af304fd1ad) preferred the first draft. Verdict: it was a relay for Rasik's notes with a revise
reflex and a noisy scale, not a judge.

### The rival added nothing; the measurement did everything (2026-10-19, the head-debate control)

**The experiment.** The head debate (out/head_debate_20261018_234135, trace `924cad7451fd`) let two
composers argue over their gat heads for up to four rounds — each starting from a different
approach (A: weight, B: rhythm), each seeing both heads plus code's measurements. In round 1 both
moved into the mandra and added Darbari's `d n P` cell; in round 2 both kept. It looked like the
debate worked. The CONTROL (out/head_control_20261019_000558, trace `c0e7320909c6`) re-ran it with
the same proposals A0/B0, the same approaches and measurements, and NO rival: each composer saw
only its own head and code's numbers.

**The result.** Without a rival, both made the same move in one revision and then kept, exactly as
the debaters did. Solo A landed at 44% below Sa — the identical figure debate A reached. The two
solo heads ended LESS alike than the two debated ones (swara similarity 0.40 vs 0.53): the debate
pulled the composers toward each other, not toward better music. Cost: 5 calls / 89k tokens for
the control vs 12 calls / 184k for the debate.

**The real finding — a stated fact is ignored; a measured fault is acted on.** Every first-draft
prompt said, in plain words, *"DWELL below home Sa (octave -1), do not just touch it"* — and approach
A added "open low". Across TEN first drafts (A0, B0 and the eight heads of the motif experiment) the
most any spent below Sa was 19%; the median was under 5%. One measurement of the composer's OWN
draft ("mandra 0%") moved four of four revisions to 31-94%. That is self-correction from code —
CRITIC's result (tool feedback works) — but for a craft fact, not a legality rule.

**The failure inside the success.** Solo B chased the number: 94% below Sa, the whole head an
octave down, the madhya gone. The measure was one-sided ("how much below Sa?"), so the fix
overshot into the opposite fault. The debate's B landed at 31% — maybe the rival moderated it, n=1
can't say. Lesson: a number shown without its band becomes a target (the same thing the seed
judges did with our measurements).

**And a bug the replay caught before production.** The first keep-rule measured the PAKAD whole. A
7-9 note pakad rarely fits one head, so the best revision (A: both `g m R S` and `d n P`) read as
"pakad lost" and was rejected, while solo B (pakad sung whole in the mandra) read as "pakad
gained" and was kept — exactly backwards. Replaying the six real heads through the rule before
wiring it found it; measuring pakad OR chalan phrases fixed it.

**The decision (built).** Debate stays parked — this is its fourth failure, and the first with a
control proving the rival contributes nothing the measurement doesn't. Instead the production gat
head gets ONE measured self-revision (`crew/head_report.py` + `crew/head_revision.py`, flag
`RMA_HEAD_REVISE`, default ON): code measures the head against the facts its prompt already
states (where the raga LIVES — each saptak it lives in ≥20% of the head; one pakad/chalan phrase;
in a vilambit gat a held andolit swara long enough to sway); a head that meets them never reaches
the model; one that misses gets one revision pass; code KEEPS the revision only when it passes the
head's hard checks, keeps the first note, and fixes a missed fact without missing one the draft
met. Replayed on the real heads it keeps A (both runs) and debate B, and reverts solo B's
overshoot. +1 call only when a fact is missed. Live-untested in the pipeline.

**For the talk.** "We gave the model a sparring partner. It turned out the sparring partner was
the ruler we handed it." The debate slide's honest evidence line: *same move, half the cost,
without the rival.*

### The rehearsal — a band that hears, tries, and has a leader (2026-10-19, first live run)

Built because Sujit asked why debate fails when real bands argue their way to better music. A
real argument works because the members hear differently, argue over ONE song, and settle it by
playing. `crew/rehearsal.py` + `crew/rehearsal_edits.py`: a sitarist (Vilayat Khan, Shahid Parvez),
a guitarist (Metallica … Slayer, Megadeth) and a drummer (Lombardo, Hoglan, Cavalera, McBrain,
Zakir Hussain) each HEAR the mix plus their own part solo (their "monitor"), propose at most one
change from a rehearsal vocabulary code plays for free (sit out / louder / softer / sparser /
cut / repeat), hear each other's changes before→after and argue; a bandleader fluent in BOTH
Hindustani and Western theory (Sujit's requirement; proposes nothing) hears every before→after
and decides. Run: out/rehearsal_20261019_075624 on fusion_20261013_074703 (Darbari doom, 160 s),
14 Gemini Pro audio calls, ~15 s each, two rounds.

**What it did that no debate did.** It argued about the ARRANGEMENT and the RIFF — the first time
the guitars were ever on the table. Round 1: all three heard the same fault (busy guitars burying
the sitar's taan at 1:52) and proposed different fixes (sparser / sit out / sparser); the
bandleader chose the drastic one (guitars out under the taan, an Opeth-style dip). Round 2
diverged: sparser guitars in the antara (sitarist), in the manjha (guitarist), and **drums out of
the intro** (drummer) — "a proper alap" in the sitarist's words. Traditional practice agrees (an
alap has no percussion), but Sujit's ear overruled it for this band: the drums under our intro are a
BUILDUP, and he wants them kept — now a house rule every member is shown.

**What it did not fix.** 12 of 12 reactions were "support", including the guitarist voting to
remove his own guitars. No one pushed back: an agreeable band, the same-model failure in a new
room. And there is no proof they LISTENED rather than read the map: every claim lines up with the
section map they were given (the listening pass is score-blind for exactly this reason).

**Measurement disagrees with the intent.** "Sparser" was meant to give the sitar space, yet the
manjha and antara came out ~1.2 dB LOUDER relative to the rest: ringing, un-muted distorted chords
fill more continuously than palm-muted chugs. And with the guitars out, the climax taan is now
~1 dB quieter than its neighbours — the band traded the climax for a dip (our design had the climax
riff at full density). Whether that is better is an ear question; ear verdict pending.

**Next, if it earns it:** blind the reactions (before/after in random order, labelled X/Y, no
"why") so agreement must come from hearing; give each member a stake ("your part must survive");
and fix "sparser" to ring SOFTER, not just longer.

**Sujit's ear (same day).** Liked the sparser guitars in the manjha and antara. The guitars sitting
out under the taan: "debatable — could have done chugs only". No drums in the intro: either is fine
(with drums it was a buildup). So of the bandleader's four kept changes: two liked, one neutral, one
debatable — the closest any model judge has come to his ear. And the debatable one exposes the
lesson: the band could only choose from the menu we gave it, and Sujit's answer ("chugs only")
wasn't on the menu. A rehearsal is only as good as the moves it is allowed to try.

**Acted on (same day, Sujit: "do the changes").** (1) The rhythm-section brief (`compose_rhythm_section`)
now plays the manjha and antara SPARSE — one ringing stroke per vibhag, a little softer than the
head's drive (the rehearsal also showed ringing chords left loud fill the room). The taan line was
already "full drive on a home pedal" — Sujit's "chugs only". (2) The rehearsal menu gained `chug`:
keep the rhythm, every stroke a palm-muted low Sa. (3) House rule shown to the band: a drum buildup
under the intro is welcome; don't propose dropping it.

### The alap that only asked questions (2026-10-19, Sujit's ear on fusion_20261019_083259_fresh)

"The alap phrases don't halt on nyas; they end leaving tension; it never builds and resolves; it
feels random; the pacing is off — as an intro it should have a pulse, like a jod." Measured: four
phrases resting on Re, Re, Pa, Sa — two of them CLIMBING into their last note — and 11 of 30 notes
starting between beats, one phrase entering mid-vibhag. Root cause was ours, twice over: the July
brief said "every earlier phrase keeps its tension, only the last resolves" — written when a
code-plucked low Sa (the jod string) supplied home between phrases — and on 2026-10-12 we deleted
that pluck but left the prompt telling the composer "don't pluck mandra Sa yourself, code does it".
Home was forbidden by the prompt and removed from the code. A rule's justification can be deleted
while the rule survives.

Sujit's rules, now built (`crew/config/lead_roles.yaml` intro brief + `gat_verifier._intro_call_and_answer`,
`_intro_pulse_violations`, `lead.intro_phrase_grid`): CALL AND ANSWER — a call does NOT rest on a
nyas, it stops on a tension note off the raga's CORE nyas (Darbari: a held komal Ga or Dha); an
answer resolves onto a core nyas, falling or turning; calls may pile up (a longer call, or several
in a row) before the answer; the close is a held Sa. ON A JOD'S PULSE — phrases start on a vibhag,
notes of a beat or more on a beat, long swaras re-struck rather than held. Code enforces: at least
one call before the close, phrases on the vibhag, long notes on the beat (hard, one retry); an answer
climbing into its nyas is reported. Defined against the CORE nyas because in Malkauns every swara is
a permitted rest — "off every nyas" would have left calls nowhere to stop. The first live retry:
two phrases started off the vibhag, code named the beats, the second draft fixed them.

### The rehearsal's ears were not listening (2026-10-19, second rehearsal)

Two members, three rounds, on the fresh song. Both members opened by proposing the same fix — "chugs
under the taan, the moving chords clash" — and later "the busy riffs smother the antara". Measured on
the song itself: the guitar was ALREADY 76% palm-muted chugs under the taan, and already sparse in the
antara (1.4 strokes per vibhag, notes nearly 3 beats long — the new brief working). The complaints were
about a song that wasn't playing. The final check settled it: in one order the bandleader described
the ORIGINAL as having no guitars under the taan and heard "synthesizer runs"; in the other it heard
the two versions as identical. Split verdict, so the original was kept — the safeguard did its job.

The lesson: a rehearsal is only as good as its ears. The audio model's descriptions track the section
map and the personas' priors, not the sound. Until a model can hear a before/after difference a human
hears (the listening pass's own rule: calibrate against Sujit's blind ranking first), the rehearsal's
proposals are guesses with a confident voice — and the cheap guard that caught it is the same one as
the Producer's: the revision must beat the original, both orders, blind.

**Sujit's ear on rehearsal #2:** "r0 (the original) feels better than r3 — r3 feels hollow in places
because of the lack of guitars." The final check was right to keep the original. Across BOTH
rehearsals almost every kept change SUBTRACTED (guitars out of the taan / manjha, softer in every
mukhada, bass out) — each reasonable alone ("give the sitar space"), unanimous every time, hollow
once stacked. The framing (personas + map) made "the sitar is buried" the default diagnosis and
removing guitar the default cure; deaf ears meant nothing pushed back. Rehearsal PARKED until an audio
model passes calibration against Sujit's blind ranking; its two good ideas live on as plain rules
(sparse manjha/antara in the rhythm-section brief; chugs under the taan).

## 2026-10-19 — what the day taught (talk-gold, one line of evidence each)

1. **A rule you state gets ignored; a fault you measure on the model's OWN draft gets fixed.** Ten gat
   heads were told "dwell below Sa" — none did (max 19%). Shown "mandra 0%" about its own draft, four
   of four moved (31-94%). The alap the same day: told "start on the vibhag", the first draft didn't;
   code named the beats, the retry did. → self-correction from code works for CRAFT, not only legality.
2. **The rival added nothing the ruler didn't.** Head debate vs its control (same proposals, same
   measurements, no rival): the same move, half the tokens, and the debated heads ended MORE alike. Four
   debate designs, four parks — each time for the same three gaps: one mind twice, nobody can hear, a
   judge who can't hear either.
3. **A number shown without its range becomes a target.** One composer chased "0% below Sa" to 94% and
   lost the madhya. Fix: keep a revision only if it fixes a missed fact WITHOUT breaking one the draft
   met — and replay the rule on real data first (our first keep-rule judged exactly backwards).
4. **The menu bounds the debate.** A rehearsal whose only moves were knobs (sit out, softer, sparser)
   argued only about volume — every kept change subtracted guitar, unanimously, and the song went hollow
   (Sujit: "r3 hollow, lack of guitars"). The answer he wanted ("chugs only") wasn't on the menu. →
   rebuilt as a NOTES debate: each player rewrites notes of its own part.
5. **Audio models describe the map, not the sound.** The band complained of busy guitars that measured
   sparse, heard "synthesizer runs", and called two different mixes identical. The blind both-orders
   final check caught it and kept the original — the same guard as the reworked Producer. Calibrate
   ears against a human before they get a vote.
6. **An agent with no part to defend adds noise.** The drummer (drums are code) proposed nothing Sujit
   liked; dropped. Split agents where the information or the stake differs.
7. **A deleted mechanism can leave its rule behind.** The jod string was deleted on 10-12; the prompt
   still forbade the composer to play home "because code does it" — the alap became all questions.
   When code goes, grep the prompts and the checks for what relied on it.
8. **Tests can encode the old design.** Reworking the alap, the "good alap" fixtures were the July shape
   and failed the new rules — and the new pulse check caught off-beat notes in our own fixtures. Rewrite
   the reference examples with the rule, not after it.
9. **Exact replay makes content edits honest.** The song was recovered note-for-note from its own trace
   (free), so a rewritten phrase or riff goes through the same pipeline as the original — no
   approximation to argue about. Changing a prompt shifts the replay; restore the checks as they were.
10. **More thinking was not better music.** High effort ≈ 4× thinking tokens, no difference Sujit could
    hear; medium stays (114k of the head debate's 184k tokens were thinking).
11. **The Producer, reworked, finally accepted a first draft** — the first acceptance on record (the old
    one revised 14/14). Live-confirmed on fusion_20261019_083259_fresh.
12. **Domain rules came from the ear, in Sujit's words:** a call ends on tension OFF the nyas; the answer
    resolves onto a main nyas; calls may pile up; a phrase may not climb into a main nyas (Sa excepted);
    the intro walks on a jod's pulse; under a taan, chugs on a home pedal; manjha and antara ring sparse.

### The first debate that argued about the music (2026-10-19, notes debate, out/notes_debate_20261019_094935)

Sitarist (Gemini) vs guitarist (gpt-6-luna), each rewriting notes of its own part; 8 calls (6 + 2
guardrail retries), trace 8975dcdabcef. For the first time the exchange was about notes, and the two
DISAGREED:
  * The sitarist rewrote the head, justifying it with "the old head ended on Sa, merging with the sam" —
    FALSE: it ended on Re. The guitarist (the other model) caught it: "the existing head already ends on
    R, so that cadence is not new", and named a real coexistence fault — the sitar's held Re rubbing the
    guitar's sustained Sa just before the sam — proposing a one-beat rest. The sitarist refused on a
    genuine gat principle ("a gat head cannot fracture into a rest") — which our own hard rule agrees with.
  * The guitarist rewrote the antara riff: from ringing upper-register steps to a low, palm-muted line
    tracing Darbari's own turns (d n P). The sitarist supported the weight but asked for the second
    cycle to end on Re with the sitar's nyas; the guitarist ACCEPTED and changed exactly that note.
One rewrite defended with a reason, one adjusted to the other's ear — the shape of a real exchange, and
the cross-model critic caught a factual error a same-model critic had never caught. Open question for the
ear: the new antara riff is busy and low where Sujit had just approved SPARSE ringing chords.

**Sujit's ear on the notes debate:** "I liked the riff change. The gat change is also good — both
mukhadas are good — but the original had more tension and was more interesting." The first debate
output his ear preferred: the guitarist's antara rewrite (low, palm-muted, tracing d n P / g m R,
ending on Re with the sitar). The sitarist's head rewrite — argued from a false premise — smoothed away
the original's motion into the sam (fewer dir strokes, no gamak, a long held Re): asked to fix what
wasn't broken, it made it calmer. Best version: riff_final (original head + new riff). OPEN: he liked
a BUSY low riff in the antara the same day he approved SPARSE ringing chords there — the rule may be
"speak the raga's language low, don't fight the sitar with unrelated high chords", not "sparse".

### The notes debate, second song: Bhairav (2026-10-19, out/notes_debate_20261019_101238)

Fresh song `fusion_20261019_100727_bhairav` (trace fb08fb641163): the Producer ACCEPTED the first draft
again (2 of 2 since the rework); the head met every measured fact (no self-revision); the alap followed the
new rules live — phrases on the vibhag, a call hanging on komal re (off Bhairav's core nyas), answers home.
The debate (trace 4b6e80296582) was about notes, grounded in the raga's sourced facts, and both players
caught real things:
  * The sitarist rewrote the head to honour Bhairav's "Pa is skipped rising" (our CHARACTER data,
    Parrikar + Tanarang) and to give the vadi komal dha a 4-beat andolan. The guitarist agreed with the
    direction but caught a SECOND rising Pa the rewrite still had, and that the held dha ended before the
    riff's dha hit — the sitarist took the fix (m→d, skipping Pa) and defended its Re ending.
  * The guitarist rewrote the outro riff (a single S held 16 beats) into descending palm-muted figures
    shadowing the sitar's tihai. The sitarist caught the rhythm: the tihai breathes in 5+5+6, so without
    one-beat rests the 2nd and 3rd statements enter on the wrong beats. The guitarist took it — and pointed
    out the sitar's printed outro is 17 beats in a 16-beat section. TRUE (measured): a real length bug in
    the shipped song that no code check caught.
Two runs, two kinds of value: the cross-model reader catches factual and arithmetic errors a same-model
critic never did; and when the premise is a sourced raga fact, the argument converges on better notes.

**Sujit's ear on Bhairav:** "clearly the revised gat was better; the outro seems the same." Notes-debate
record after two songs: 2 better (Darbari antara riff, Bhairav head), 1 sidegrade (Darbari head), 1 neutral
(Bhairav outro — the last 8 s, already ringing out), 0 worse — the first debate design with a winning record
against the human ear. What changed from the four parked designs: notes not knobs, each player owns a real
part, two different models read each other, arguments rest on sourced raga facts, code checks every rewrite.
