# Prompt Engineering — how we write prompts HERE

A short, opinionated, cited reference for the prompts in this repo. Our prompts live as
external config (`crew/config/agents.yaml` for role/goal/backstory, `crew/config/tasks.yaml`
for task descriptions), the crew runs on the **native google-genai provider** (not LiteLLM —
verified below), and every agent returns Pydantic-validated structured output. This doc is
tailored to that reality: it tells you what to do, why, and where the labs disagree.

Every recommendation is tagged **[Gemini]** (Gemini-specific), **[cross-lab]** (Google +
Anthropic + OpenAI converge), or **[judge]** (LLM-as-judge). Sources are keyed inline like
`[G-struct]` and listed in full at the end. Primary/official sources are preferred; where a
claim rests on a single blog or forum post, it is marked *(single-source)*.

---

## 1. TL;DR house rules (the checklist)

- **Trust controlled generation; do not scrape JSON.** Our `LLM(model="gemini/gemini-3.5-flash")`
  resolves to the **native `GeminiCompletion` provider** (`is_litellm=False`), so tool-less agents
  get Gemini's native **controlled generation** (`response_mime_type="application/json"` +
  `response_json_schema`). The decoder is constrained — the model *cannot* emit ```json fences or
  prose around the object. Hand-rolled text-scraping is unnecessary for us. **[Gemini]**
- **Simplify schemas, don't parse manually.** The real structured-output risk is *complex schemas*
  under controlled generation: `Optional` unions (`anyOf`), deep nesting, explicit field defaults.
  Prefer flat scalar fields; minimize optional+nullable; keep enums closed. **[Gemini]** `[G-struct]`
- **Keep the `reasoning` field first, and verify it emits first.** Reasoning-first CoT works only if
  the reasoning token stream precedes the answer. Confirm it in a trace. **[Gemini]** `[G-json-blog, castillo]`
- **Behavioral rules go in the backstory/goal; the task + data go in the description.** System-level
  = persona, hard rules, output contract. User-level = this piece's inputs and the one objective. **[cross-lab]**
- **Tell the model what TO do.** Replace blanket negatives ("never guess", "do not infer") with a
  positive instruction — Gemini over-indexes on negatives and OpenAI/Anthropic say the same. **[cross-lab]**
- **Dial back ALL-CAPS mandates.** "CRITICAL: you MUST" → "Use…". Newer models over-trigger on
  aggressive language. **[cross-lab]** `[anthropic]`
- **Markdown *or* XML delimiters, not both.** We use markdown headings (METHOD / HARD RULES / FACTS) —
  keep it consistent. **[Gemini]** `[schmid]`
- **Judges: fixed 3- or 5-point rubric, per-criterion reasoning before the score, concrete 1/3/5
  anchors, an explicit "don't reward length" line.** **[judge]**
- **Temperature is our knob today — but see §3.** Generators 0.9, composers 0.7, critics 0.2,
  extractor 0.0. Google's Gemini-3-family guidance says keep temp at **1.0**; this is a real tension
  we should verify, not assume. **[Gemini]** `[gemini3]`
- **One bounded guardrail retry, never a loop.** If a step needs 2+ retries routinely, fix the
  prompt/schema. Already our rule (`COMPOSER_RETRIES=1`, `GENERATOR_RETRIES=1`). **[cross-lab]**

---

## 2. Structured output on Gemini (our reality)

The single most important fact for this codebase, verified against our installed CrewAI 1.15.2:
`crewai.LLM(model="gemini/gemini-3.5-flash")` uses the **native `GeminiCompletion` provider**, not
LiteLLM. In `_prepare_completion_params`, a **tool-less agent** (Interpreter, composers, Lead, Riff,
Rasik, Producer, Conductor) gets Gemini's native **controlled generation**:
`response_mime_type="application/json"` plus a `response_json_schema` (Gemini 2.0+, which 3.5-flash
is) or `response_schema` (1.5). This is model-native constrained decoding — analogous to LangChain's
`method="json_schema"`. The consequence that shapes everything: **the model physically cannot wrap the
object in ```json fences or add prose**, so the manual "scrape the JSON out of the text and retry"
pattern that appears in a lot of Gemini folklore is **unnecessary for us**. Our `output_pydantic`
validation is the shape guarantee; the guardrail adds the one domain rule (legality).

