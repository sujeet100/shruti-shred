# Handoff — measured self-revision, alap call-and-answer, the rehearsal (parked), the notes debate (2026-10-19)

Read this first, then CLAUDE.md (Status, last bullet) and TALK.md ("2026-10-19 — what the day taught").
Earlier handoffs: `HANDOFF_2026-10-18_evening.md`, `HANDOFF_2026-10-18_morning.md` (history only).

## 1. State of the tree

- **Nothing committed since `521554b`** (~36 paths; `talk/` and `out/` untracked). Commit only when Sujit asks.
- **Suite: 1343 pure tests.** `export GEMINI_API_KEY=invalid OPENAI_API_KEY=invalid CREWAI_DISABLE_TELEMETRY=true;
  for f in tests/test_*.py; do uv run python $f | tail -1; done`
- **Deck: V75** (https://claude.ai/artifact/9fb9xNiGt1rF8UWXMQ82ja) — self-correction pattern card (slide 15),
  debate verdict rewritten with the control, new self-correction verdict after it (65 slides).

## 2. DONE — the notes debate (out/notes_debate_20261019_094935). Sujit: riff change LIKED; head rewrite a sidegrade (original had more tension). Best = riff_final.wav

`talk/audio/notes_debate_run.py` was running at handover → `out/notes_debate_<stamp>/` (transcript.md,
record.json, original/sitar_proposed/sitar_final/riff_proposed/riff_final/both_final.wav). Sitarist = Gemini,
guitarist = `openai/gpt-6-luna` medium. If the dir has no transcript.md the run died — re-run (~6 calls, ask).
When done: summarise the exchange in plain words for Sujit (did they argue NOTES? did the critique change
the other's rewrite? did anyone withdraw?), give him the files; his ear judges. Check whether the guitarist's
riff edit changed the drums (they are re-derived from the guitar).

## 2b. DONE, awaiting the ear — notes debate #2, Bhairav (out/notes_debate_20261019_101238; song
fusion_20261019_100727_bhairav). Found a real bug: the sitar's outro phrase is 17 beats in a 16-beat
section (no check catches an outro overrun) — fix candidate, ask first.

## 3. What was found and built today (details: TALK.md 2026-10-19 sections)

- **Head-debate control** (`talk/audio/head_control_run.py`): solo revision with the same measurements made
  the debaters' move at half the cost → debate parked; built **measured head self-revision** (`crew/
  head_report.py`, `crew/head_revision.py`, `RMA_HEAD_REVISE` on). Live: fired (6% mandra), revision ended on
  Ni and was discarded → guardrail now holds the keep rule's lines.
- **Fresh live run** `fusion_20261019_083259_fresh` (`talk/audio/fresh_run.py`, notes in `_rounds/notes.md`):
  the reworked Producer ACCEPTED the first draft (first ever); sparse manjha/antara measured in the guitar.
- **Rehearsal** (two live runs, `out/rehearsal_20261019_075624`, `_092350`): unanimous, subtractive, ears
  hallucinated; Sujit: "r0 better, r3 hollow" → PARKED. Kept from it: sparse manjha/antara, chugs under taan.
- **Alap** rebuilt to Sujit's rules (call off the nyas / answer onto a core nyas / calls may pile up / no
  climb into a main nyas / jod pulse). One live alap A/B: `out/alap_ab_20261019_092312/` (B predates the
  no-climb rule; its phrase 4 climbs into Re — Sujit heard it as off).
- Infra: trace replay `tolerance=`; audio judge timeout + rehearsal resume; `gpt-6-luna` has NO audio input.

## 4. Waiting on Sujit's ear

- The notes debate versions (above).
- `out/alap_ab_20261019_092312/A.wav` vs `B.wav` (old vs call-and-answer alap) — a fresh alap call under the
  no-climb rule is the obvious next live step (1 call, ask).
- `out/fusion_20261019_083259_fresh.wav` as a whole.

## 5. Next (ask before any live call)

1. Collect + explain the notes debate; if it argued music and Sujit likes a version, decide whether a
   notes-debate pass belongs in the pipeline (cost ~6 calls) or stays a talk experiment.
2. One alap call under the full rules (no-climb included).
3. Ears calibration (Gemini Pro vs OpenAI `gpt-audio`) on Sujit's judged pairs — gates any audio judge.
4. Deck: the rehearsal + notes-debate story (menu bounds the debate; ears describe the map) once judged.
5. Producer: slim the scores schema; blind draft-vs-final once it revises again.

## 6. Cautions

- Changing a prompt shifts trace replays (sizes); restore the checks as they were (see
  `talk/audio/notes_debate_run.py::_checks_as_recorded`).
- Direct google-genai audio calls are invisible to the CrewAI tracer — log them (rehearsal `calls.jsonl`).
- When deleting code, grep prompts and checks for anything that relied on it (the jod lesson).
