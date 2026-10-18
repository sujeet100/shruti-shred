# Handoff — the redesign is built; the first live run exposed why the lead goes silent (2026-10-11, ~23:59)

Read this first, then CLAUDE.md (Architecture + Status were updated this session) and DESIGN.md
from "THE REDESIGN" onward. Everything below is uncommitted.

## 1. State of the tree

- **Nothing is committed.** 79 changed paths since `a9b1658` (this session + earlier uncommitted
  work). Deleted files: `crew/arranger.py`, `crew/conductor.py`, `crew/repairs.py`,
  `tests/test_arranger.py`, `tests/test_conductor.py`. `talk/` is untracked.
- **Suite: 934 pure tests green**, `uv run ruff check crew tests` clean (run every file:
  `for f in tests/test_*.py; do uv run python $f; done` — there is no pytest in the env).
- **UI server is running** (`uv run python -m ui.server`, port 8500, legacy composers, no
  `RMA_COMPOSER`/`RMA_LISTEN`). Restart it after any code change — it caches modules.
- **Model:** `gemini/gemini-3.8-flash`, pinned (verified answering as itself). **No temperature
  anywhere.** Thinking level `low` everywhere — 3.8 REJECTS `minimal` (400), which broke the first
  live run until fixed. CrewAI's trace reports `reasoning_tokens: 0` (it doesn't map Gemini's thought
  count) — don't read that as "no thinking". No prompt caching happened (cached_prompt_tokens 0).

## 2. What this session built (details: DESIGN.md "THE REDESIGN — BUILD RECORD")

- Riff: strict voicing by stroke FUNCTION (`crew/riff_voicing.py`), raga half-step shapes,
  raga-derived home root (Marwa → Dha), verifier split HARD vs advisory (`texture_notes`), the
  climax plays a PEDAL at full density, `anchor` decides generation order (riff_first is real).
- Gat optional (`form: gat|song`); gat/intro verifiers split HARD vs CRAFT; climax-taan long holds →
  jhala.
- Critics: Ustad = code; Rasik = consultant (≤3 lead suggestions); Producer = the one judge with a
  `RevisionPlan`; `crew/triage.py`, `crew/revision.py`; Conductor, debate, Arranger deleted; grinds kept.
- The single-owner Composer behind `RMA_COMPOSER` (seed call: chart + main riff + hook; develop reuses
  the loops; seeds ride the Arrangement). **Never run live.**
- Advisory listening pass behind `RMA_LISTEN` (`crew/loudness.py`, `crew/listening.py`, Pro, blind,
  cross-checked). **Never run live.**

## 3. The first live run — what went wrong (Sujit: "too poor, lead empty most of the time, too slow")

Evidence: `out/fusion_20261011_234242.{wav,json,arrangement.json}`, trace `traces/15fbd6571f72.json`
(browse: `uv run python -m crew.trace_portal` → :8420). Legacy composers path, listening off.
Query: the 90 s Bhairav song-form prompt (E, teentaal 128, half-step riff, hard stop).

1. **Composers labelled 3 sections `intro`** (alap + the riff section + the main melody section,
   beats 0-96). The song-form guardrail allows `intro` anywhere.
2. **`intro` ⇒ the lead treats it as an alap**, ending on a held Sa that rings out to fill the section:
   section 1 ends on a 15-beat Sa; section 2 (48 beats, the MAIN melody, fg=lead) is ONE G held 48
   beats — the model returned a 1-note 1-beat cell and placement stretched it. A plucked sitar decays
   in ~a beat ⇒ ~30 s of audible silence.
3. **Best-of-N picked the emptiest take**: `_generate_verified_cell` keeps the take with the FEWEST
   violations; a near-empty cell trips the fewest checks.
4. **No judge saw it**: the Producer scored balance 4-5 ("lead has ample room") three times — on the
   score a 48-beat note looks like melody; no metric is decay-aware.