The one agent that differs is **Ustad**, which carries the `validate_composition` tool. Gemini
cannot combine tools with a response schema, so CrewAI injects a `structured_output` pseudo-tool and
the answer arrives as a **function call** (analogous to LangChain `method="function_calling"`). Same
Pydantic guarantee, different transport. (Gemini 3 has since added the ability to combine structured
outputs *with* built-in tools via `response_format` `[gemini3]`, but the CrewAI-mediated path we use
still routes Ustad through the pseudo-tool.)

So the actionable rule is **not** "parse it yourself" — it is **keep schemas simple**. Google states
plainly that **"Very large or deeply nested schemas may be rejected"** `[G-struct]`, and Gemini's
controlled generation has historically handled unions and optionality poorly. Concretely, for our
`crew/contracts.py`:

- **`Optional[...]` fields become `anyOf` unions with `"null"`.** Our contracts lean on these heavily
  (`RawIntent`, `ResolvedBrief`, and the `Note`/`LeadNote`/`RiffNote`/`DrumHit` families). Nullable is
  *supported* — the correct encoding is a type array, `{"type": ["string", "null"]}` `[G-struct]` —
  and Google frames deliberate nullability as a hallucination-reducer (return `null` when context is
  missing) `[firebase]`. But each optional widens the constrained-decoding search and adds an `anyOf`
  branch, so prefer required scalars with a sentinel (e.g. `""`, `0`) over `Optional` where the field
  is really always present. **[Gemini]**
- **Avoid unions of dissimilar types.** `meend: Optional[Union[str, dict]]` (contracts.py:669) is the
  hardest shape for controlled generation — a nullable union of a string and an object. If it misbehaves
  live, split it into two nullable scalar fields. **[Gemini]** *(inference from `[G-struct]` + `[castillo]`)*
