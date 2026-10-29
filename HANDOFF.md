# Handoff — state after the 2026-10-20 work, the DevDay promo renders and the run-history commit (2026-10-29)

Read this first, then CLAUDE.md (Architecture + the last Status bullets) and TALK.md from
"One prompt per job" onward. Earlier handoffs (history only): `HANDOFF_2026-10-19.md`,
`HANDOFF_2026-10-18_evening.md`, `HANDOFF_2026-10-18_morning.md`, `HANDOFF_2026-10-11.md`;
the talk deck's own handover is `talk/HANDOVER.md`.

## 1. State of the tree

- All product code is committed (last code commit `0e253cf`, 2026-10-20). Suite: **1400 pure tests,
  all green** — `export GEMINI_API_KEY=invalid OPENAI_API_KEY=invalid CREWAI_DISABLE_TELEMETRY=true;
  for f in tests/test_*.py; do uv run python $f | tail -1; done`.
- **The run history is now in git** (2026-10-29): every render's composition JSON, MIDI, chart
  (`*.arrangement.json`) and listening report in `out/`, every experiment directory's notes and
  transcripts, every agent trace in `traces/`, and the talk clips' source data in `talk/audio/build/`.
  WAV/MP4 and image stills stay out (a WAV re-renders from its JSON for free). Each has a catalogue
  explaining what every run was for and what it showed: **`out/README.md`**, **`traces/README.md`**,
  **`talk/audio/README.md`**. New runs should get a row there when they are made.
- Defaults: the five-agent path (`RMA_COMPOSER`, `RMA_RHYTHM_SECTION` on), head self-revision on
  (`RMA_HEAD_REVISE`), `RMA_HEAR` / `RMA_AGENTIC_COMPOSER` / `RMA_LISTEN` off, no time budget unless
  `RMA_BUDGET_S` is set.

## 2. What happened since the last handoff

- **2026-10-20** (commits `a3c30f0`, `0e253cf`, `4f07426`): GPT's code and prompt reviews built, each
  claim verified first — acceptance is a final code check with an explicit `outcome`; Rasik and the
  Producer judge blind in parallel and meet in a second look; the notes debate runs only on a named
  concern; the alap and the long taan have their own prompt templates; the rhythm section picks each
  section's drum feel. One live run, `fusion_20261020_144218_darbari_symph`: accepted; the Producer's
  taan revision won both orders of the blind compare. After Sujit's ear: Darbari sways 25 c, a swaying
  note takes no kan, the taan's pulse follows the tempo. Lessons are in TALK.md ("One prompt per job",
  "Stopping is not accepting", "The judge was an echo", "A constant written at one tempo", "Four
  questions before you add an agent", "Your decomposition has an expiry date").
- **2026-10-21**: DevDay promo runs (traces `devday-promo-*`). Three produced songs —
  `fusion_20261021_184831` (Bhairavi), `_184834` (Bhairav), `_185852` (Charukeshi symphonic); the two
  Kirwani symphonic runs and the Darbari doom-symphonic run left no render (see `traces/README.md`;
  some hit "402 credits depleted"). No code changed.
- The talk deck is a Claude Slides artifact (https://claude.ai/artifact/9fb9xNiGt1rF8UWXMQ82ja, V195
  per memory); source in `talk/deck`, the slide-10 studio scene in `talk/studio`.

## 3. Open, in rough priority (ask before any live call)

1. **Darbari's ga sway direction** — two sources (Levy 1982 via van der Meer 2015; Arnold/Bor/van der
   Meer 1985) say it swings UP from a low base; ours dips. A free A/B render for Sujit's ear.
2. **Outro overrun** (found 2026-10-19 in the Bhairav notes debate): the sitar's outro phrase ran 17
   beats in a 16-beat section and no check catches it. Still unfixed.
3. GPT prompt items left: raga-specific cadence examples in the intro brief (it currently shows
   Darbari's `g m R` to every raga), a "no change" option for the notes debate, short-taan/song-taan
   templates.
4. Producer: slim the scores schema (the UI and stop rule read it today).
5. Ears calibration (Gemini Pro vs an audio model) on Sujit's judged pairs before any audio judge
   gates anything; the rehearsal stays parked until then.

## 4. Cautions

- Ask Sujit before ANY live render or full eval; one live check, batched.
- Changing a prompt shifts trace replays; restore the checks as recorded
  (`talk/audio/notes_debate_run.py::_checks_as_recorded`).
- Direct google-genai audio calls are invisible to the CrewAI tracer — log them yourself.
- When deleting code, grep prompts and checks for anything that relied on it (the jod lesson).
