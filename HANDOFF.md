# Handoff — ReAct tested, the Producer measured and reworked, cross-model debate running, deck at V68 (2026-10-18, evening)

Read this first, then CLAUDE.md (Status, last bullets) and TALK.md (2026-10-18 sections). Earlier
handoffs: `HANDOFF_2026-10-18_morning.md`, `HANDOFF_2026-10-11.md` (history only).

## 1. State of the tree

- **Nothing is committed** (~37 changed paths incl. earlier sessions' work; `talk/` and `out/` untracked).
  Commit only when Sujit asks.
- **Suite: 1285/1285 pure tests.** Run every file with dummy keys and check EACH file's x/y:
  `export GEMINI_API_KEY=invalid OPENAI_API_KEY=invalid CREWAI_DISABLE_TELEMETRY=true; for f in tests/test_*.py; do uv run python $f | tail -1; done`
- `.env` now holds `GEMINI_API_KEY` and `OPENAI_API_KEY` (never print values).

## 2. IN FLIGHT — the cross-model debate (check this first)

- Started 17:41 in the background: `uv run python -m crew.seed_experiment --cross openai/gpt-6.1-sol:high
  gemini/gemini-3.8-flash:high "a slow doom gat in Darbari Kanada, key of C sharp"` (RMA_LLM_TIMEOUT_S=420).
  At handover: 18 model calls done, 0 failures, still running. Output dir `out/seed_ab_20261018_174135/`
  (blind clips p1_X/Y/Z.wav + key.json + record appear at the END); log copy `out/seed_ab_20261018_174135.log`
  (the live log is in the old session's scratchpad). Arms: **single** (Gemini high) / **debate-same**
  (Gemini high vs itself) / **debate-cross** (Sol high vs Gemini high). If the dir is still empty, the run
  died with the old session — re-run the command above (ask Sujit; ~25 calls, Sol + Gemini at high).
- When done: (1) give Sujit the blind clips; (2) analyse **idea flow** from the record: draft diversity
  same-model vs cross-model (`draft_diversity`), what each revised seed took from the rival (head cell,
  sam swara, riff rhythm/roots, form), whether arguments cite music or numbers, selector pick vs his ear.
- Verdict feeds the debate cards (`talk/deck/patterns.py` debate record; currently "Parked: same model,
  same facts" — the hypothesis this run tests).

## 3. What was built / found this session

**ReAct (step 1 of the plan):** `hear_phrase` tool (`crew/hearing.py`, `crew/hearing_tool.py`, behind
`RMA_HEAR`, OFF). Live A/B (`talk/audio/hear_ab.py`): the first pair was confounded (song C's seed hook rode
the prompt); fresh pair: blind reviewer + **Sujit's ear prefer A (no tool)** — B fixed what the tool showed
and lost Darbari's vakra cadence. Lesson (TALK.md): a tool decides what the agent attends to. Off it stays.

**The Producer, measured** (`talk/audio/producer_analysis_20261018.json`): revised round 0 in 14/14 runs;
30/36 plans copied Rasik near-verbatim; 87% of scores 4-5; after an edit scores rose 10 / fell 9 / flat 5;
6/14 shipped a version below its own earlier round. High-effort run (`talk/audio/high_effort.py`, trace
57af304fd1ad): its one edit lowered its own score and shipped; **Sujit blind: the first draft "clearly
better"** (`out/blind_producer_20261018_165129/`).
**Reworked (BUILT, pure-tested, LIVE-UNTESTED):** champion take + `crew/compare.py` (draft vs revision,
asked twice with order swapped, revision kept only if it wins both; failure keeps the draft), Flow `Version`
snapshot + `_keep_the_better`, `MAX_JUDGE_ROUNDS=1` (judge's revision ends the loop), new
`compare_versions` task + `VersionChoice` contract, Producer prompt: ACCEPT by default, problem-not-swaras
instructions, no auto-adopt of Rasik, no numbers quoted. Scores schema unchanged (UI + stop rule read it).
**Next:** slim the 11-criterion scores; a 3-run blind test draft-vs-final (live — ask).

**Effort/models:** high effort (Composer + judges) = 4x thinking, only gain Ga/Dha held 0→4. Plain prompt on
older models: gemini-2.5-* all refused ("no longer available"); `gemini-3-flash-preview` low = a 20-s fragment,
parts misaligned; asked 3.5 → **answered by 3.6** (5/32 distinct guitar bars); all 0 wrong notes.
`talk/audio/pure_songs.py` now has `RMA_PURE_THINKING` and model-suffixed clip ids. Git history: there was
**no plain-LLM baseline before the agents** (July "naive" was hand-written) — memory `no-pre-agent-baseline`;
the Act 1 "one prompt: plausible" slide is unmeasured (Sujit: don't change yet).

**Wiring fixes (verified):** `crew/config.py` `composer_override(model, effort)` (ContextVar) +
`seed_debate.Side` / `debate(sides=, arm=)` + `seed_debate_crew.llm_side` + `seed_experiment --cross`.
`build_llm`: non-Gemini models got Gemini's `http_options` (crash) → plain `timeout`; OpenAI uses
`api="responses"` because CrewAI's Chat-Completions path sends reasoning_effort only to "o1" names (Sol had
silently run at medium). No temperature anywhere (OpenAI docs: Sol effort low/medium(default)/high/xhigh/max).
**CAUTION:** an edit to `crew/config/tasks.yaml` once anchored on a heading shared by two tasks and cut both;
repaired from trace-rendered prompts. Anchor edits inside the task's own block.

## 4. The deck — https://claude.ai/artifact/9fb9xNiGt1rF8UWXMQ82ja (Version 68, 61 slides)

Source `talk/deck/story.py` (+ `patterns.py`, `scenes.py`, `workflow.py`, `titles/bot.py`). Publish
procedure unchanged (story.py → preview.py (LOOK) → clickcheck.py 0 BLOCKED → publish changed files; send
deck.json only when order changes; read any unread live file first). Changes this session:
title = small geometric **DevDay bot** playing sitar (`titles/bot.py`, headbang + strum, reusable per talk);
dividers = outlined numeral + progress strip with the bot; quote slides = radial purple glow + mustard “;
Music 101 `process` scene ("four jobs, not four instruments"); slide 10 poses the question, `ladder` (end of
Act 2) answers it (correct → raga's words → music); step-by-step workflow graphs steps 3–11
(`workflow.py`); 7 pattern INTRO cards = **animated persona scenes** (`scenes.py`: envelopes fly, bubbles
pop with verbatim trace quotes) + What/Use/Avoid; 7 VERDICT cards in Act 3 (incl. "Predefined workflow —
Kept", evaluator "Reworked — revised the first draft 14 times out of 14"); `balance` take-home (steering
scale); vote moved before close (pick composes live during Q&A; pre-rendered fallback NOT made yet).
**Open on the deck:** 61 slides is long (trim candidates l1, l4, eleven); "legal"→"correct" elsewhere
(step 7, guardrail, eleven); slide 4 & quote both say "Swap the raga…"; experiment caveats; debate verdict
awaits §2; pre-rendered vote fallbacks (live, ask).

## 5. Next session, in order

1. Collect §2 (clips + idea-flow analysis), update the debate card with the result.
2. Producer: scores slimming + 3-run blind draft-vs-final test of the reworked loop (ask before live).
3. Challenger (the morning plan; the keep-the-best rule already embodies "original wins ties").
4. Deck trims + the open items above.

Rules unchanged: ask Sujit before ANY live run; batch; trace; never overwrite a render; commit only when asked.