- **Explicit field defaults have bitten the response schema.** A GitHub/forum report shows the API
  rejecting Pydantic models with `Field(default=...)` / inherited defaults ("Default value is not
  supported in the response schema") while `Optional` + `None` defaults pass `[gh699, forum-opt]`
  *(single-source, forum)*. Our schemas use `reasoning: str = ""` and `Field(default_factory=list)`
  throughout and evidently work end-to-end on 3.5-flash, so this is a **watch-item, not a known break** —
  if a new model version starts 400-ing, defaults are the first suspect.
- **anyOf / `$ref` / `type:"null"` are now first-class.** Google added full JSON-Schema keyword support
  (unions, recursion, nullability, numeric bounds) across supported models `[G-json-blog]`, so the older
  "nullish values hard-fail" era is largely over on current models — but complexity limits remain.
- **Reasoning-first ordering.** We declare `reasoning` as the first schema field on every agent so the
  model thinks before it commits. Gemini now preserves schema property order implicitly for 2.5+ models
  `[G-json-blog]`, so this should hold on 3.5-flash — but an older google-genai SDK once **sorted keys
  alphabetically**, silently emitting the answer before the reasoning and dropping task accuracy >10 pts
  `[castillo]` *(single-source, blog; likely superseded)*. **Verify in a trace that `reasoning` actually
  streams first**; if it ever doesn't, the cheap fix is to rename fields so the desired order is also
  alphabetical.
- **Shape ≠ correctness.** "While output is syntactically correct JSON, always validate values in your
  application… implement robust error handling for schema-compliant but semantically incorrect outputs"
  `[G-struct]`. This is exactly our "code decides the checkable" split: `output_pydantic` guarantees the
  shape, the guardrail and `validate_composition` guarantee the music. **[Gemini]**

Schema hygiene that costs nothing: put a **`description` on the schema and on every non-obvious field**,
use **specific types and enums** (we already use `Literal` for `kind`, `RiffTechnique`, verdicts), and
keep any in-prompt examples in the **same property order as the schema** `[G-struct]`.

---

## 3. Temperature and top-p

Temperature is our primary steering knob (`crew/config.py`), on the theory that Gemini has no
reasoning-effort slider. Two corrections to that framing are worth stating up front. First, the code
already passes `reasoning_effort="low"` into `LLM(...)`, which CrewAI maps to Gemini's thinking budget —
so a reasoning control **does** exist for this model family (Gemini 3 exposes `thinking_level`:
`minimal`/`low`/`medium`/`high`, default `high`) `[gemini3]`. Second, and more consequential:

> **[Gemini] Tension to resolve.** For the **Gemini-3.x family** (which `gemini-3.5-flash` belongs to),
> Google "**strongly recommend[s] keeping the temperature parameter at its default value of `1.0`**"
> and warns that "**setting it below 1.0 may lead to unexpected behavior, such as looping or degraded
> performance, particularly in complex mathematical or reasoning tasks**" `[gemini3]`. Our critics run
> at 0.2 and our extractor at 0.0 — directly against this guidance.

This is the classic older-Gemini vs Gemini-3 shift. The pre-3 canon (Boonstra's whitepaper, the Vertex
parameter docs, and every practitioner cheat-sheet) says lower temperature for determinism and higher for
creativity, which is where our 0.9/0.7/0.2/0.0 ladder comes from. The Gemini-3 guidance inverts the
low-temp-for-consistency habit. **We should not silently "fix" this** — instead, treat it as an empirical
question our own tooling can answer: run a critic at 0.2 vs 1.0 on a fixed composition, read both traces,
and keep whichever gives stabler, better-justified scores. If low temp is causing looping or flat scoring,
the Gemini-3 default is the cause. Until then, the numbers below capture *both* worlds; use the Gemini-3
column for 3.x models and the classic column only where it empirically beats it.

**Reference values (cite the row you rely on):**

| Task type | Classic Gemini / Boonstra | Gemini-3.x family | Source |
|---|---|---|---|
| Supported range / default | 0.0–2.0, default 1.0, start at 1.0 | same; **keep at 1.0** | `[vertex-params, gemini3]` (primary) |
| Creative generation (our generators) | temp 0.8–1.0, top-p ~0.95 | 1.0 | `[vertex-params, boonstra]` |
| Balanced "natural text" | temp 0.7, top-K 30, top-P 0.95 | 1.0 | `[boonstra]` (blog) |
| Extraction / factual (our Interpreter) | temp 0.0–0.2 | 1.0 (per Gemini-3 guidance) | `[boonstra, weinmeister]` (blog) |
| Judge / scoring (our critics) | temp 0 or 0.1–0.2 | 1.0 (per Gemini-3 guidance) | `[wandb]` (blog) vs `[gemini3]` (primary) |

Mechanics worth knowing, so the knobs aren't fought against each other: Gemini applies **top-K first, then
top-P, then temperature** on the narrowed set `[vertex-params]`. Google's tuning order is **temperature
first, then top-p, and top-k rarely** `[vertex-params]`. Temperature and top-p should move in the *same*
direction (both low for focus, both high for diversity) `[boonstra]` *(blog)*. Note that **temperature 0
is "mostly deterministic," not fully** — "a small amount of variation is still possible" `[vertex-params]`
— so a temp-0 critic can still drift slightly between runs. And a **fixed seed is best-effort, not a
determinism guarantee** `[vertex-params]`.

One judge-specific caveat that cuts against reaching for temperature at all: decoding temperature is **not
a bias-mitigation lever** — rubric position bias stays flat across `τ ∈ {0, 0.3, 0.6, 1.0}` `[pos-bias]`
(primary). So if a critic is unstable because of *bias*, temperature won't save it; the rubric fixes in §7 will.

---

## 4. System-instruction vs user-content split

The split maps cleanly onto our two config files, and the labs agree on the principle. **Behavioral
constraints, the role/persona, and the output-format contract belong at the system level — the very top,
where they "anchor the model's reasoning process"** `[schmid, vertex-gen3]` **[Gemini]**. That is our
`agents.yaml` `role`/`goal`/`backstory`: durable identity that is the same on every call (Rasik is a
disciplined rasik who would rather give an honest 2; the Producer is raga-agnostic; Ustad trusts the tool
over his ear). The **per-invocation task and its data belong at the user level** — our `tasks.yaml`
`description`, holding this section's METHOD, HARD RULES, the injected raga/tala/subgenre FACTS, and the one
objective. Keep one task = one objective = one output; this is already how the files read.

For agents that receive a **large data blob** (a whole realized composition for the critics, prior-section
memory for Lead/Riff), Google's Gemini-3 guidance is specific: **put the instruction/question at the *end*,
after the data, and anchor it with a phrase like "Based on the preceding information…"** `[vertex-gen3]`
**[Gemini]**. OpenAI's long-context guidance rhymes: **place key instructions at both the top and the
bottom**, and when instructions conflict, GPT-4.1 follows the one **closer to the end** `[openai-41]`
**[cross-lab]**. Practical upshot for the critic tasks: the rubric and the "score now" instruction should
sit after the composition dump, not be buried above it.

---

## 5. Instruction craft

The most load-bearing cross-lab rule, and the one our current prompts most often break: **tell the model
what to do, not what not to do.** Anthropic's canonical example is replacing "Do not use markdown" with
"Your response should be composed of smoothly flowing prose paragraphs" `[anthropic]`; OpenAI says the same
and adds that all-caps, bribes, and tips are generally unnecessary `[openai-41]`; and **Gemini-3 warns
specifically that blanket negative constraints like "do not infer" / "do not guess" make the model
over-index on them and fail basic logic**, recommending you positively steer it to *use the provided
context instead* `[vertex-gen3, schmid]` **[cross-lab, esp. Gemini]**. Our Interpreter goal ("Never invent
or guess a value") and several `Do NOT …` lines in `tasks.yaml` are exactly this pattern; where we can, we
should reframe positively — e.g. "Copy only spans that appear verbatim in the request; leave every unstated
field null" carries the same meaning without the negative the model over-weights. Keep negatives only for
genuine hard bans (the legality rules), and phrase those as the guardrail's job rather than leaning on prose.

Related, and important for our HARD-RULES blocks: **dial back aggressive emphasis.** Anthropic notes newer
models are so responsive to the system prompt that "CRITICAL: You MUST use this tool when…" over-triggers,
and the fix is ordinary phrasing, "Use this tool when…" `[anthropic]` **[cross-lab]**. Our "You MUST call
validate_composition" is legitimately load-bearing, but it is enforced structurally anyway (Ustad has no
verdict field to fill), so the caps are decorative — prefer plain imperative.

On **delimiters**, use markdown **or** XML tags, not both — mixing them muddies the boundary between
instructions and data `[schmid]` **[Gemini]**. We use markdown headings consistently, which is fine.
Anthropic prefers XML tags `[anthropic]` and OpenAI finds both markdown and XML work well while **JSON is a
poor wrapper for input context** `[openai-41]` (distinct from JSON as an *output* format, which is fine) —
so keep our structural markdown, and don't wrap injected facts in JSON just for looks.

On **output-format control**, we get it largely for free from controlled generation (§2); the prompt's job
is to name the shape in one line and let the schema enforce it, not to describe the JSON at length.

---

## 6. Few-shot vs zero-shot, and reasoning-first CoT

Google's default is unambiguous: **"always include few-shot examples… prompts without them are likely to be
less effective"** `[vertex-gen3]`, and Anthropic recommends **3–5 diverse examples wrapped in `<example>`
tags** `[anthropic]` **[cross-lab]**. For our generators and critics — which have a fixed idiom to imitate
(a legal power-chord riff, a per-criterion justification) — a couple of worked examples in the task
description earn their tokens. This is the standard advice and we should lean into it for the composing and
scoring tasks.

The important nuance is the **reasoning-model caveat**, which is where the labs split by *model class* (see
§8). For genuine reasoning models, hand-holding hurts: OpenAI says the o-series "**perform best with
straightforward prompts**," that "think step by step" is unnecessary and can *hinder*, and that you should
**start zero-shot** `[openai-reason]` (primary); Anthropic says **"a prompt like 'think thoroughly' often
produces better reasoning than a hand-written step-by-step plan"** `[anthropic]`; and Gemini-3 says if you
used chain-of-thought prompting to force 2.5 to reason, **switch to `thinking_level:"high"` plus *simplified*
prompts** `[gemini3]`.

How that maps to us: **`gemini-3.5-flash` at `reasoning_effort="low"` is not a heavy reasoning model**, so
our **reasoning-first CoT (the `reasoning` field emitted first) is appropriate and helps** — it externalizes
the chain the model isn't spending large internal thinking budget on, and it makes the trace auditable
(Google itself endorses "instruct the model to explain its reasoning" as a first-class strategy `[vertex-strat]`).
The caveat bites the other direction: **if we promote the critics/Conductor to a Pro tier at high thinking**
(the planned `RMA_PRO_MODEL` move), we should *lighten* the CoT scaffolding, not add more — let the model's
own reasoning run and keep the schema's `reasoning` field as a short justification rather than a prescriptive
step-by-step recipe. Watch, too, for the interaction with controlled generation: constrained JSON decoding
has been reported to *reduce* quality on heavy reasoning tasks (JSON-Schema worse than natural language on
5/6 reasoning tasks) `[castillo]` *(single-source, blog)* — one more reason our reasoning-first-then-scores
schema (reason in a free-text field, *then* commit the structured scores) is the right shape.

---

## 7. LLM-as-judge (Rasik, Producer, Conductor)

Our critics are textbook LLM-as-judge, and the discipline that makes them trustworthy is baked into the
design already; this section is the checklist to hold the line. The best-practice core is **criterion-by-
criterion reasoning written out *before* the numeric score (G-Eval style), not a one-line "is this good?"**
`[wandb]` — which is exactly our `reasoning`-first schema and our fixed 1-5 rubrics (`RasikScores`:
pakad/idiom/rasa; `ProducerScores`: nine criteria). Reinforce it with:

- **Concrete anchors.** State what a **1, a 3, and a 5** look like for each criterion; anchors lock the
  grading boundary and counter central-tendency clustering `[wandb]` **[judge]**. Our rubric field comments
  are terse — spelling out the 1/3/5 band per criterion in `tasks.yaml` is the highest-value upgrade here.
- **Define success / failure / partial per criterion**, and name the edge case (fluent-but-wrong) so the
  judge doesn't reward surface polish `[wandb]` **[judge]**.
- **Stay in a 3- or 5-point scale.** This is the *lower-bias regime*; binary and 9-point scales measurably
  *increase* position bias `[pos-bias]` (primary) **[judge]**. Our 1-5 is correct — don't "refine" it to 1-10.
- **Anti-verbosity line.** Add an explicit "**do not reward longer or more elaborate answers; score only on
  the named criterion**." A rubric line like this roughly *halves* verbosity bias `[futureagi]` *(single-
  source, blog)* **[judge]**. Cheap, and directly relevant since a florid composition shouldn't out-score a
  tight one.