5. **The revise loop thrashed at full price**: all 3 verdicts targeted the taan's scalar runs; each
   revise regenerated the WHOLE lead (9 calls; phase 2 splices only the plan's sections but still pays
   for the whole voice), and the taan came back scalar every time — phase 1b had DEMOTED the taan
   scalar-run cap to craft (a cheap local re-roll became failed whole-voice revises). 41 calls, ~7.5 min.
6. Over-fill: the breakdown riff put `hammer_on` on nearly every stroke (voicing leaves legato single
   ⇒ no power chords); the alap put a meend on nearly every note and `murki` on every note.

## 4. NEXT — the fixes (proposed, Sujit asked for a handoff before approving; all free code)

| # | Fix | Where |
|---|-----|-------|
| a | `intro` only on the FIRST section, `outro` only on the LAST — both forms | `crew/composers.py` `_GAT_CHECKS`/`_SONG_CHECKS`/`draft_error` |
| b | No lead note held past the sitar's decay: cap any lead hold at ~4 beats everywhere (generalise `animate_long_holds`, now taan_long only; revisit `_ring_out_intro` and the short-cell extension in placement); only the piece's final ring is exempt | `crew/lead.py` |
| c | Best-of-N ranks by SEVERITY: an underfilled/near-empty cell always loses | `crew/lead.py` `_generate_verified_cell` (and the same pattern in `riff_texture.verified_riff`) |
| d | Decay-aware **audible lead coverage** metric per section → Producer prompt; code triage forces a lead revise of a lead-foreground section with <~40% audible lead (physical ⇒ hard) | `crew/metrics.py`, `assess_composition` in `crew/config/tasks.yaml`, `crew/triage.py` |
| e | Restore the taan scalar-run cap as HARD (local re-roll) | `crew/gat_verifier.py` `check_taan` |
| f | Section-scoped regeneration (call the model only for the plan's sections) + stop rule (same target twice unimproved ⇒ accept) | `crew/flow.py` `_regenerate`, `crew/revision.py`, `generate_lead`/`generate_riff` |
| g | Normalise meaningless legato (hammer_on after a rest / on a repeated pitch / first note) before voicing; report meend over-use as craft | `crew/riff_voicing.py` or the riff boundary; `crew/gat_verifier.py` |

Then ONE live run (ask Sujit first — CLAUDE.md cost rules): ideally `RMA_COMPOSER=1 RMA_LISTEN=1`
on the same prompt, and compare against this run.

## 5. Still waiting on Sujit

- **Grind treatment re-listen** (the corrected sets): `out/grind_{keep,damp,resolve}_FA_src_20261011_224721.wav`
  (Bhairav) and `..._YA_src_20261011_224756.wav` (Yaman). His first verdict was KEEP; phase 2
  implemented keep (no damping at all). Ignore grind files stamped 223522/224141/224547/224605.
- **The live batch**: (1) 3.8 smoke — DONE implicitly (thinking levels probed: low/medium/high OK,
  minimal 400); (2) single-call re-baseline on 3.8 (`talk/audio/pure_songs.py`, ~31k tokens);
  (3) one interpreter eval at default temperature; (4) a Composer run; (5) listening calibration
  (Sujit ranks 6-8 renders blind; judge ≥70% pairwise agreement, ≥80% order consistency).
- The UI page (`ui/app.html`, `ui/README.md`) still shows the debate/Conductor — the UI session's job;
  the event stream still works (final call = VERDICT with `data={"decision","plan"}`).

## 6. How this session worked (keep doing it)

- Measure from saved JSON/MIDI/traces before changing anything; free A/B renders via the scripts in
  `talk/audio/` (`grind_ab.py`, `harmony_ab.py`, `climax_ab.py`, `revoice.py`, `pure_songs.py`).
- Subagents in the SHARED tree on DISJOINT files (worktrees would start from the stale HEAD because
  nothing is committed); anything sharing `flow.py`/`contracts.py`/`tasks.yaml` runs in sequence.
- Principle (Sujit): build the RIGHT decomposition, not one for teaching — the journey is the talk.
  Hard checks only for what is physical/structural/raga-legal; taste is measured and reported. The
  lesson of this run: "physical" includes the sitar's DECAY — a held note on a plucked string is silence.
