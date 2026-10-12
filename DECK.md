# Deck outline — Shruti Shred: What Domain Knowledge Does to an Agentic System

*45 minutes. Practical over theoretical: every pattern is shown as what we did, what bit
us, and the do/don't it left behind. Stories and evidence live in `TALK.md`; this file is
the slide order and the clock. The abstract (`ABSTRACT.md`) is the promise — the deck
keeps its pattern order.*

**The claim, in one line:** domain knowledge decides where uncertainty may live — facts and
derivations stay in code, contextual judgement goes to models, and several agents earn
their place only when a decision needs distinct roles, shared state, or visible
disagreement. *(Sharpened from a GPT review of this outline, 2026-10-11.)*

**Guard rail for the stage:** no argument in the talk may depend on the live run. The
performance and the demo are payoffs; every point is made from pre-captured evidence first.

---

## The clock at a glance

| Time | Part | Slides | What the room gets |
|---|---|---|---|
| 0:00–1:00 | **Cold open — live performance** | 0 | You on rhythm guitar over a 1-min generated piece |
| 1:00–4:00 | **The reveal + the problem** | 4 | "11 agents wrote that" → why one prompt can't |
| 4:00–6:00 | **90-second domain primer** | 2 | Just enough raga/tala/metal to follow |
| 6:00–13:00 | **Where does an agent belong?** | 5 | The code ↔ hybrid ↔ LLM line; decisions, not nouns |
| 13:00–29:00 | **The patterns, in the order the system uses them** | 10 | Eight patterns + the ones we refused |
| 29:00–36:00 | **What building it taught us** | 6 | War stories with evidence |
| 36:00–41:00 | **Live demo** | 2 | The run kicked off at minute 3 lands |
| 41:00–44:00 | **The do/don't checklist + close** | 2 | What to take home |
| 44:00–45:00 | Buffer / Q&A pointer | 1 | |

~32 slides (32 is the thank-you). If Q&A is *inside* the 45, cut Part 4 to three stories (see "Cut list").

---

## 0:00–1:00 · Cold open — the performance

No title slide yet. Lights down, a single black slide with the raga name, and you play.

### Recommended piece

- **Raga: Bhairav.** Its double-harmonic scale (komal re, shuddha Ga, komal dha, shuddha Ni)
  is the sound a Western metal ear already reads as "Indian + heavy" — the flat second over
  an open low string is a classic metal tension, so the fusion lands in the first bar with
  no explanation. It also pays off later: the **red-note slide** (an illegal shuddha Re
  caught in Bhairav) becomes a callback to the piece they just heard.
- **Subgenre: heavy metal.** Its range in the subgenre data is 110–180 BPM, which holds
  128 (melodic death runs 150–220, so it would not). Galloping, anthemic riffs under a
  melodic lead suit "you + the sitar", and it stays playable under stage nerves.
- **Tala: teentaal (16 matras).** One avartan = four bars of 4/4, so you count it like any
  metal song. Avoid Rupak/Jhaptaal for the play-along; odd cycles are a talk point, not a
  stage risk.
- **Tempo: 128 BPM → 8 avartans ≈ 60 s exactly.** Sa = **E**, so the ground note is your
  open low E (or drop-D with Sa = D if you prefer that tuning).