- **Ground every score in evidence, require a citation.** Our critics must point to the phrase / name the
  ornament / cite the metric (`pakad_presence`, the `metrics.py` numbers) before committing a score. This is
  the "criteria, not vibes" discipline and it is also what lets a human audit the trace.

On the **three biases**, and what actually reaches them:

- **Position/order bias is structural and *not* reachable by a rubric instruction or by temperature**
  `[futureagi, pos-bias]` (primary). It applies to rubric scoring too: the judge over-selects score options
  and criterion orders at certain positions, and the *direction* is model-specific (some first-biased, some
  last-biased) `[pos-bias]`. Reach it mechanically — **permute option/criterion order** across runs (a few
  random shuffles suffice) and, in any *pairwise* comparison, **swap A/B and average** `[pos-bias, futureagi]`.
  This is CLAUDE.md's "swap option order when comparing," now empirically grounded.
- **Verbosity bias** — the "don't reward length" line above, plus keep scores per-criterion so length can't
  masquerade as quality `[futureagi, wandb]`.
- **Self-preference bias** — a judge inflates outputs from its own model family (reported ~10–25%
  `[futureagi]` *(single-source, blog)*). Our critics and generators are the **same Gemini family**, so this
  is live. The clean mitigation is a **different family for the judge**; the practical one, given we're
  Gemini-committed, is to **lean on the stronger judge tier** (bigger models are markedly more robust to
  scoring bias `[scoring-bias, pos-bias]`, primary — the concrete argument for `RMA_PRO_MODEL` on the
  critics) and to keep scores grounded in *code-computed* facts the model can't flatter away.

Two structural notes specific to our debate. First, **debate can *compound* bias** (bandwagon / CoT
amplification) unless a disciplined referee breaks it `[bias-loop]` — which is precisely why the Conductor is
a code-clocked terminator that always rules at the cap rather than waiting for organic consensus. Second, if
we ever include a **reference answer** in a scoring prompt, give it a **full/maximum score** — that
calibrates best and is the most influential prompt-format choice `[scoring-bias]` (primary). And prefer
**anti-sycophancy by default**: Gemini-3 is already terse and direct unless asked to be chatty `[gemini3]`,
so we don't need to fight verbosity in the judges' output — just don't invite it.

---

## 8. Where the labs disagree (flag explicitly)

- **Temperature for consistency [Gemini vs classic canon].** Gemini-3 says **keep temp at 1.0** and warns
  that lowering it degrades reasoning `[gemini3]`; Boonstra/Vertex/every judge blog say **lower temp for
  deterministic scoring** `[boonstra, wandb, vertex-params]`. This directly contradicts our 0.2/0.0 config —
  resolve empirically (§3), don't assume. **This is our biggest open tension.**
- **Few-shot: always vs start-without [model-class split].** Google: **always include examples** `[vertex-gen3]`.
  OpenAI reasoning guide: **start zero-shot**, reasoning models often don't need them `[openai-reason]`. Not a
  flat contradiction — it's instruction-tuned models (our Flash generators → examples help) vs reasoning
  models (a Pro/high-thinking tier → try without first).