- **Backup raga: Bageshree** — the one raga a practitioner has already certified ("intro and
  gat sound convincingly Bageshree"). Less heavy (Dorian), safer on authenticity.

### Form (one avartan ≈ 7.5 s)

| Avartan | Section | Sitar | You (rhythm) |
|---|---|---|---|
| 1 | Alap | Short phrase over the drone | One ringing Sa power chord, let it decay |
| 2–3 | Gat enters, band in | The mukhda — the hook | Chug the open E, accents on sam |
| 4–5 | **Sawal-jawab** (call and response) | Asks a phrase, rests for the answer | Answers, half a cycle each — previews the blackboard pattern (slide 16) |
| 6–7 | Taan climax | Fast taan | Ringing pads underneath (the riff yields) |
| 8 | **Tihai** | Phrase ×3 landing on sam | Hit the final sam together — dead stop |

The tihai ending is the stage gift: three repeats telegraph the final hit, so you and the
backing track land it together without a cue.

### Production prep (mixing in Logic Pro; only the renders need your go)

- Drive it from a **fixed chart** so the form is exactly the table above.
- A **minus-one mix** in Logic Pro: mute the rendered rhythm guitar so you *are* the rhythm
  guitar; add a one-avartan count-in click on your in-ear bus only.
- Tab the riff straight from the saved composition JSON — the agents' riff, played by hand.
  That buys the reveal line: *"I didn't write the riff I just played."*
- Sawal-jawab gaps: cut the lead on your half-cycles in avartans 4–5 **in Logic Pro**.
- Lock section changes to avartan boundaries (7.5 s at 128 BPM), never to round seconds.
- Rehearse the audio routing on the venue system; keep a recording of the full
  performance as the fallback.
- Render 2 candidates (Bhairav + Bageshree), pick by ear. Keep the losing one as a spare.

---

## 1:00–4:00 · The reveal + the problem

1. **"Everything you just heard except the guitar was composed by eleven agents."**
   The reveal. Title of the talk lands here, not before.
2. **Who I am** — 15 seconds, one line on why a guitarist built this.
3. **The naive attempt.** One prompt: *"compose metal in raga Bhairav."* Play 10 s of the
   one-shot. It's plausible — and nobody in the room can tell whether it's right. Neither
   could the system. *Line:* "The model has heard both traditions and knows the rules of
   neither."
   **Generalise it:** clinical coding, contract drafting, tax rules — any domain with real
   rules has this failure. Plausible ≠ correct, and nothing inside the system can tell them
   apart.
4. **Audience pick → kick off the live run now.** Two options on screen (raga × subgenre),
   show of hands, start `compose_flow` and *leave it running*. "We'll come back to it." A
   full run takes minutes; starting it here turns latency into suspense instead of dead air.

## 4:00–6:00 · The 90-second domain primer

5. **Three independent axes.** Raga = *which notes are legal* (plus grammar and a signature
   phrase, the pakad). Tala = *the rhythmic cycle*, which always resolves on the sam.
   Subgenre = *tempo, register, feel*. 14 ragas × 6 talas × 8 subgenres = 672 — constraints
   multiply into a huge creative space.
6. **Rules and taste.** "You need no music theory for this talk. You need one fact: this
   domain has rules a machine can check, and taste a machine has to judge — and your domain
   does too."

## 6:00–13:00 · Where does an agent belong?

7. **The thesis slide — two questions, a spectrum between them.**
   Every output faces two questions: *is it allowed?* and *is it worth keeping?* "The first
   has a proof. The second has an argument." So: `CODE decides` (is this note legal?) →
   `HYBRID` → `LLM decides` (does it sound like the raga?). Most of the system lives in the
   middle:
   - code establishes legality, an agent explains the violation (Ustad)
   - code measures the arrangement, an agent evaluates it (Producer)
   - code builds a menu of legal edits, an agent chooses one (Arranger)
8. **Knowledge is data; reasoning is the LLM.** `RAGAS["bhairav"]` on screen — verified
   against two Hindustani sources, cited in the code, contested facts flagged in the data,
   asserted by tests. *Line:* "The agents reason over the rulebook; they never write it."
   - ✅ Put domain facts in code with tests. ❌ Let the model supply facts from memory.
9. **One agent per decision, not per noun.** The first design drew an agent per instrument
   and hit ~15. Drawing one per *decision* gave 11. Of seven instruments, only **two** are
   agents (lead, riff); bass, drums, drone follow the riff, so they're code.
   *Line:* "If you're drawing one agent per noun in the output, you're writing a `utils.py`."
10. **The roster** — 11 agents, one sentence each, grouped: *front door* (Interpreter),
    *composers* (Pandit, Riffsmith), *generators* (Lead, Riff, Orchestra), *critics* (Ustad,
    Rasik, Producer), *repair* (Arranger), *referee* (Conductor).
11. **Do / don't for Part 2.**
    - ✅ Ask per criterion: "can code check this?" If yes, it's not the model's job.
    - ✅ Make a deterministic voice the default; promote to an agent only for a real decision.
    - ❌ An agent per entity/instrument/document type. Every agent is latency, cost, and a
      failure surface.

## 13:00–29:00 · The patterns, in the order the system uses them

*Format for each slide: what the pattern is (one line) → how we used it → what bit us → the
rule. ~1.5–2 min each. Code on slides is ≤10 lines.*

12. **Prompt chaining + routing + structured output — the front door.** The Interpreter
    extracts what the user *said* (fuzzy, LLM); a pure resolver decides what's *legal*
    (code). Junk degrades to "open", never to a crash.
    *Bit us:* it hallucinated a whole brief. Raising effort didn't fix it; a `reasoning`
    field **first in the schema** did.
    - ✅ Reasoning-first in the schema. ✅ Fix the prompt before buying effort.
    - ❌ Let the intake make creative choices ("it quietly picked doom for you").
13. **ReAct + the guardrail — Ustad.** One validator, two jobs: the hard gate on generator
    output, *and* a tool the critic calls to explain the violation. The output type has
    **no verdict field** — a lying fake Ustad still yields "illegal".
    *Bit us:* a zero-arg tool + default caching would have returned the first piece's
    verdict forever.
    - ✅ Make the unsafe decision unrepresentable in the type. ❌ "Please don't decide X."
    - **Red-note visual** — callback to the opening Bhairav.
14. **Verifiers — turning a feeling into a budget.** "The riff sounds light", "the alap
    should breathe" → ground share, pitch-change cap, rest share, ends-on-Sa. The model
    composes, code measures, a bounded re-roll quotes the exact violation back.
    *Line:* "You can't prompt for silence — you have to own the clock."
    - ✅ One bounded retry with the violation in the prompt. ❌ Retry loops; if a step needs
      2+ retries routinely, fix the prompt or schema.
15. **Memory — sections that hear what came before.** Each section is generated seeing the
    realised prior sections, so the hook comes back instead of a collage of eight strangers.
    - ✅ Pass the *realised* artifact, not the plan of it.
16. **Collaboration on a blackboard — the studio session.** Lead and riff build each section
    on a shared canvas: leader proposes, follower answers, bounded refines. **Code picks who
    leads** (by section kind) and when it stops.
    *When to use it — the selection rule:* a **shared plan** (everyone reads the same
    constraints, outputs merge mechanically) is enough until a part must *respond to work
    already produced*; only then pay for a **shared blackboard**. Parallel lead + riff
    against one chart were legal and coherent on paper, and deaf to each other.
    *Bit us:* the critique loop's revise regenerated a voice *in isolation* — silently
    erasing the collaboration. Fix: the canvas became first-class flow state.
    - ✅ Cross-agent context must live in durable state. ❌ Autonomous turn-taking on stage.
17. **Evaluator-optimizer + LLM-as-judge — Rasik and the Producer.** Three orthogonal
    critics: *is it legal / does it sound like the raga / does it work as a song.* Judges
    get a fixed 1–5 rubric, anchors per score, facts computed by code (pakad present at beat
    8; energy curve; overlap metrics), and must justify before scoring.
    *Visual:* inputs (composition · computed facts · anchored rubric) → LLM judge → outputs
    (criterion scores · evidence-backed reasons · repair focus). "A judge interprets
    evidence; it never invents it."
    *Bit us:* Rasik was right ("that's a scale run, not a taan") and nothing improved — the
    generator couldn't act on it. Fix was a required `phrase_plan` on the *generator*.
    - ✅ "Code measures, LLM evaluates." ✅ A critic is only as good as the generator's
      ability to act on it. ❌ "Rate this 1–10" with no rubric.
18. **Debate + arbitrator — the money moment.** Triage in code: illegal ⇒ forced revise, no
    debate; everyone happy ⇒ accept. Only a legal-but-contested piece earns a debate:
    Rasik ↔ Producer, bounded rounds, the Conductor *always* rules at the cap with a
    **surgical** ruling — one layer, one reason. Show the real Darbari transcript.
    *Line:* "Debate needs a referee and a clock."
    - ✅ Gate the expensive debate behind a free check. ❌ Wait for consensus — adversarial
      agents are designed never to agree.
19. **Repair should be as local as the failure.** One principle, three scales in the system:
    - *a cell* — a verifier names the exact violation and only that cell re-rolls;
    - *a voice* — the Conductor's ruling names one layer and one reason, and only that voice
      regenerates while bass/drums/drone re-derive around it;
    - *a note* — when riff and melody grind, the **Arranger** picks from a **code-built menu
      of legal one-note edits**. Who yields is code (gat-first ⇒ riff yields); it cannot move
      an attack, so the hook survives by construction.
    - ✅ Give the model choices, not a blank page, when correctness matters. ✅ Regenerate
      the whole output only when the failure is genuinely global.
20. **The loop itself — and the patterns we refused.** One CrewAI Flow: interpret → compose
    → generate → critique → arbitrate → local repair → render, with the round cap as one
    line of code. **Refused, grouped by what they would cost** (defaults for *this* system,
    not universal bans):
    - *Decomposition* — entity-shaped roles (an agent per instrument).
    - *Authority* — models for facts code can prove.
    - *Control* — orchestrator-workers, autonomous delegation (the framework's own headline
      feature), and **unbounded** reflection. Our reflection is bounded; that's the point.
    - ✅ Own the loop and the terminator. ❌ Trust a framework to stop; Flows have no
      built-in loop cap.
21. **Recap slide** — the eight patterns on one diagram, each tagged code / hybrid / LLM.

## 29:00–36:00 · What building it taught us

*One story per slide, each with its evidence. These are the "practical" heart for an
engineering audience.*

22. **One complaint, four layers.** "The riffs sound light and happy" looks like a prompt
    problem. The saved composition JSON apportioned it across four layers (strata visual):
    - *Menu* — the piece was Yaman, the brightest raga we offer;
    - *Voicing* — chord stacks were bright add9/tenth colours, not power-chord weight;
    - *Generation* — the line changed pitch on 79% of notes (a melody wearing a riff's clothes);
    - *Render* — the slides and palm-mutes *were* in the data and came out inaudible.
    Each layer got its own fix and owner; only one of them was the prompt. (Companion
    one-liner: the drum data declared blast beats the drum code never read — "sounds
    robotic" was plumbing, not a missing agent.)
    - ✅ Decompose aesthetic feedback against evidence before touching anything.
      ❌ Assume the prompt is the guilty layer.
23. **The MIDI outvoted two reviewers.** My ear and a Gemini review agreed the riff was muddy
    from tritone chord stacks. The file said: 110 octaves, 8 fifths, zero tritones. The real
    causes were register, clipping, and dry samples.
    - ✅ Save the symbolic artifact beside every output; diagnose from it. ❌ Fix the
      plausible mechanism.
24. **The prompt that documented a bug.** A renderer clamp chopped every palm-mute to 80 ms;
    instead of fixing it, we'd written it *into the prompt* as a musical rule — and the
    agent faithfully composed around the bug for months. Visual: the deleted prompt line
    beside `PALM_MUTE_MS = 80`.
    - ❌ Never explain a defect to the model as a rule. Your output is only as good as
      whatever consumes it.
25. **The rule that was backwards.** Our prompt demanded "at least three note values" — the
    exact opposite of a real gat (one pulse, two values). A practitioner sang two gats, we
    measured, flipped the rule, and got: *"convincingly Bageshree."*
    - ✅ When you encode a domain you don't practise, build for correction — keep the
      refutation as the test.
26. **Don't trust the framework's knobs — verify in the trace.** CrewAI's Gemini provider
    silently dropped `reasoning_effort`: 4k–18k thinking tokens per call, 137 s stalls. A
    loop listener that fires once and never re-arms. Both found by reading traces and source.
    - ✅ Tracing on by default for every LLM run. ✅ Test the *second* iteration of a loop.
27. **Engineering hygiene that kept it affordable.** Every stage injected → the whole
    multi-agent flow unit-tested with zero API calls (760+ pure tests). One eval case at a
    time, not the suite. Debate gated behind code triage. Live billing changes behaviour.

## 36:00–41:00 · Live demo

28. **Back to the run from minute 3.** Open the trace portal on it: the composers' dialogue,
    a guardrail retry, Ustad's tool call, the critics' rubric, and — if it fired — the
    debate and the Conductor's ruling. Then **play it**.
29. **Insurance.** A pre-recorded run (trace + WAV) one keypress away. Say it out loud if
    you use it; the audience respects honesty more than a stall.

*Depends on: the live UI (Phase 3) or, failing that, the trace portal as the viewing
surface — the portal exists today and is enough.*

## 41:00–44:00 · Close

30. **The decision matrix — the reusable framework.** Read each row as a question about
    the decision in front of you; the answers choose the architecture.

    | Decision property | Code | One model | Several agents |
    |---|---|---|---|
    | Provable answer (is this note legal?) | ✅ owns it | ✗ | ✗ |
    | Contextual judgement (does it sound like the raga?) | supplies evidence | ✅ judges | ✗ |
    | Constrained choice (which fix for this grind?) | defines the options | ✅ chooses | ✗ |
    | Shared evolving artefact (lead ⇄ riff) | owns state + turns | possible | ✅ distinct roles |
    | Conflicting goals (soul vs. impact) | sets bounds + clock | ✗ hides the trade-off | ✅ debate + arbiter |

    *Line:* "The pattern follows the decision."
31. **The checklist** — the practical do/don'ts from every part, on one slide (the
    leave-behind; show it while you land the takeaways, don't read it out):

    | Do | Don't |
    |---|---|
    | Put domain facts in code, with sources and tests | Let the model supply facts |
    | One agent per decision | One agent per noun / instrument |
    | Make the unsafe decision unrepresentable in the type | Ask the model nicely not to decide it |
    | Turn feelings into measurable budgets | Chase taste with prompt adjectives |
    | Code measures, LLM evaluates | Rubric-free "rate this" judging |
    | Repair as locally as the failure | Regenerate everything on any complaint |
    | Bounded loops, a referee, a clock | Wait for agents to converge |
    | Measure the artifact before you fix | Fix the plausible mechanism |
    | Trace every run; verify every knob | Trust the framework's defaults |
    | Build for a practitioner to correct you | Encode a domain from reasoning alone |

    **Three takeaways** spoken over it (the abstract's promise): name the pattern your
    problem needs; decide which parts should *not* be agents; encode your domain's rules
    into the parts that are.

## 44:00–45:00

32. **Thank you** — repo/QR, and optionally 10 s of the live piece as the walk-off.

---

## Cut list (if running long, in order)

1. Slide 15 (memory) — fold into slide 16 as one sentence.
2. Slides 23, 27 — keep the lines, drop the slides (23's lesson is already in 22).
3. Slide 21 (recap diagram) — the matrix on slide 30 does the same job.
4. Part 4 down to three stories: 22, 24, 25.

## Open decisions for Sujit

- Is Q&A inside the 45 or after? (Changes whether the cut list is needed.)
- Opening raga: Bhairav (heavier, red-note callback) or Bageshree (practitioner-certified)?
- Live demo surface: build the Phase 3 UI before the talk, or demo through the trace portal?
- Two-option audience vote, or a free-text prompt through the Interpreter? (Free text shows
  the front-door pattern live but is riskier.)

---

## The built deck (2026-10-11)

**Live deck:** https://claude.ai/artifact/9fb9xNiGt1rF8UWXMQ82ja (Slides artifact, private until shared).
**Source:** `talk/deck/project/` (index `deck.json` + one HTML file per slide).
**Sprites:** `talk/sprites/gen_sprites.mjs` regenerates the 48×64 personas and the instruments
(`node talk/sprites/gen_sprites.mjs` → `talk/sprites/svg/`); `talk/sprites/assets.json` maps each
to its uploaded `/_blob/` id. The personas are a hi-fi port of the demo UI's sprite factory.

**Look:** the demo UI's pixel-art studio. Stage-black, role colours (composer gold, generator
saffron, critic magenta, Conductor cyan), Press Start 2P headlines, VT323 body, Noto Sans
Devanagari. **Motion rules (from the GPT creative direction):** motion only for a change of system
state; audio is evidence; one focal event per slide; war stories and the close stay still.

**Changed by the creative direction:** the experiment is now one A/B/C slide (plausible → correct →
music, verdicts held until all three play); the vote picks between **pre-generated** branches
(doom / symphonic / thrash) whose real traces we replay; the closing line is "The model supplies
range. The domain supplies shape. The architecture decides which one has authority." Rejected from
it: its critic roles (Ustad is legality and exits the debate; the debate is Rasik ↔ Producer).

## Audio script (to produce)

| ID | Clip | Slide | Cost |
|---|---|---|---|
| A01 | 60 s backing, Bhairav / heavy / teentaal 128 / Sa=E, rhythm guitar muted | perform | one approved live render + Logic |
| A02 | 12 s stem build: drone → + sitar → + tabla | hindustani | free (deterministic render) |
| A03 | 9 s: scale-like run vs encoded Bhairav movement | raga | free |
| A04 | 6 s: straight Re vs Re with andolan (optional) | raga | free |
| A05 | 7.5 s: one teentaal cycle at 128 BPM | tala | free |
| A06 | 3 × 6 s: prompt-only / prompt+rules / domain-shaped | naive (A/B/C) | one cached LLM call for A; B and C free |
| A07 | 10 s: Lead phrase, Riff response, combined | blackboard | free re-render of a saved studio piece |
| A08 | 11 s: failing region vs repaired, all else identical | debate / repair | free re-render of a saved revise |
| A09 | 9 s: same notes without vs with articulations | layers | free (the gate-fix A/B already exists) |
| A10 | 8 s: melody-riff vs chug-riff, same tempo and pitches | verifier | free |
| A11 | 45–60 s: the voted branch | demo | three pre-generated runs (approved) |
| A12 | 60 s: recorded performance with guitar | fallback | Logic |

Level-match every A/B pair, leave 0.5–1 s silence between parts, never talk over a comparison.