- **Chain-of-thought hand-holding [model-class split].** For non-reasoning models, *induce* planning/CoT
  (GPT-4.1: explicit planning +4% pass rate `[openai-41]`; our reasoning-first field). For reasoning models,
  *don't* — "think step by step" can hinder `[openai-reason]`, "think thoroughly" beats a prescribed plan
  `[anthropic]`, Gemini-3 wants simplified prompts + `thinking_level` `[gemini3]`.
- **Delimiter of choice [stylistic].** Gemini-3: markdown **or** XML, don't mix `[schmid]`. Anthropic: **XML
  tags** `[anthropic]`. OpenAI: markdown/XML both fine, **JSON poor for wrapping input** `[openai-41]`. Pick
  one per file; we use markdown.
- **"nullish/complex JSON hard-fails" — mostly historical.** Older reports (OpenAI-compat mode 400s on
  Optional, default-value rejection) `[forum-opt, gh699]` *(forum)* predate Google's full JSON-Schema
  rollout `[G-json-blog]` and, crucially, describe the **LiteLLM/OpenAI-compat path we do *not* use**. On our
  **native** provider with a current model, the remaining real limit is schema *size/nesting* `[G-struct]`,
  not nullability per se.

---

## 9. Sources

**Primary / official (Google):**
- `[G-struct]` Gemini API — Structured outputs. https://ai.google.dev/gemini-api/docs/structured-output
- `[gemini3]` Gemini API — Gemini 3 developer guide (temperature=1.0, thinking_level, verbosity, structured-output+tools). https://ai.google.dev/gemini-api/docs/gemini-3
- `[G-json-blog]` Google — "JSON Schema support and implicit property ordering in the Gemini API" (anyOf/$ref/null; order preserved 2.5+). https://blog.google/technology/developers/gemini-api-structured-outputs/
- `[vertex-strat]` Vertex AI — Overview of prompting strategies (clear instructions, few-shot, explain reasoning, delimiters). https://cloud.google.com/vertex-ai/generative-ai/docs/learn/prompts/prompt-design-strategies
- `[vertex-params]` Vertex AI — Experiment with parameter values (temperature 0–2, default 1.0; tuning order; pipeline order; seed best-effort). https://cloud.google.com/vertex-ai/generative-ai/docs/learn/prompts/adjust-parameter-values
- `[vertex-gen3]` Vertex AI — Gemini 3 prompting guide (instructions-at-end for long context; positive over negative; few-shot). https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/start/gemini-3-prompting-guide

**Primary / official (Anthropic, OpenAI):**
- `[anthropic]` Anthropic — Claude prompting best practices (positive instructions; XML delimiters; 3–5 examples; dial back caps; structured outputs + retries; general-over-prescriptive reasoning). https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices
- `[openai-41]` OpenAI — GPT-4.1 prompting guide (literal instruction-following; top+bottom placement; induce planning; JSON poor for wrapping). https://developers.openai.com/cookbook/examples/gpt4-1_prompting_guide
- `[openai-reason]` OpenAI — Reasoning best practices (straightforward prompts; skip "think step by step"; start zero-shot). https://developers.openai.com/api/docs/guides/reasoning-best-practices

**Primary / research (LLM-as-judge):**
- `[pos-bias]` "Position Bias in Rubric-Based LLM-as-a-Judge" (rubric scoring is multiple-choice-like; direction model-specific; temperature not a lever; 3–5-point is lower-bias; permutation fixes it). arXiv 2602.02219.
- `[scoring-bias]` "Evaluating Scoring Bias in LLM-as-a-Judge" (rubric-order / score-ID / reference-answer biases; full-mark reference calibrates best; stronger judges more robust). arXiv 2506.22316.

**Secondary / practitioner (marked single-source where relied on):**
- `[boonstra]` Lee Boonstra (Google Cloud) — Prompt Engineering whitepaper (temp/top-K/top-P presets; sweet spot 0.7/30/0.95). https://www.leeboonstra.dev/writing/write-prompting-whitepaper/
- `[schmid]` Philipp Schmid (Google DeepMind) — Gemini 3 prompting best practices (system-instruction placement; markdown-or-XML; verbosity). https://www.philschmid.de/gemini-3-prompt-practices
- `[castillo]` Dylan Castillo — "The good, the bad, and the ugly of Gemini's structured outputs" (constrained decoding vs CoT; historical alphabetical key-sort). https://dylancastillo.co/posts/gemini-structured-outputs.html
- `[weinmeister]` Karl Weinmeister (Google Cloud) — "Beyond temperature: tuning with top-k and top-p." (Google Cloud Community, Medium)
- `[wandb]` Weights & Biases — "Exploring LLM-as-a-Judge" (rubric construction; anchors; order randomization; identity hiding).
- `[futureagi]` FutureAGI — "LLM-Judge Bias Mitigation (2026)" (verbosity/position/self-preference magnitudes; anti-length rubric line). https://futureagi.com/blog/evaluating-llm-judge-bias-mitigation-2026/
- `[bias-loop]` "Bias in the Loop: Auditing LLM-as-a-Judge for Software Engineering" (debate compounds bias without a referee). arXiv 2604.16790.
- `[firebase]` Firebase AI Logic — Generate structured output (deliberate nullable reduces hallucination). https://firebase.google.com/docs/ai-logic/generate-structured-output
- `[forum-opt]` Google AI Developers Forum — Optional fields fail in OpenAI-compat mode (400). https://discuss.ai.google.dev/t/structured-output-optional-fields-dont-work-in-openai-sdk-compatibility-mode/82329
- `[gh699]` googleapis/python-genai #699 — response_schema rejects Pydantic default values. https://github.com/googleapis/python-genai/issues/699
